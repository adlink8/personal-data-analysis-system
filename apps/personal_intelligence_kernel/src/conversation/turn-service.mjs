/**
 * Pi-owned conversation turn adapter (Plan 61-03).
 *
 * `runConversationTurn` owns one real `AgentSession.prompt(...)` lifecycle for a
 * single turn: subscribe before prompt, set exactly the leased tool names, await
 * idle, then unsubscribe/dispose in `finally`. Only sanitized event categories
 * (tool_call / tool_result / settled / cancelled / outcome_unknown / failed) are
 * projected; body/prompt/completion/credential/secret values and keys never leave.
 */

const SAFE_CATEGORIES = Object.freeze(["tool_call", "tool_result", "settled", "cancelled", "outcome_unknown", "failed"]);

function turnIndex(event) {
  return Number.isInteger(event?.turnIndex) ? event.turnIndex : 0;
}

function toolName(event) {
  return typeof event?.toolName === "string" ? event.toolName : "unknown";
}

/** Project a raw Pi AgentSession event to a safe receipt category, or null. */
function projectSafeEvent(event) {
  switch (event?.type) {
    case "tool_execution_start":
      return { category: "tool_call", turn_index: turnIndex(event), tool_name: toolName(event) };
    case "tool_execution_end":
      return {
        category: "tool_result",
        turn_index: turnIndex(event),
        tool_name: toolName(event),
        status: event.output && typeof event.output === "object" && event.output.ok === true ? "ok" : "failed",
      };
    case "agent_settled":
      return { category: "settled", turn_index: turnIndex(event) };
    default:
      return null;
  }
}

/** Project the raw event buffer according to the terminal outcome state. */
function projectEvents(rawEvents, state) {
  if (state !== "settled") return [{ category: state, turn_index: 0 }];
  const projected = [];
  for (const event of rawEvents) {
    const safe = projectSafeEvent(event);
    if (safe) projected.push(safe);
  }
  return projected;
}

async function waitForIdleWithinBudget(waitForIdle, timeoutMs) {
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    await waitForIdle();
    return true;
  }
  let timer;
  try {
    return await Promise.race([
      Promise.resolve().then(() => waitForIdle()).then(() => true),
      new Promise((resolveRace) => {
        timer = setTimeout(() => resolveRace(false), timeoutMs);
        timer.unref?.();
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

/**
 * Plan 61-09 (HARNESS-07): governed pre-prompt projection context builder.
 *
 * Calls the fixed `personal.model_projection.get` provider with the turn's
 * scope/binding and injects ONLY compatible current derived/correctable context
 * (status current|uncertain) before `AgentSession.prompt`. Stale, conflicting,
 * unknown, empty, foreign-scope or version-less results are omitted with a
 * limitation in the receipt and are never presented as current truth. The
 * receipt always carries the projection version/freshness/limitations for an
 * injected projection and only limitations for an omission.
 */
function buildProjectionContext({ scope, binding, modelProjectionProvider }) {
  if (!scope || !binding || typeof modelProjectionProvider !== "function") {
    return { injected: [], receipt: null };
  }
  return Promise.resolve()
    .then(() => modelProjectionProvider({ scope, binding }))
    .then((result) => {
      const data = result?.data;
      if (!data || typeof data !== "object" || Array.isArray(data)) {
        return { injected: [], receipt: { omitted: true, limitations: ["projection provider returned no derived context"] } };
      }
      const status = data.status;
      const injectable = status === "current" || status === "uncertain";
      const scopeMatches = String(data.scope ?? "") === scope;
      const hasVersion = Number.isInteger(data.version) && data.version >= 1;
      const limitations = Array.isArray(data.limitations) && data.limitations.length > 0
        ? data.limitations
        : ["derived projection; not a personal fact or stable label"];
      if (!injectable || !scopeMatches || !hasVersion) {
        return { injected: [], receipt: { omitted: true, limitations } };
      }
      return {
        injected: [{
          projection_id: data.projection_id,
          version: data.version,
          provenance_class: data.provenance_class ?? "inference",
          scope: data.scope,
          status,
          valid_from: data.valid_from,
          valid_to: data.valid_to,
          observed_at: data.observed_at,
          confidence: data.confidence,
          uncertainty: data.uncertainty,
          freshness: data.freshness,
          support_refs: data.support_refs,
          support_count: data.support_count,
          conflict_refs: data.conflict_refs,
          conflict_count: data.conflict_count,
          conflicts: data.conflicts,
          supersession: data.supersession,
          limitations,
        }],
        receipt: {
          version: data.version,
          scope: data.scope,
          status,
          freshness: data.freshness,
          support_count: data.support_count,
          conflict_count: data.conflict_count,
          limitations,
        },
      };
    })
    .catch(() => ({ injected: [], receipt: { omitted: true, limitations: ["projection provider unavailable"] } }));
}

/**
 * Run one conversation turn on the supplied per-turn session.
 *
 * Returns `{ ok: true, turn }` for every terminal outcome; `turn.success` is only
 * true for `settled`. Cancellation and outcome_unknown are never success
 * envelopes and require the existing ledger reconcile controls.
 */
export async function runConversationTurn({
  session,
  prompt,
  activeToolNames = [],
  profile = "conversation",
  taskId = null,
  sessionId = null,
  idempotencyKey = null,
  skillId = null,
  skillChecksum = null,
  scope = null,
  binding = null,
  modelProjectionProvider = null,
  signal,
  timeoutMs = 30000,
} = {}) {
  if (!session) throw new TypeError("session is required");
  if (typeof prompt !== "string" || !prompt.trim()) throw new TypeError("prompt is required");
  if (!Array.isArray(activeToolNames)) throw new TypeError("activeToolNames must be an array");

  // Plan 61-09: the governed pre-prompt context builder runs before any
  // AgentSession.prompt and never blocks the turn on an omitted projection.
  const projection = await buildProjectionContext({ scope, binding, modelProjectionProvider });

  const rawEvents = [];
  const unsubscribe = typeof session.subscribe === "function"
    ? session.subscribe((event) => rawEvents.push(event))
    : null;
  let state = "outcome_unknown";
  try {
    if (signal?.aborted) {
      state = "cancelled";
      await session.abort?.();
    } else {
      session.setActiveToolsByName(activeToolNames);
      await session.prompt(prompt, {
        source: "rpc",
        expandPromptTemplates: false,
        ...(projection.injected.length > 0 ? { projection_context: projection.injected } : {}),
      });
      const settled = await waitForIdleWithinBudget(() => session.waitForIdle(), timeoutMs);
      state = settled ? "settled" : "outcome_unknown";
      if (!settled) await session.abort?.();
    }
  } catch (error) {
    state = "failed";
  } finally {
    if (unsubscribe) unsubscribe();
    try { session.dispose(); } catch { /* bounded disposal must continue */ }
  }

  const turn = {
    state,
    success: state === "settled",
    profile,
    task_id: taskId,
    session_id: sessionId,
    idempotency_key: idempotencyKey,
    skill_id: skillId,
    events: projectEvents(rawEvents, state),
    receipts: {
      skill_checksum: skillChecksum,
      tool_count: activeToolNames.length,
      timeout_ms: Number.isFinite(timeoutMs) ? timeoutMs : null,
      outcome: state,
      ...(projection.receipt ? { projection: projection.receipt } : {}),
    },
  };
  return { ok: true, turn };
}

export const SAFE_TURN_CATEGORIES = SAFE_CATEGORIES;
