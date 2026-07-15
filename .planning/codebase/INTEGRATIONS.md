# External Integrations and Data Lifecycle

**Scope:** external systems, service boundaries, credentials, privacy, and artifact lineage for Phase 18.  
**Inspection rule:** no private conversation, event, or evaluation body text was opened.

## Integration registry

| Integration | Direction | Current boundary | Data/privacy | Required governance |
|---|---|---|---|---|
| AgentsView | inbound | `%USERPROFILE%/.agentsview/sessions.db` -> read-only snapshot -> normalized/canonical SQLite | R4 conversations, tool traces, possible secrets | Live DB must use SQLite URI `mode=ro` + `query_only`; never mutate it. Record schema hash, snapshot hash, watermark, redaction counts, and source availability. |
| Google Takeout / structured Google | inbound | `Google/raw` -> structuring scripts -> `Google/structured/db/google_data.sqlite` -> normalized events/light assertions | R4 raw activity; R3 inferred interests | Raw stays ignored; enforce category/service privacy filters; manifest export date, service, parser version, rejected rows, and deletion propagation. |
| Archived GPT export | inbound/legacy | soft-archived source path -> compatible import pipeline | R4 | Mark legacy and non-live; source absence must be explicit, not silently treated as empty. Retention/deletion must cover archive copies. |
| Local Chroma | internal service | REST API v2; local vector collections, KU port 8001 | R3/R4 embeddings and documents | Loopback only; immutable generation names, manifest, active pointer, candidate gate, rollback, retention, orphan cleanup report. |
| Local embedding model | local compute | sentence-transformers, BGE small Chinese, offline | R3/R4 text remains local | Configurable path and device; record model ID/digest/dimension; prohibit accidental online model resolution. |
| Vertex AI Gemini | outbound LLM | extraction code calls Google model endpoint | R4 evidence may be transmitted | Explicit opt-in/run mode, approved region/project, data-minimizing prompt, no secrets, provider/model/prompt/schema audit, retry/cost/rate limits. Confirm provider retention policy outside code before production runs. |
| OpenAI-compatible LLM | outbound LLM | `OPENAI_BASE_URL`, `OPENAI_API_KEY`/`MEM0_API_KEY`, selectable model | R3/R4 depending on job | Endpoint allowlist; never log key/base auth; label third-party compatible endpoints accurately; record provider endpoint class and model, not credential. |
| REST API | outbound local surface | stdlib HTTP, default `127.0.0.1:8000` | exposes personal search/evidence | Loopback default; API has no built-in auth, so external bind is prohibited absent auth + TLS proxy + explicit configuration. Apply bounds, audit metadata, and response redaction. |
| stdio MCP | outbound local surface | MCP SDK tools share `unified_search` backend | exposes personal search/evidence | Read-only tools only; enforce same limits/privacy contract as CLI/REST; mutation remains offline admin. |
| ChatGPT Apps MCP adapter | outbound bridge | Node server `127.0.0.1:8789`, proxies local REST; widgets | personal records may reach client/UI | Loopback default, explicit tunnel runbook, strict origin/CSP, no private widget fixtures in Git, response-size limits, export safeguards. |
| Streamlit dashboard | local UI | local process over integrated SQLite | R3/R4 display | Loopback only, no public deployment without auth; screenshots/exports inherit displayed data's privacy class. |
| Import drop zone | inbound filesystem | `imports/incoming` -> batches/duplicate audit/quarantine | R4 names and payloads | Atomic intake, MIME/size validation, duplicate hash, quarantine, manifest, source consent, and retention. Never execute imported code. |

## End-to-end lifecycle contract

```text
external/live source
  -> read-only probe + schema hash
  -> immutable local snapshot
  -> staging normalization
  -> validation/privacy gate
  -> atomic canonical publish
  -> candidate knowledge/vector build
  -> comprehensive evaluation + canary
  -> active pointer promotion
  -> read-only distribution
  -> retention review / approved rollback or disposal
```

Each arrow must produce a run manifest. Minimum manifest fields: `run_id`, timestamps, producer version/commit, source locator class (not secret path content), source schema/content hashes, input row counts, output hashes/counts, rejects/redactions, privacy class, configuration/model/prompt/schema versions, validation result, and publish/rollback journal entry.

## Source-of-truth rules

- Dialogue evidence: AgentsView live source is external and read-only; the canonical dialogue snapshot is the internal reproducible evidence surface for downstream jobs.
- Personal knowledge: canonical knowledge-unit tables plus the current active vector generation. LLM summaries and AgentsView insights are not allowed to override evidence.
- Google activity: normalized Google events preserve provenance; light assertions are derived and must remain traceable to eligible aggregates.
- Retrieval: `integration/scripts/vector/unified_search.py` is the backend shared by CLI, REST, MCP, and Apps. Compatibility shims must delegate and carry a deprecation status.
- Evaluation: synthetic tracked suites and private gold suites are distinct. Reports must state dataset identity, size, privacy class, system variants, and uncertainty; no selective metric publication.

## Credential and network policy

- Credentials are environment/credential-store inputs only. They must not appear in source, manifests, logs, reports, CLI history examples, or exception bodies.
- Maintain an endpoint allowlist for outbound LLM calls. `OPENAI_BASE_URL` is powerful enough to redirect R4 data and therefore needs validation and an explicit live-run flag.
- All local services bind `127.0.0.1` by default. A non-loopback bind is a deployment event requiring authentication, TLS, CORS/origin policy, threat review, and an operator-visible warning.
- Timeouts, bounded retries with jitter, rate/cost caps, and resumable checkpoints are required for live LLM jobs. Cached provider responses inherit R4 unless irreversibly sanitized.
- Network-free tests must be the default. Live integration tests are opt-in, separately marked, and cannot use private fixtures unless explicitly authorized.

## Artifact-specific lifecycle

### SQLite / DuckDB

- Open external live sources read-only. Snapshot before multi-step reads when WAL consistency matters.
- Write to a sibling staging file; run schema, FK, CHECK, count, provenance, and integrity checks; publish atomically.
- Maintain migration/version metadata and backup before destructive schema operations.
- WAL/SHM files are runtime artifacts. Detect stale sidecars; never treat copying only the main DB as a valid hot backup.
- Rollback must restore both data and the authoritative pointer/manifest, then rerun smoke validation.

### Vector generations

- A collection is immutable after candidate completion.
- Manifest includes embedding model digest/dimension, source DB hash/schema version, unit filter, count, Chroma API version, and build run.
- Compare candidate vs current on the same frozen/private suites. Failed gates leave active unchanged.
- Keep a bounded number of known-good generations; report orphans before an approved cleanup.

### Reports and visualizations

- Private reports live under ignored analysis/runtime zones. A separately sanitized publication process may emit source-controlled documentation.
- Every chart includes metric definition, sample size, system variant, baseline, absolute percentage-point delta, relative delta where meaningful, confidence interval, dataset/run IDs, and generation timestamp.
- HTML/PNG/SVG inherit the highest privacy class of embedded labels, tooltips, links, data, and metadata. Visual masking alone is not anonymization.
- Report regeneration must be deterministic from a registry entry; manually edited generated HTML is prohibited.

### Logs and runtime state

- Log structured operational metadata, never message/evidence bodies or credentials.
- Define rotation/TTL; separate audit journals from disposable debug logs.
- PID, temporary, staging, retry-cache, and checkpoint files have owners and cleanup-on-success behavior; crash recovery is tested.

## Gitignore assessment

The current ignore policy correctly keeps broad private/generated zones and binary/data formats out of Git, and explicitly allows public synthetic eval/config/docs and app manifests. Two controls are still required:

1. A governance test must prove every tracked exception is intended and contains no private material. Broad negations such as `integration/apps/**/*.html` need a bounded source-directory policy so generated exports cannot become tracked accidentally.
2. A `git check-ignore` policy test must cover representative R1-R4 paths, private evals, database sidecars, logs, report formats, app source assets, and public synthetic fixtures.

Do not use `.gitignore` as the only privacy control: ignored files can still be copied, served, packaged, uploaded, backed up, or embedded in reports.

## Per-file integration governance fields

In addition to the repository inventory fields defined in `STACK.md`, files crossing an integration boundary require:

| Field | Purpose |
|---|---|
| `integration_id` / `direction` | Stable registry key; inbound, outbound, bidirectional, or internal service. |
| `external_owner` / `contract_version` | System of record and expected API/schema version. |
| `locator_kind` | Config key/path class; never store credentials or unnecessary absolute user paths. |
| `data_categories` / `privacy_class` | Conversation, activity, inference, embedding, metric, credential metadata. |
| `legal_or_consent_basis` | Why ingestion/transmission is allowed; manual confirmation for new outbound destinations. |
| `read_write_mode` | read-only source, snapshot, staging write, atomic publish, append-only journal. |
| `watermark` / `deletion_lineage` | Incremental cursor and how source deletion reaches all derivatives. |
| `provider_model_prompt` | Versions for LLM-derived artifacts. |
| `network_policy` | Endpoint allowlist, locality, auth, TLS, timeout, retries, cost/rate cap. |
| `failure_policy` | fail closed, retry, quarantine, retain old active, or manual intervention. |
| `observability_policy` | Permitted counters/hashes and prohibited content. |
| `rollback_procedure` / `last_drill` | Reversal path and evidence of a successful rehearsal. |

## Phase 18 acceptance checks for integrations

- Enumerate every inbound/outbound integration and verify its effective policy reaches every deepest-level file it owns.
- Prove AgentsView cannot be opened writable by adapters or pipelines.
- Prove outbound LLM work cannot start without explicit live mode, credentials, approved endpoint, and audit manifest.
- Prove non-loopback REST/Apps/UI startup fails or emits a blocking security requirement without auth configuration.
- Prove candidate gate failure leaves database/vector active pointers unchanged; prove rollback by sandbox drill.
- Prove private inputs, databases, vectors, reports, widget fixtures, and logs are neither tracked nor included in distributable artifacts.
- Generate a sanitized architecture/report dashboard from metadata only: counts, sizes, ages, privacy classes, owners, lineage coverage, orphan count, and retention violations.
