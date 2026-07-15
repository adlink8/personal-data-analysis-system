---
date: 2026-07-12
scope: Phase 15 Retrieval SSOT & Hybrid Governance; Phase 16 Google Light Structuring
status: closed_milestone_v1
verification_mode: code-and-artifact-audit
p0_closed_at: 2026-07-12
full_suite: "372 passed (pytest.ini testpaths=tests)"
privacy_policy: service_and_category_content
---

# Phase 15–16 GSD Audit Addendum

## Verified Current Delivery

| Area | Verified evidence |
|---|---|
| Phase 15 layered retrieval | CLI/REST backend exposes `fallback_policy=layered`; active KU is 30,012; frozen layered report records R@5=1.00. |
| Phase 15 evidence | live draft evidence rows 30,517/30,517 and resolvable canonical refs 13,579/13,579 in `15-RESEARCH.md`. |
| Phase 16 normalized events | root CLI dry-run reports 1,696 activities / expected normalized events 1,696. |
| Phase 16 light assertions | root CLI dry-run reports 49 assertions; `g|` namespace remains separate from `cm|`. |
| Targeted tests | `test_knowledge_search_contracts.py`, `test_knowledge_distribution_contracts.py`, `test_knowledge_evidence_backfill.py`, `test_google_light_structure.py`: 38 passed. |

## P0 Follow-ups Before Formal GSD Closeout

### A. Reproducible full-suite collection — **DONE**

Root `pytest.ini` sets `testpaths = tests` and excludes `_recycle/` (and other non-test trees). Bare `python -m pytest -q` no longer imports archive/shim modules or collides on dual `test_knowledge_unit_llm.py` basenames.

**Acceptance met:** fresh full suite **372 passed** (2026-07-12); collection has no import-file mismatch.

### B. GSD artifact/status consistency — **DONE**

Added `15-01-SUMMARY.md` and `16-01-SUMMARY.md`. Phase 16 remains a wave-outline PLAN with empty formal requirement IDs; SUMMARY/VERIFICATION document that it was implemented outside a full task-contract PLAN. ROADMAP/STATE/PROJECT aligned with complete status and this audit closeout.

### C. Location-category privacy decision — **DONE**

**Policy locked: service + category/content.**

- Restricted services: `Maps` / service names containing `地图`
- Restricted category/content substrings: payment `支付|金融|卡` **and** location `地图|地点|位置|导航`
- Search/Gemini activities under `地图 / 地点 / 本地生活` no longer form light assertions
- Restricted activities may still enter `normalized_events`
- Production rewrite after decision: assertions **48** (was 49); restricted_skipped **39** (was 31); location interest_topic removed
- Regression fixtures in `tests/test_google_light_structure.py`; policy text in `integration/docs/retrieval-ssot.md`

## P1 Quality and Lifecycle Follow-ups

### Phase 15 retrieval quality

- The frozen suite has 20 cases and zero Google-tagged queries.
- The reported R@5=1.00 is dominated by canonical-message lexical `LIKE`/snippet retrieval against gold evidence. It proves the current gold evidence can be found; it is not an independent semantic/generalization measurement.
- `allow_legacy_pad=true` by default means layered fallback can still append non-Google `personal_events` when earlier layers are short. This is an intentional transition behavior, but must be observable in production reporting.

**Recommended 15-02 scope:** independent holdout with Google, paraphrase, no-answer, and privacy cases; per-layer hit/fallback/latency telemetry; a documented default/rollout decision for legacy pad.

**15-02 status: DONE** — see `15-02-SUMMARY.md` (telemetry, holdout suite, legacy_pad transition_observable).

### Phase 16 Google lifecycle

- `normalized_events` uses idempotent upsert, but has no source snapshot/run manifest, deletion propagation, or output checksum.
- `google_light_assertions` replaces all current rows on write, with no staged candidate, retained prior version, rollback target, or publish journal.
- Light assertions are exposed in status counts only; there is no controlled query/consumer contract yet.

**Recommended 16-02 scope:** source snapshot + run manifest, staged assertions, privacy/reconcile gate, versioned publish/rollback, upstream deletion handling, and an explicit read-only consumer contract.

**16-02 status: DONE** — see `16-02-SUMMARY.md` (stable event_id, orphan delete, stage/gate/promote, RO list/get REST+MCP).  
Note: full SQLite file snapshot of google_data is deferred; run manifest + input/dataset hashes provide rebuild audit without duplicating the whole DB.

## Execution Order

1. ~~Test-discovery repair~~ **done**
2. ~~Resolve/document the Google location privacy policy~~ **done** (service + category/content; production rewrite applied)
3. ~~Add Phase 15/16 summaries and align ROADMAP/GSD status~~ **done**
4. Plan/execute 15-02 and 16-02 — **DONE** (user-authorized sequential execution 2026-07-12).

## Scope Fence

This audit does not authorize Google dialogue-KU extraction, writes to live AgentsView, deletion of historical raw/Chroma collections, or production assertion rewrites without the explicit privacy-policy decision above.
