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
  signal,
  timeoutMs = 30000,
} = {}) {
  if (!session) throw new TypeError("session is required");
  if (typeof prompt !== "string" || !prompt.trim()) throw new TypeError("prompt is required");
  if (!Array.isArray(activeToolNames)) throw new TypeError("activeToolNames must be an array");

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
      await session.prompt(prompt, { source: "rpc", expandPromptTemplates: false });
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
    },
  };
  return { ok: true, turn };
}

export const SAFE_TURN_CATEGORIES = SAFE_CATEGORIES;
