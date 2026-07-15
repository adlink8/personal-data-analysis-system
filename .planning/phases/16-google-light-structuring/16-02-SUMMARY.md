---
phase: 16-google-light-structuring
plan: "02"
status: complete
completed: 2026-07-12
privacy_policy: service_and_category_v1
---

# Phase 16-02 Summary: Lifecycle + Read-only Consumer

## Delivered

1. **Normalized events**
   - Stable `event_id = g|sha256(activity|{id})[:24]`
   - Orphan delete when activity removed
   - Run manifest in `google_structure_runs` + promote log
   - input_hash / dataset_hash on stats

2. **Light assertions lifecycle**
   - Composite PK `(assertion_id, run_id)` so staging coexists with current
   - Write path: stage → privacy/reconcile gate → promote (old current → superseded)
   - Gate fail → abort, previous current untouched
   - `--rollback` restores previous run
   - Active pointer: `Google/structured/db/google_structure_active_run.txt`

3. **Read-only consumer contract**
   - Backend: `list_google_light_assertions` / `get_google_light_assertion`
   - REST: `GET /google/assertions`, `GET /google/assertions/<id>`
   - MCP: `list_google_assertions`, `get_google_assertion`
   - Envelope: `kind=google_light_assertion`, `not_knowledge_unit=true`

4. **Tests**
   - Orphan deletion + stable id under title edit
   - Stage/promote + consumer list/get
   - Existing privacy fixtures retained

## Commands

```powershell
python integration/scripts/build_google_normalized_events.py --write
python integration/scripts/build_google_light_assertions.py --write
python integration/scripts/build_google_light_assertions.py --rollback
python -m pytest tests/test_google_light_structure.py -q
```
