# Phase 58 Validation Strategy

| Behavior | Requirement | Command |
|---|---|---|
| Manifest/selection/state machine | PSKILL-02 | `npm test --prefix apps/personal_intelligence_kernel -- --test-name-pattern=skill-engine` |
| Personal intelligence Skills | PSKILL-01, PSKILL-03 | `python -m pytest tests/eval/test_pi_personal_skills.py -q` |
| Data maintenance Skills | PSKILL-01, PSKILL-03 | `python -m pytest tests/eval/test_pi_data_skills.py -q` |
| Replay/fault/forbidden sequence | PSKILL-02, PSKILL-03 | `python -m pytest tests/integration/test_pi_skill_recovery.py -q` |
