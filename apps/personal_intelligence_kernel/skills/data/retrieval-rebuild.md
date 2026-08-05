# retrieval.rebuild

Entry: rebuild an isolated retrieval generation.
Steps: inspect source, build a new generation, reconcile missing/orphan/duplicate counts, evaluate frozen policy, and prepare a release preview.
Stop: nonzero reconcile, failed evaluation, fingerprint drift, or budget exhaustion.
Checkpoint: active generation is never switched by this Skill.
