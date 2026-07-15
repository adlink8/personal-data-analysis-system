# Graph domain
## Responsibility
Evidence-backed entity and relation candidates, judgments and graph queries.
## Boundaries
Uses stable IDs; cannot read raw source paths or depend on services.
## Entry points
Graph build, judge and query modules in this package.
## I/O and privacy
Derived R3 relations retain evidence references; generated graphs stay ignored.
## Tests
Graph candidate, judgment and contract tests under `tests/`.
## Ownership
Owner: graph. Status: supported.

