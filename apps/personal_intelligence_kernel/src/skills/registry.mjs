import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

export const SKILL_SCHEMA = "pi-project-skill-v1";
const PROFILES = new Set(["production", "operator", "test"]);
const PRIVACY = new Set(["R0", "R1", "R2"]);
const STATUSES = new Set(["active", "deprecated"]);
const TOKEN = /^[a-z][a-z0-9_.-]{1,127}$/;

export class SkillRegistryError extends Error { constructor(code, message = code) { super(message); this.name = "SkillRegistryError"; this.code = code; } }

function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize);
  if (value && typeof value === "object") return Object.fromEntries(Object.keys(value).sort().map((key) => [key, canonicalize(value[key])]));
  return value;
}
const digest = (value) => createHash("sha256").update(JSON.stringify(canonicalize(value))).digest("hex");
const canonicalSkill = (skill) => { const copy = { ...skill }; delete copy.checksum; return copy; };
export const skillChecksum = (skill) => digest(canonicalSkill(skill));

function fail(code) { throw new SkillRegistryError(code); }
function token(value) { return typeof value === "string" && TOKEN.test(value); }

export class SkillRegistry {
  constructor({ manifests = [], allowedTools = [], profile = "production", now = new Date() } = {}) {
    this.manifests = manifests;
    this.allowedTools = new Set(allowedTools);
    this.profile = profile;
    this.now = now;
  }
  validate(skill) {
    const required = ["schema", "id", "version", "purpose", "input_schema", "output_schema", "profile", "privacy_ceiling", "allowed_tools", "instruction_checksum", "steps", "max_steps", "max_rounds", "token_budget", "cost_budget", "timeout_ms", "stops", "recovery", "owner", "expires_at", "status", "checksum"];
    if (!skill || required.some((key) => !(key in skill))) fail("skill_manifest_invalid");
    if (skill.schema !== SKILL_SCHEMA || !token(skill.id) || !/^\d+\.\d+\.\d+$/.test(skill.version)) fail("skill_manifest_invalid");
    if (skill.profile !== this.profile || !PROFILES.has(skill.profile) || !PRIVACY.has(skill.privacy_ceiling) || !STATUSES.has(skill.status)) fail("skill_profile_invalid");
    if (skill.checksum !== skillChecksum(skill)) fail("skill_checksum_mismatch");
    if (!/^[0-9a-f]{64}$/.test(skill.instruction_checksum) || !skill.owner || Date.parse(skill.expires_at) <= this.now.getTime()) fail("skill_expired");
    if (!Array.isArray(skill.allowed_tools) || skill.allowed_tools.length === 0 || skill.allowed_tools.some((tool) => !token(tool) || !this.allowedTools.has(tool))) fail("skill_tool_escalation");
    if (!Array.isArray(skill.steps) || skill.steps.length === 0 || skill.steps.length > skill.max_steps || skill.max_steps < 1 || skill.max_steps > 64) fail("skill_steps_invalid");
    if (!Number.isInteger(skill.max_rounds) || skill.max_rounds < 1 || skill.max_rounds > 16 || !Number.isInteger(skill.token_budget) || skill.token_budget < 1 || !Number.isInteger(skill.cost_budget) || skill.cost_budget < 0 || !Number.isInteger(skill.timeout_ms) || skill.timeout_ms < 1) fail("skill_budget_invalid");
    if (!Array.isArray(skill.stops) || skill.stops.length === 0 || !skill.recovery || typeof skill.recovery !== "object") fail("skill_recovery_invalid");
    const ids = new Set();
    for (const step of skill.steps) {
      if (!step || !token(step.id) || ids.has(step.id) || !token(step.tool) || !this.allowedTools.has(step.tool) || step.receipt_required !== true || typeof step.requires_confirmation !== "boolean") fail("skill_step_invalid");
      ids.add(step.id);
      if ((step.tool === "snapshot.activate" || step.tool === "snapshot.rollback") && step.requires_confirmation !== true) fail("skill_checkpoint_missing");
    }
    return Object.freeze({ ...skill, steps: Object.freeze(skill.steps.map((step) => Object.freeze({ ...step }))), allowed_tools: Object.freeze([...skill.allowed_tools]) });
  }
  load() {
    const valid = [];
    for (const skill of this.manifests) { try { valid.push(this.validate(skill)); } catch { /* invalid manifests abstain */ } }
    this.manifests = valid;
    return valid;
  }
  select({ purpose, input_schema, task_id, session_id, evidence_ref } = {}) {
    const matches = this.manifests.filter((skill) => skill.status === "active" && skill.profile === this.profile && skill.purpose === purpose && (!input_schema || skill.input_schema === input_schema));
    if (matches.length !== 1) return { selected: false, reason: matches.length ? "skill_collision" : "skill_not_found", skill: null };
    const skill = matches[0];
    return { selected: true, reason: "selected", skill: { id: skill.id, version: skill.version, checksum: skill.checksum, purpose: skill.purpose, task_id: task_id ?? null, session_id: session_id ?? null, evidence_ref: evidence_ref ?? null } };
  }
  static async fromFile(path, options = {}) { const raw = JSON.parse(await readFile(resolve(path), "utf8")); const items = Array.isArray(raw) ? raw : raw.skills; return new SkillRegistry({ ...options, manifests: items ?? [] }); }
}
export const createSkillRegistry = (options) => new SkillRegistry(options);
