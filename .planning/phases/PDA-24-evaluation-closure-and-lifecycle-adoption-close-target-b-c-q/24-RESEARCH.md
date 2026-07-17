---
phase: 24
researched: 2026-07-17
status: complete
---

# Phase 24 Research

## Existing Assets to Reuse

| Concern | Existing implementation | Gap |
|---|---|---|
| Five-mode eval | `evaluation/run_knowledge_eval.py`, retrieval adapters, scorer v2 | Not bound to composite snapshot strongly enough; current live verdict FAIL |
| Policy | `eval_policy_v2.yaml`, candidate safety scope | Correct thresholds; missing evidence-aware abstention and human coverage |
| Answer eval | deterministic extractive answer + citation scoring | Expected-abstain can short-circuit generation; support decision must be derived from evidence, not the label |
| Abstention | private 58-case dev set + threshold sweep | No feasible score threshold; needs multi-signal support decision |
| Gold/review | private suite and 50-row grounded packet | Human provenance/import and coverage construction workflow absent |
| Lifecycle | `reconcile_knowledge_lifecycle.py`, `pk-ku history` | Heuristic writes mutate rows directly; no immutable event ledger/review manifest/correction type |
| Serving | Phase 23 immutable snapshot and rollback | Eval/lifecycle artifacts need snapshot membership and rollback evidence |

## Recommended Architecture

### Evidence support decision

Introduce a deterministic `EvidenceSupportDecision` with independent signals:

- typed evidence resolution status and eligibility;
- current lifecycle and snapshot membership;
- lexical/entity overlap between query, KU question/subject/answer and resolved evidence metadata;
- citation availability and provenance class;
- explicit privacy/secret vetoes;
- calibrated confidence only as a secondary feature.

The decision returns `supported`, `unsupported`, or `uncertain`, reason codes and evidence IDs. `unsupported/uncertain` abstain unless a lower layer supplies independently supported evidence. Evaluation records every reason code. Development calibration selects a policy on the private dev split only; frozen results remain untouched.

### Human evidence workflow

Use private JSONL packets with metadata-only tracked schemas:

1. deterministic candidate selection from resolvable evidence;
2. blind review packet under `var/runtime/private_evals`;
3. explicit label import requiring reviewer ID, timestamp and allowed enums;
4. immutable label-set checksum and audit report;
5. dataset builder includes only reviewed rows as real Gold.

Judge calibration follows the same pattern. Paid generation is optional and separately authorized; cached answers can be labeled without network calls.

### Lifecycle adoption

Add append-only lifecycle events and review manifests. A lifecycle action is valid only when:

- source/target units and current versions exist;
- evidence refs resolve and are eligible;
- action type is explicit (`supersede`, `conflict`, `correct`, `restore`);
- reviewer/actor, reason and before state are recorded;
- the action manifest checksum matches at apply time;
- apply occurs in one FK-enabled transaction and emits a rollback event.

The current table remains the materialized state; the event ledger is the audit authority. Candidate vector rebuild filters current-only and is published through a new serving snapshot.

## Risks and Controls

| Risk | Control |
|---|---|
| Fabricated human completion | Human fields cannot be auto-populated; validation distinguishes agent/deterministic/human provenance |
| Frozen-set overfitting | Calibrate only on private dev; policy and frozen run hashes immutable |
| Privacy leak in reports | Tracked artifacts contain schemas/counts/hashes only; payloads stay private |
| Broad lifecycle corruption | Review manifest + bounded action count + before/after hash + transaction + rollback |
| Active regression | Candidate snapshot, genuine gate PASS, atomic activation; FAIL leaves active unchanged |
| Snapshot mixing | Eval manifest stores snapshot ID/hash and per-role versions; mismatch is a critical gate |

## Planning Conclusion

Four plans are required: evidence-aware relevance, private human-evidence workflow, governed lifecycle adoption, and final evaluation/UAT closure. Plans 01 and 02 can run in parallel after the shared snapshot contract; lifecycle adoption depends on the review/event infrastructure; final acceptance depends on all prior outputs and genuine human evidence.
