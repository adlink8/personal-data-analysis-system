# Phase 22 — Context

**Created:** 2026-07-16  
**Milestone:** v1.1 → product hardening (toward product-grade daily use)  
**Depends on:** Phase 14–16, 21; post-hoc product work (pk-sync/pk-ku, canary LLM labels)

## Problem statement

Daily KU path today is **append-mostly**:

- `pk-ku prepare --extract-new-only` (default) queues **new** evidence only.
- Modified claims and subject-level conflicts are **not productized**.
- `lifecycle` / `supersedes_id` exist in schema with **sparse use**.
- User requirement: **never hard-delete personal history** — keep a **growth line**; retrieval should prefer **current** without erasing the past.
- Retrieval already has layered fallback (KU → dialogue → Google); lifecycle reconcile is the missing **middle layer**.

## Product decisions locked (from operator conversation 2026-07-16)

| ID | Decision |
|----|----------|
| D-22-01 | No physical DELETE of knowledge_units / canonical rows for “cleanup”. |
| D-22-02 | Growth line = multi-version units by subject + time; `lifecycle` marks current vs superseded. |
| D-22-03 | Retrieval default surface = `lifecycle=current` only; archive/growth queries are explicit. |
| D-22-04 | Policy changes via **CLI flags**, not code edits for daily ops. |
| D-22-05 | Promote remains fail-closed on eval; canary labels may be human or LLM-assisted. |
| D-22-06 | Bidirectional layering principle: top-down route + mandatory leaf fallback; scores sort, not truth. |

## Non-goals

- Novel-style Chapter/Arc/Global story memory as Knowledge SSOT.
- Promoting memory experiment tables to knowledge SSOT.
- Auto-delete of archive/quarantine or domains facades before 2026-08-13 window.
- Replacing Phase 17 human gold/judge work (tracks in parallel).

## Inputs already available

- Product CLI: `pk-sync`, `pk-ku` (inspect→…→canary/label-with-llm→promote→watermark)
- Candidate index example: `knowledge_units_ir_4cd8af4ad_20260716020508` (canary labeled 30/30, strict FAIL on 1 wrong)
- Active still: `knowledge_units_205bff9560b9_20260712142938`
- Docs: `docs/runbooks/ku-incremental.md`, gap audit under `.planning/cleanup/`
