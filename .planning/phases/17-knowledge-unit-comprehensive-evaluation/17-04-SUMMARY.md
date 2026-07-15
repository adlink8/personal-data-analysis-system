---
phase: 17
plan: "04"
status: complete
completed: 2026-07-13
---

# Plan 17-04 Summary: Promotion Gate + Entrypoint

## Delivered

| Item | Path |
|------|------|
| Policy | `eval_policy_v1.yaml` |
| Gate | `gate_knowledge_candidate.py` (fail-closed) |
| Promote hook | `promote_knowledge_index.py --require-eval-pass --eval-summary/--eval-gate` |
| Full CLI | `run_knowledge_eval.py --full --render --gate --dry-run` |
| UAT sheet | `17-UAT.md` |
| Tests | `test_knowledge_eval_gate.py` (incl. pure-KU regression not masked by Hybrid 1.0) |

## Gate behavior on current live summary

- **FAIL** (correct): privacy hits on mixed suite; primary Δpp 8.2 &lt; 10; L1→L1+L2 pure-KU regression flag path covered in unit tests.
- Active collection/checksum **never modified** by eval/gate.

## Human checkpoint residual

- Sandbox PASS→promote→rollback UAT table in `17-UAT.md` still for operator sign-off (`17-04-05`).
