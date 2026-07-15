# Phase 15-02 VERIFICATION — Live Holdout Report

**Date:** 2026-07-12  
**Runner:** `python integration/scripts/_tools/phase15_02_holdout_eval.py`  
**Artifact:** `integration/analysis/ai_context/phase15_02_holdout_eval.json`  
**Active KU:** `knowledge_units_run_76c6259e_20260712062418`

## Executive summary

Live layered retrieval was evaluated on the independent 8-case holdout (google / paraphrase / no_answer / privacy). **Pad was never used** (`pad_used_rate=0.0`) for pad-on or pad-off. Scored Google title matches hit R@5=1.0, but **all queries first contributed from `knowledge_unit`**, and no-answer cases show **abstain false-positives** (top1 knowledge_unit). Do **not** flip `allow_legacy_pad` default yet based on pad alone — pad is idle on this suite; generalization gaps are elsewhere.

## Modes (live)

| Mode | n | scored | R@5 | pad_used_rate | abstain_fp |
|---|---:|---:|---:|---:|---:|
| layered pad on | 8 | 2 | **1.00** | **0.00** | **2** |
| layered pad off | 8 | 2 | **1.00** | **0.00** | **2** |
| legacy pad on | 8 | 2 | **1.00** | **0.00** | **2** |

## By suite_tag (layered pad on)

| Tag | n | hits | R@5 | notes |
|---|---:|---:|---:|---|
| google | 2 | 2 | 1.00 | Scored via title substrings; first layer still **knowledge_unit** (not non_dialogue_raw) |
| paraphrase | 2 | 0 | 0.00 | No gold_refs; informational only |
| no_answer | 2 | — | — | **abstain_fp=2** (route=knowledge + top retrieval_unit=knowledge_unit) |
| privacy | 2 | 0 | 0.00 | No forbidden subject leakage recorded |

## Layer telemetry (observed)

- `first_contributing_layer` counts: **knowledge_unit = 8 / 8** for all modes.
- `non_dialogue_raw` / `legacy_pad` often **not attempted** because KU already filled top slots.
- Example latency (google-001, pad on): KU ~529ms, cm ~199ms, turns ~275ms; total wall ~24s (includes model load).

## legacy_pad decision (from live data)

| Criterion | Observation | Status |
|---|---|---|
| pad_used_rate low | **0.0** on holdout | Met on this suite |
| google+paraphrase pad-off within −5pp of pad-on | Both R@5=1.0 on scored subset | Met (tiny n) |
| Telemetry shipped | Yes (`telemetry` on every search) | Met |
| Ready to flip default → false | **No** — suite too small; no-answer FP still open; pad idle ≠ pad safe to remove | **Keep default true** (`transition_observable`) |

## Residual / next quality work (not blocking 15-02)

1. Enrich holdout with real gold refs for paraphrase + Google PE/`g|` IDs.
2. Tighten no-answer scoring / abstain policy when KU returns weak hits.
3. Optional: force short KU slots for Google-intent queries to exercise non_dialogue_raw.

## Sign-off

- [x] Live holdout JSON written  
- [x] Pad observability confirmed  
- [x] Default pad remains **true** with documented rationale  
