# Phase 18 Validation

| Requirement | Gate |
|---|---|
| GOV-01/02 | file+directory+empty+excluded descendant+symlink/reparse coverage=100%；metadata completeness=100%；generated lineage=100%；unknown/conflict=0 |
| GOV-03/07 | zone/privacy/git/artifact policy tests；R3/R4 tracked violations=0 |
| GOV-04 | stable module README coverage=100%；leaf inventory coverage=100% |
| GOV-05/06 | path hits 与 shim baseline 不增加；每项债务有 owner/status/target |
| GOV-08/09 | lock/constraints、Python matrix、Node、pytest 与 governance gates |
| GOV-10 | ROADMAP/STATE/GSD/artifacts consistency |
| GOV-11 | dry-run migration manifest、shadow verification、rollback drill |
| GOV-12 | sanitized governance report build and trend smoke |

最终验证必须证明：没有读取/泄漏私人正文，没有未经确认的删除/移动，工作区既有改动未被覆盖。
