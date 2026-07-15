---
phase: 18
plan: "05"
subsystem: repository-governance
tags: [dependencies, ci, preflight, reporting, security]
requires: [18-03, 18-04]
provides:
  - reproducible direct-dependency and Node lock contracts
  - one local/CI governance preflight entrypoint
  - aggregate-only governance history and HTML reporting
affects: [18-06]
key-files:
  created:
    - requirements-optional.txt
    - constraints.txt
    - governance/policies/dependencies.yaml
    - governance/baselines/preflight.json
    - integration/apps/personal_data_chatgpt/package-lock.json
    - integration/scripts/governance/check_dependencies.py
    - integration/scripts/governance/preflight.py
    - tests/test_governance_preflight.py
    - .github/workflows/ci.yml
    - docs/dependency-governance.md
  modified:
    - requirements.txt
    - requirements-dev.txt
    - integration/scripts/governance/render_governance_report.py
    - tests/test_governance_report.py
    - tests/test_agentsview_normalization.py
requirements-completed: [GOV-08, GOV-09, GOV-10, GOV-12]
completed: 2026-07-13
---

# Phase 18 Plan 05: Reproducibility and CI Gates

Python/Node dependency surfaces, repository governance checks and sanitized trend
reporting now form one repeatable local/CI contract. No global package was installed,
no private fixture was required, and no production/private data was modified.

## Delivery

- Split core, development and optional Python feature dependencies; added reviewed
  exact constraints for all declared direct packages and documented fresh-venv use.
- Added a lockfile for the dependency-free Node 20 app. Manifest name/version and
  lockfile version drift are now machine-checked.
- Added Windows CI for Python 3.12, Python 3.14 and Node 20 using the same preflight
  command and offline-default pytest discovery used locally.
- Added one preflight entrypoint covering inventory, privacy, path, shim, dependency,
  docs, planning, architecture, secret, artifact-lineage, retention and test-matrix
  gates. Every gate reports owner and policy.
- Added exact-ID baseline handling: only named non-P0 debt can be grandfathered;
  P0 findings are always blocking.
- Added aggregate SQLite history and HTML reporting. R3/R4 bodies, leaf paths and
  excerpts are never written to the registry or page.

## Verification

```text
python integration/scripts/governance/preflight.py --ci
PASS — 12/12 gates; privacy violations=0; P0=0

python -m pytest -q tests/test_governance_preflight.py tests/test_governance_report.py
PASS — 6 passed

python -m pytest -q tests/test_governance_*.py
PASS — 31 passed, 1 skipped (Windows symlink privilege fixture)

python -m pytest --collect-only -q
PASS — complete live test tree collected; archive/helper discovery excluded

python -m pytest -q
PASS — full repository live suite

npm test  (integration/apps/personal_data_chatgpt)
PASS — 10 passed

python integration/scripts/governance/render_governance_report.py --preflight ...
PASS — run_id=1, gates=12, aggregate HTML/SQLite generated under ignored runtime
```

## Environment evidence

`python -m pip check` on the existing machine-wide Python 3.14 interpreter reports
pre-existing FastAPI/Starlette, mcpo/FastAPI and SeleniumBase/BeautifulSoup conflicts,
plus an invalid residual torch distribution warning. Plan execution did not mutate or
repair that shared environment. Fresh installs are delegated to isolated CI/venv using
the checked contracts; this host debt is not treated as evidence against the contracts.

## Deviations

- A live fresh-environment install was not run locally because it would download and
  mutate dependencies. The plan's safety constraint was honored by validating all
  contracts without installation and defining isolated CI jobs that perform the install.
- The first secret scan correctly blocked on synthetic `sk-` fixtures. Those exact
  source lines now carry an explicit synthetic-fixture marker; the exception applies
  only to marked test lines, while P0 baseline exemption remains impossible.
- `git diff --check` reports whitespace debt in unrelated pre-existing dirty files.
  Those files were not reformatted or modified by this plan.

## Safety

- No move, delete, archive, production database write or private-body read occurred.
- No dependency installation, network call or Git commit was performed.
- Existing user and parallel-agent worktree changes were preserved.

## Self-Check: PASSED

All plan-listed artifacts exist, all deterministic acceptance gates pass, reporting
is aggregate-only, and Plan 18-06 may consume the preflight contract.
