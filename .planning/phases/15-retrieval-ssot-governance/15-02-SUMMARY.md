---
phase: 15-retrieval-ssot-governance
plan: "02"
status: complete
completed: 2026-07-12
---

# Phase 15-02 Summary: Holdout Quality + Layer Telemetry

## Delivered

1. **`search_knowledge_units` telemetry**  
   - Response always includes `allow_legacy_pad` and `telemetry`  
   - Layers: knowledge_unit, canonical_messages, conversation_turns, non_dialogue_raw, legacy_pad, legacy_personal_events  
   - Fields: attempted / hits / latency_ms; first_contributing_layer; pad_used; total_latency_ms  

2. **Independent holdout suite** (does not mutate frozen)  
   - `integration/evals/knowledge_units/holdout_15_02.synthetic.jsonl`  
   - Tags: google, paraphrase, no_answer, privacy  

3. **Eval runner**  
   - `integration/scripts/_tools/phase15_02_holdout_eval.py`  
   - Modes: layered pad on/off + legacy; offline-smoke for schema  

4. **legacy_pad decision (documented)**  
   - Default remains **true** (`transition_observable`)  
   - Flip criteria written in `retrieval-ssot.md` §2.2  
   - Emergency rollback: `PERSONAL_DATA_ALLOW_LEGACY_PAD=1` after future default flip  

5. **Tests**  
   - Empty query telemetry shape  
   - pad_used true/false  
   - holdout schema coverage  

## Commands

```powershell
python -m pytest tests/test_knowledge_search_contracts.py -q
python integration/scripts/_tools/phase15_02_holdout_eval.py --offline-smoke
python integration/scripts/_tools/phase15_02_holdout_eval.py  # live vectors
```
