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
      // The Pi runtime emits { result: { content, details }, isError } on
      // tool_execution_end — there is no `output` field. Success requires a
      // clean execution (isError falsy) and the tool's own ok receipt.
      return {
        category: "tool_result",
        turn_index: turnIndex(event),
        tool_name: toolName(event),
        status: !event.isError && event?.result?.details?.ok === true ? "ok" : "failed",
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
 * Phase 6a-1: bounded conversation-history prefix builder.
 *
 * History is an OPTIONAL prompt-text prefix, never a session-store write and
 * never a change to the per-turn AgentSession isolation model. Only normalized
 * user/assistant display text is injected; tool input/result, thinking, system
 * and secret-bearing messages are filtered out before rendering (privacy
 * boundary). The rendered block is capped at `maxBytes` (default mirrors the
 * kernel MAX_PROMPT_BYTES budget semantics) by dropping the OLDEST turns first
 * and then hard-truncating to a whole UTF-8 boundary.
 */
export const MAX_HISTORY_CONTEXT_BYTES = 24 * 1024;
const HISTORY_ROLES = Object.freeze(["user", "assistant"]);
const HISTORY_BLOCK_START = "<conversation_history>";
const HISTORY_BLOCK_END = "</conversation_history>";

function normalizeHistoryTurn(turn) {
  if (!turn || typeof turn !== "object" || Array.isArray(turn)) return null;
  const role = typeof turn.role === "string" ? turn.role : "";
  if (!HISTORY_ROLES.includes(role)) return null;
  const content = typeof turn.content === "string"
    ? turn.content
    : (typeof turn.display_text === "string" ? turn.display_text : "");
  if (!content) return null;
  return { role, content };
}

/**
 * Render normalized history turns into a bounded, clearly marked context block.
 *
 * @param {Array<{role: string, content: string}>} historyTurns
 * @param {{maxBytes?: number}} [options]
 * @returns {{text: string, turn_count: number, bytes: number, truncated: boolean}}
 */
export function buildHistoryContext(historyTurns, { maxBytes = MAX_HISTORY_CONTEXT_BYTES } = {}) {
  const turns = Array.isArray(historyTurns)
    ? historyTurns.map(normalizeHistoryTurn).filter(Boolean)
    : [];
  if (turns.length === 0) return { text: "", turn_count: 0, bytes: 0, truncated: false };
  const render = (items) =>
    `${HISTORY_BLOCK_START}\n${items.map((turn) => `<turn role="${turn.role}">${turn.content}</turn>`).join("\n")}\n${HISTORY_BLOCK_END}`;
  let candidates = [...turns];
  let text = render(candidates);
  let truncated = false;
  // Drop the OLDEST turns first until the block fits, but always keep the most
  // recent turn (hard-truncated below) so a single oversized message still
  // contributes context instead of vanishing entirely.
  while (Buffer.byteLength(text, "utf8") > maxBytes && candidates.length > 1) {
    candidates = candidates.slice(1);
    truncated = true;
    text = render(candidates);
  }
  const encoded = new TextEncoder().encode(text);
  if (encoded.length > maxBytes) {
    truncated = true;
    // Decode on a whole UTF-8 boundary; an incomplete trailing sequence is
    // replaced with U+FFFD instead of emitting an invalid byte stream.
    text = new TextDecoder("utf-8").decode(encoded.subarray(0, maxBytes));
  }
  return { text, turn_count: candidates.length, bytes: Buffer.byteLength(text, "utf8"), truncated };
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
  history_turns = null,
  history_max_bytes = MAX_HISTORY_CONTEXT_BYTES,
  signal,
  timeoutMs = 30000,
} = {}) {
  if (!session) throw new TypeError("session is required");
  if (typeof prompt !== "string" || !prompt.trim()) throw new TypeError("prompt is required");
  if (!Array.isArray(activeToolNames)) throw new TypeError("activeToolNames must be an array");

  // Plan 61-09: the governed pre-prompt context builder runs before any
  // AgentSession.prompt and never blocks the turn on an omitted projection.
  const projection = await buildProjectionContext({ scope, binding, modelProjectionProvider });

  // Phase 6a-1: optional normalized history is rendered as a clearly marked,
  // byte-bounded prefix. It is prompt text only — never persisted to any
  // session store and never part of the per-turn session identity.
  const history = buildHistoryContext(history_turns, { maxBytes: history_max_bytes });
  const effectivePrompt = history.text ? `${history.text}\n\n${prompt}` : prompt;

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
      await session.prompt(effectivePrompt, {
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
      ...(history.turn_count > 0 ? { history: { injected: history.turn_count, bytes: history.bytes, truncated: history.truncated } } : {}),
      ...(projection.receipt ? { projection: projection.receipt } : {}),
    },
  };
  return { ok: true, turn };
}

export const SAFE_TURN_CATEGORIES = SAFE_CATEGORIES;
