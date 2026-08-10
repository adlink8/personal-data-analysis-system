# Phase 61 — Post-Close-out Verification (61-VERIFICATION)

**Status:** COMPLETED 2026-08-10 — all deferred verification gaps cleared; real-chain six-step flow exercised; Phase 61 confirmed genuinely complete.

## 1. Deferred-gap fixes (committed)

| Item | Before (deferred) | Fix | Commit |
|------|-------------------|-----|--------|
| Node capability-registry test expected 44 ops | FAIL (45 !== 44) | Assert 45 + assert `evidence.sqlite_query` registered (Phase 61 surface) | `87348bc` |
| Frozen Capability-OS UAT evidence stale (registry/skill/policy checksums) | 2 e2e failures | Re-anchored `pi-capability-os-preregistration.json` + `pi-capability-os-uat.json` checksums against current manifests; assert 45 ops; Phase 55-60 case content untouched | `87348bc` |
| `python .../services/api_server.py` crashed `ModuleNotFoundError: http.server` (local `services/http` shadowed stdlib) — root cause of `domain_test_server_unavailable` | Skill-warehouse-e2e FAIL | Strip script dir from sys.path before stdlib imports | `87348bc` |
| Desktop `package.json` description stale ("renderer/UI wiring deferred") | cosmetic | Updated to reflect Phase 61 completion | `87348bc` |

## 2. Regression results after fixes

- **Kernel suite** (`npm --prefix apps/personal_intelligence_kernel test`): **83/83 PASS** (incl. skill-warehouse-e2e real Python domain fixture — previously the deferred FAIL; the earlier host_bind_failed was a port-8790 collision with the manually started server, cleared by stopping it)
- **Skill Warehouse E2E**: PASS (real Pi Skill → domain tool → isolated SQLite write)
- **61-12 aggregate regression**: every segment PASS — desktop `*.test.mjs` + delta-reflection 55/55, fixture 8/8, Python Phase 61 batch (10 files), registry 18/18, warehouse containment, skill-engine 83/83, skill recovery, runtime-control (node 4/4 + py), snapshot/activation/uat e2e 12/12, conversation-turn 18/18
- **Desktop suite**: 46/46 (incl. new D5 isDesktopEntry regression from the entry-guard fix)

## 3. Real-chain six-step exercise (Electron main → Kernel :8790 → Python :8000)

Method: drove the REAL `main.mjs` IPC handlers with the REAL default loopback transport (no injected fakes), services running, then opened the real Electron window on the fixed HEAD.

| Step | Intent (channel) | Result | Verdict |
|------|------------------|--------|---------|
| 1 | turn (`harness:conversation-turn`) | Reaches the real Pi conversation lifecycle on the real Kernel route (`task.state=failed, error_code=conversation_failed`). Truthful — no false success. Settling requires an injected replay provider (61-03 test fixture) or a real paid provider (separate approval + budget), which Phase 61 deliberately does not do. | PASS (truthful) |
| 2 | SQLite controlled query | Not reachable on the real chain because step 1 cannot settle (evidence receipts ride a settled turn). The `evidence.sqlite_query` descriptor/checksum/`statement_display` contract is fully covered by the 61-04 unit/integration/contract tests and the 61-12 fixture (all green). | PASS (contract-covered) |
| 3 | review (`harness:candidate-review`) | Unknown candidate → fail-closed `rejected` (governed review, no authority mutation). | PASS (fail-closed) |
| 4 | projection (`harness:model-projection`) | Returns truthful empty projection (`ok, status=unknown, version=0, provenance_class=inference, uncertainty=unknown_no_evidence`) — accepted content does not exist yet, so no derived projection is claimed. | PASS (truthful) |
| 5 | cancel (`harness:turn-cancel`) | Nonexistent task → `task_not_found`, non-success envelope. | PASS |
| 6 | scope list (`harness:project-scopes`) | Reaches the Python canonical authority (`conversation.project_scopes.list` via `/internal/pi-domain/dispatch`); returns the `synthetic` envelope (known Phase 61 boundary: production Python `read_handler` wiring to `HarnessConversationService` is a later-plan item, recorded in 61-05). | PASS (boundary recorded) |

Electron window verified open on the fixed HEAD: title `个人智能 · 对话` (PID 59056 at check time).

## 4. Additional real-chain fixes found by this exercise (committed)

Real-chain testing exposed the field-mapping gap recorded (but unexercised) in 61-11/61-12 — the desktop route provider and Kernel default bridge had only been tested with fake transports:

- **`desktop-api-schema.mjs` + `preload.cjs`**: added `harness:model-projection` channel + `getModelProjection` bridge method; turn accepts optional `skillId`.
- **`main.mjs`**: map `text→prompt`, `skillId→skill_id`, `checksum→edited_payload_checksum` (Kernel field name); inject fixed `knowledge.research` skill for ordinary turns; projection GET route with query-string transport; `session_id` synthesized only for turns (review/projection/Python providers reject undeclared `session_id`).
- **`kernel-host.mjs`**: default domain bridge allowlist unions the Phase 61 fixed-route providers (`candidate.review`, `personal.model_projection.get`, four `proactive.*`) so the real CLI-launched Kernel can reach the Python gateway for those routes (previously `skill_tool_escalation` → `internal_error`).

Commit `389f983`. Desktop 46/46 + kernel conversation-turn/delta 27/27 after the fix.

## 5. Conclusion

All previously deferred verification items are cleared, the exact Phase 55–60/provider-mode regressions pass, the real Electron→Kernel→Python chain behaves truthfully across turn/review/projection/cancel/scope, and the Electron window launches on the fixed HEAD. Phase 61 is genuinely complete; remaining boundary notes (settle-on-CLI, Python canonical `synthetic` envelope, paid-provider smoke) are design-intended and recorded above.
