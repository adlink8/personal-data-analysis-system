---
phase: 17
status: passed
last_run: 2026-07-18
---

# Phase 17 UAT — Promotion Gate & Full Eval

## Final Result

The lifecycle-adjusted evidence-aware candidate passed policy v2 and completed
a reversible composite snapshot release UAT.

| Step | Actual | Pass? |
|---|---|---|
| Real evaluation | run `3a4b7f7b85e864b86031a79a0c017fa74c80e5b9908aa7fd73e765343fcc5d99`; 67 real Gold, 45 cross-turn | PASS |
| Five modes | raw, L1, exact L2-only 764/764, L1+L2, hybrid | PASS |
| Primary quality | Recall@5 +10.4478pp; CI low +4.4776pp | PASS |
| Cross-turn | +13.3333pp over L1; CI low +4.4444pp | PASS |
| Safety | candidate privacy/secret=0; citations=1.0; enforced no-answer gates pass | PASS |
| Candidate reconcile | 32,181/32,181; missing/orphan/duplicate=0 | PASS |
| Candidate activation | snapshot `ss_5d816a6bf3ebd0bce9463236`; Doctor 10/10 critical | PASS |
| Live query | corrected 8002 health unit returned at rank 1 | PASS |
| Rollback | prior snapshot `ss_1590353394c948b908a5d675`; Doctor 10/10 critical | PASS |
| Forward restore | final snapshot restored; pointer/version/snapshot parity clean | PASS |

## Final Authority

- Active collection: `knowledge_units_ir_4cd8af4ad_20260718054940`.
- Collection checksum:
  `9bb4592f157ecf6f51ef0a1cc997127a483f93df04c4daedf7c9426675f7842c`.
- Active snapshot: `ss_5d816a6bf3ebd0bce9463236`.
- Gate: `var/reports/analysis/evaluations/3a4b7f7b85e864b8/gate.json`.

The earlier FAIL runs remain immutable regression evidence. No thresholds were
changed to obtain PASS.
