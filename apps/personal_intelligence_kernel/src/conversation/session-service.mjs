/**
 * Governed empty-session provider (Plan 61-05).
 *
 * `conversation.session.create` is a named Kernel intent: after validating
 * sender/schema/binding/idempotency, it requests an approved project scope
 * through the Python canonical `conversation.project_scope.select` provider
 * (exactly one bridge call), then persists only governed empty Session metadata
 * `{session_id, project_scope_id, created_at, status: "empty"}` in the existing
 * Session store and returns an empty safe `ConversationThreadView`.
 *
 * It never writes canonical conversation bodies, Candidate, promotion, active
 * pointer or desktop persistence, and it never describes runtime text as
 * canonical history. Until a later canonical ingestion event the active body is
 * runtime/session-scoped only.
 */

import { sha256 } from "../events/schema.mjs";

const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9._:/_-]{0,255}$/;

export class SessionServiceError extends Error {
  constructor(code, message = code) {
    super(message);
    this.name = "SessionServiceError";
    this.code = code;
  }
}

function assertIdentifier(value, code) {
  if (typeof value !== "string" || !IDENTIFIER.test(value)) throw new SessionServiceError(code);
  return value;
}

/** Project-scope identity is a working-directory path: permissive but fail-closed. */
function assertScope(value, code) {
  if (typeof value !== "string" || !value || value.length > 512 || /[\x00-\x1f\x7f"\\]/.test(value)) {
    throw new SessionServiceError(code);
  }
  return value;
}

function emptyThreadView() {
  return {
    messages: [],
    state: "empty",
    limitation: "empty: no committed conversation history yet; runtime text stays session-scoped",
  };
}

/**
 * Create governed empty Session metadata after the Python canonical authority
 * approves the requested project scope.
 *
 * @param {object} args
 * @param {import("../sessions/store.mjs").SessionStore} args.sessionStore
 * @param {object} args.domainBridge        canonical PiDomainGateway bridge
 * @param {string} args.session_id
 * @param {string} args.project_scope_id
 * @param {string} args.idempotency_key
 * @param {string} args.binding
 * @param {Date}   [args.now]
 */
export async function createConversationSession({
  sessionStore,
  domainBridge,
  session_id: sessionId,
  project_scope_id: projectScopeId,
  idempotency_key: idempotencyKey,
  binding,
  now = new Date(),
} = {}) {
  if (!sessionStore || !domainBridge) throw new SessionServiceError("session_runtime_unavailable");
  assertIdentifier(sessionId, "session_identity_invalid");
  assertScope(projectScopeId, "scope_identity_invalid");
  assertIdentifier(idempotencyKey, "task_identity_invalid");
  if (typeof binding !== "string" || !binding) throw new SessionServiceError("binding_required");

  const scopeResult = await domainBridge.invoke("conversation.project_scope.select", {
    project_scope_id: projectScopeId,
    limit: 1,
    task_id: `pi_task_${sha256(idempotencyKey).slice(0, 24)}`,
    idempotency_key: `${idempotencyKey}:scope-validate`,
    binding,
  });
  if (!scopeResult?.ok) {
    const code = scopeResult?.error?.code ?? "domain_unavailable";
    throw new SessionServiceError(code);
  }

  const created_at = now.toISOString();
  const thread = emptyThreadView();
  const existing = sessionStore.get(sessionId);
  if (existing) {
    return {
      duplicate: true,
      ok: true,
      session: { session_id: sessionId, project_scope_id: projectScopeId, created_at: existing.created_at, status: "empty" },
      thread,
    };
  }
  sessionStore.create({ session_id: sessionId, now: created_at });
  sessionStore.append(
    sessionId,
    { kind: "session_metadata", project_scope_id: projectScopeId, status: "empty", created_at },
    { now: created_at },
  );
  return {
    duplicate: false,
    ok: true,
    session: { session_id: sessionId, project_scope_id: projectScopeId, created_at, status: "empty" },
    thread,
  };
}

export const CONVERSATION_SESSION_ROUTE = "/v1/conversations/session";
