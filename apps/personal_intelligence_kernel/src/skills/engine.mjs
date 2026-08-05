import { createHash } from "node:crypto";

export const SKILL_STATES = Object.freeze(["pending", "running", "waiting_confirmation", "completed", "failed", "cancelled", "outcome_unknown"]);
const TERMINAL = new Set(["completed", "failed", "cancelled"]);

export class SkillEngineError extends Error { constructor(code, message = code) { super(message); this.name = "SkillEngineError"; this.code = code; } }
const digest = (value) => createHash("sha256").update(JSON.stringify(value)).digest("hex");
const nowIso = () => new Date().toISOString();

function stateKey(skill, taskId, sessionId) { return `${skill.id}:${taskId ?? ""}:${sessionId ?? ""}`; }

export class SkillEngine {
  constructor({ registry, now = new Date() } = {}) { if (!registry) throw new SkillEngineError("registry_required"); this.registry = registry; this.now = now; this.states = new Map(); }
  _newState(skill, { task_id, session_id, idempotency_key, input }) {
    if (!task_id || !session_id || !idempotency_key) throw new SkillEngineError("skill_binding_required");
    const key = stateKey(skill, task_id, session_id);
    const existing = this.states.get(key);
    if (existing) return existing;
    const state = { schema: "pi-skill-execution-v1", state: "pending", skill_id: skill.id, skill_checksum: skill.checksum, task_id, session_id, idempotency_key, input_ref: { checksum: digest(input ?? {}) }, step_index: 0, steps: [], rounds: 0, started_at: nowIso(), updated_at: nowIso() };
    this.states.set(key, state);
    return state;
  }
  _stepIdempotency(state, step) { return `${state.idempotency_key}:${step.id}`; }
  _receipt(state, step, result) { return result?.receipt ?? result ?? { status: "success", tool: step.tool }; }
  async run({ skill, task_id, session_id, idempotency_key, input = {}, confirmed = false, executor, reconcile } = {}) {
    if (!skill || typeof skill !== "object") throw new SkillEngineError("skill_required");
    if (typeof executor !== "function") throw new SkillEngineError("executor_required");
    const state = this._newState(skill, { task_id, session_id, idempotency_key, input });
    if (TERMINAL.has(state.state)) return state;
    if (state.state === "outcome_unknown") {
      if (typeof reconcile !== "function") return { ...state, state: "outcome_unknown", recovery_required: true };
      const recovered = await reconcile(state.steps[state.steps.length - 1]);
      if (!recovered) return { ...state, recovery_required: true };
      state.steps[state.steps.length - 1].status = "committed";
      state.steps[state.steps.length - 1].receipt = recovered;
      state.step_index += 1;
      state.state = "running";
    }
    state.state = "running";
    state.rounds += 1;
    if (state.rounds > skill.max_rounds) { state.state = "failed"; state.error_code = "skill_round_limit"; return state; }
    while (state.step_index < skill.steps.length) {
      if (state.steps.length >= skill.max_steps) { state.state = "failed"; state.error_code = "skill_step_limit"; return state; }
      const step = skill.steps[state.step_index];
      if (!skill.allowed_tools.includes(step.tool)) { state.state = "failed"; state.error_code = "skill_tool_escalation"; return state; }
      if (step.requires_confirmation && confirmed !== true) { state.state = "waiting_confirmation"; state.checkpoint = step.id; state.updated_at = nowIso(); return state; }
      const record = { step_id: step.id, tool: step.tool, status: "running", correlation_id: digest({ skill: skill.id, task: task_id, session: session_id, step: step.id }), idempotency_key: this._stepIdempotency(state, step), started_at: nowIso() };
      state.steps.push(record);
      try {
        const result = await executor({ skill, step, input, task_id, session_id, correlation_id: record.correlation_id, idempotency_key: record.idempotency_key });
        record.status = "committed"; record.receipt = this._receipt(state, step, result); record.completed_at = nowIso(); state.step_index += 1; state.updated_at = nowIso();
        if (step.requires_confirmation) {
          state.state = "waiting_confirmation";
          state.checkpoint = step.id;
          return state;
        }
      } catch (error) {
        record.status = error?.code === "outcome_unknown" ? "outcome_unknown" : "failed"; record.error_code = error?.code ?? "skill_step_failed"; record.completed_at = nowIso(); state.updated_at = nowIso(); state.state = record.status === "outcome_unknown" ? "outcome_unknown" : "failed"; return state;
      }
    }
    state.state = "completed"; state.updated_at = nowIso(); return state;
  }
  cancel({ skill, task_id, session_id } = {}) { if (!skill) return null; const state = this.states.get(stateKey(skill, task_id, session_id)); if (!state || TERMINAL.has(state.state)) return state ?? null; state.state = "cancelled"; state.updated_at = nowIso(); return state; }
  get({ skill, task_id, session_id } = {}) { return skill ? (this.states.get(stateKey(skill, task_id, session_id)) ?? null) : null; }
}

export const createSkillEngine = (options) => new SkillEngine(options);
