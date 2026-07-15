---
phase: 16-google-light-structuring
plan: "01"
type: execution
wave: "1-3"
status: complete
requirements: []
note: "No formal REQUIREMENTS.md IDs mapped; scope from 16-01-PLAN + 15-NOTES-google-followup"
completed: 2026-07-12
verified: 2026-07-12
privacy_policy: service_and_category_content
audit_closeout: 2026-07-12
---

# Phase 16 Plan 01 Summary: Google Light Structuring

**Filled `normalized_events` (g| namespace) and privacy-filtered aggregate light assertions. Not dialogue knowledge units. Privacy policy locked to service + category/content after 15–16 audit.**

## Accomplishments

### Wave 1 — Normalized events
- Script: `integration/scripts/pipeline/build_google_normalized_events.py` (+ root shim).
- Production: **1,696 / 1,696** activities → `normalized_events`.
- Idempotent upsert; `event_id` prefix **`g|`** (dialogue remains **`cm|`**).

### Wave 2 — Light assertions + privacy
- Script: `integration/scripts/pipeline/build_google_light_assertions.py` (+ root shim).
- **Privacy policy (locked 2026-07-12):** restrict by **service and category/content**
  - Services: `Maps` (and service names containing `地图`)
  - Category/content substrings: `支付|金融|卡` and location intent `地图|地点|位置|导航`
  - Search/Gemini rows under `地图 / 地点 / 本地生活` **do not** form `interest_topic`
  - Restricted rows may still live in `normalized_events`
- Post-policy production write (2026-07-12):
  - activities scanned **1696**
  - restricted_skipped **39**
  - eligible **1657**
  - assertions **48** (`interest_topic` 6 / `frequent_service` 3 / `frequent_channel` 31 / `domain_affinity` 8)
  - removed prior `interest_topic = 地图 / 地点 / 本地生活` (8 Search/Gemini-sourced events)

### Wave 3 — Tests + docs
- `tests/test_google_light_structure.py` — restriction helpers, idempotency, privacy fixtures (Search/Gemini location rows), dry-run.
- Docs: `integration/docs/retrieval-ssot.md` §3.2; report `integration/analysis/ai_context/google_light_structure_report.json`.
- Status surface: `get_knowledge_status().google_structure` counts (status only; no full consumer query contract yet).

## Key files

- `integration/scripts/pipeline/build_google_normalized_events.py`
- `integration/scripts/pipeline/build_google_light_assertions.py`
- `tests/test_google_light_structure.py`
- `16-VERIFICATION.md`, `16-CONTEXT.md`
- Cross-phase audit: `../15-retrieval-ssot-governance/15-16-AUDIT.md`

## Explicit residuals (not blocking complete)

Tracked in `15-16-AUDIT.md` P1 / recommended **16-02** (requires approval):

- No source snapshot / run manifest, deletion propagation, or output checksum on `normalized_events`.
- Assertions replace current rows on write — no staged candidate, retained prior version, rollback target, or publish journal.
- Light assertions are status-count only; no controlled read-only consumer contract.

## Closeout notes (audit 2026-07-12)

- Implemented outside a fully standard GSD task-contract PLAN (wave outline only); this SUMMARY + VERIFICATION are the formal executor closeout artifacts.
- Full suite after privacy rewrite + discovery fix: **372 passed**.
- Production assertion rewrite authorized only after privacy-policy decision above (service + category/content).
