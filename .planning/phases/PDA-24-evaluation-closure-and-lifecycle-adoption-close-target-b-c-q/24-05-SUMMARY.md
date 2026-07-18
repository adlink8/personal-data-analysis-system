---
phase: 24
plan: 05
status: complete
completed_at: 2026-07-18T17:30:00+08:00
commit: 0ed63ec
requirements: [QUAL-01, QUAL-02]
---

# Phase 24 Plan 05 Summary

## Delivered

- Candidate embeddings now combine canonical subject/question/answer with at
  most two resolved, eligible preceding user contexts.
- Secret-like spans are sealed before embedding; sidechain, system,
  ineligible-session and missing evidence is excluded.
- Stored Chroma documents remain canonical question/answer only. Evidence
  bodies are absent from documents and metadata.
- Candidate version IDs are unique per collection, preventing a rebuild from
  replacing the current Active version row.
- Evaluation can bind an explicit immutable draft candidate snapshot without
  changing serving authority.

## Real Candidate

- Collection: `knowledge_units_ir_4cd8af4ad_20260718051619`
- Version: `kiv_ir_4cd8af4ad_914e19183559`
- Candidate snapshot: `ss_a121823ef6f5a4fff38b1e87`
- Current units: 32,182
- Enriched units: 22,423
- Evidence snippets: 22,548
- Privacy-sealed spans: 15
- Embedding manifest: `5a88cc1bb96ce43a740d04460695bc0a31499c50b650ee5d36703bba9762b44d`
- Collection checksum: `ddcf6fc7e8fec159f032234264496972c182e25adc42894c7bb6a42ef1a0ad50`

## Verification

- Targeted implementation and serving tests: 23 passed.
- Candidate build: 32,182 indexed; missing/orphan/duplicate all zero.
- Full private run: `231fbdce8b421f2f44a546a5ef53d1b8624f7b5230c9cd2aa7408d3d650b3f5`.
- Gate: PASS, no errors, Active unchanged.
- Overall Recall@5 gain: +10.45pp; bootstrap CI lower bound +4.48pp.
- Real cross-turn gain: +13.33pp over L1; CI lower bound +4.44pp.
- L1+L2 privacy/secret hits: 0; no-answer false-positive rate: 0.

## Remaining Phase 24 Work

QUAL-01 and QUAL-02 now have direct PASS evidence. LIFE-01 and LIFE-02 remain
open until a bounded real reviewed lifecycle cohort is applied and its
correction/supersede/conflict/restore event ledger is verified.
