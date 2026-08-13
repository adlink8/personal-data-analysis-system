"""Phase 62-07 Task 1: metadata-only per-family adapter fidelity evaluator.

RED/GREEN integration tests for
:mod:`personal_knowledge.evaluation.conversation.adapter_fidelity`:

  - per-family metrics: discovered sessions, native artifacts available,
    captured artifacts, adapted sessions/events/relations, explicit
    unknown/redacted/unavailable dispositions, source-ref resolution sample,
    replay digest stability, compatibility projection parity and view coverage
  - a read-only live-metadata smoke mode that NEVER returns bodies (D-09/D-31)
  - activation gates: 17/17 families have a capability result; every
    native-available session is captured or explicitly blocked; no unresolved
    provenance; forbidden-source access zero; replay digest stable; current
    consumers pass; partial ChatGPT/Cursor limitations disclosed

All tests run against temporary sources and read-only metadata probes. No live
database, no var/, no network, no provider calls (D-31).
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path

from personal_knowledge.adapters.conversation_sources.registry import known_families
from personal_knowledge.application.run_pipeline import shadow_conversation_generation

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "conversation_sources"

# fixture body text that must never reach any metadata-only output
_BODY_MARKER = "Here is the summary."


def _make_source(tmp_path: Path, *files: tuple[str, str]) -> Path:
    """files: (output_name, fixture_name) pairs; defaults to one codex file."""
    src = tmp_path / "sources"
    src.mkdir(exist_ok=True)
    if not files:
        files = (("codex.jsonl", "codex_agent_sessions.jsonl"),)
    for output_name, fixture_name in files:
        shutil.copy2(FIXTURES / fixture_name, src / output_name)
    return src


def _shadow(tmp_path: Path, src: Path | None = None) -> tuple[dict, Path, Path, Path]:
    if src is None:
        src = _make_source(tmp_path)
    db = tmp_path / "v2.sqlite"
    store = tmp_path / "artifacts"
    report_path = tmp_path / "report.json"
    report = shadow_conversation_generation(
        source_root=src, db=db, artifact_store=store, report_path=report_path,
    )
    return report, db, store, src


def _evaluate(report: dict, db: Path, store: Path, inventory: dict | None = None):
    from personal_knowledge.evaluation.conversation.adapter_fidelity import (
        evaluate_adapter_fidelity,
    )

    return evaluate_adapter_fidelity(
        report, generation_db=db, artifact_store=store, inventory=inventory
    )


# ---------------------------------------------------------------- evaluator

def test_evaluator_reports_all_17_families_with_capability_result(tmp_path):
    report, db, store, _src = _shadow(tmp_path)
    evaluated = _evaluate(report, db, store)
    names = set(evaluated.families)
    assert names == set(known_families())  # 17/17 explicit results
    for name in known_families():
        entry = evaluated.families[name]
        assert entry.status in ("full", "partial", "blocked", "no_source")
        assert entry.capability["adapter_version"]  # versioned capability
        if name == "codex":
            assert entry.status == "full"


def test_per_family_metrics_include_discovery_capture_adapt_counts(tmp_path):
    report, db, store, _src = _shadow(tmp_path)
    evaluated = _evaluate(report, db, store, inventory={"codex": 1})
    codex = evaluated.families["codex"]
    assert codex.discovered_sessions == 1
    assert codex.captured_artifacts == 1
    assert codex.captured_sessions >= 1
    assert codex.adapted_events >= 1
    assert codex.adapted_relations >= 1
    assert codex.dataset_digest  # deterministic artifact/generation digest


def test_disposition_counts_reflect_explicit_field_decisions(tmp_path):
    """D-07/D-13: dispositions are counted explicitly by kind and never hidden."""
    report, db, store, _src = _shadow(tmp_path)
    evaluated = _evaluate(report, db, store, inventory={"codex": 1})
    codex = evaluated.families["codex"]
    assert isinstance(codex.dispositions, dict)
    assert set(codex.dispositions) <= {
        "mapped", "preserved_by_reference", "redacted",
        "unavailable", "unsupported",
    }
    assert 0.0 <= codex.disposition_coverage <= 1.0
    # adapters without explicit dispositions report coverage 0, not a lie
    assert codex.disposition_coverage == 0.0


def test_synthetic_dispositions_are_counted_explicitly(tmp_path):
    """A generation with redacted/unavailable dispositions counts them."""
    from personal_knowledge.core.conversation_events import (
        AdaptedSession,
        EventKind,
        FidelityDimension,
        FidelityLevel,
        FieldDisposition,
        FieldDispositionRecord,
        FidelityProfile,
        Provenance,
        TypedEvent,
        make_event_id,
    )
    from personal_knowledge.adapters.conversation_sources.contracts import (
        SourceArtifact,
    )
    from personal_knowledge.application.conversation.event_repository import (
        GenerationInput,
    )
    from personal_knowledge.application.conversation.event_generations import (
        GenerationLifecycle,
    )
    from personal_knowledge.application.conversation.compatibility_projection import (
        compute_projection,
    )

    db = tmp_path / "synthetic.sqlite"
    artifact = SourceArtifact(
        artifact_id="art-syn", family="pi", source_kind="file",
        content_hash="h" * 64, capture_method="sha256",
        relative_path="pi.jsonl", byte_size=10,
    )
    prov = Provenance(
        artifact_id="art-syn", artifact_hash="h" * 64,
        native_locator="pi.jsonl#0", native_session_id="s1",
        native_event_id="ev1", contract_version="1",
    )
    session = AdaptedSession(
        session_id="s1", provenance=prov, fidelity=FidelityProfile.complete(),
        native_session_id="s1",
    )
    event = TypedEvent(
        event_id=make_event_id(
            "pi", "art-syn", "1", "ev1", kind=EventKind.COMPACTION_SUMMARY,
            session_id="s1",
        ),
        session_id="s1", kind=EventKind.COMPACTION_SUMMARY,
        provenance=prov,
        fidelity=FidelityProfile.from_levels(
            {FidelityDimension.CONTENT_AVAILABILITY: FidelityLevel.PARTIAL}
        ),
        summary="redacted nav snippet",
        field_dispositions=(
            FieldDispositionRecord(
                "native_body", FieldDisposition.PRESERVED_BY_REFERENCE,
                "raw row kept in immutable artifact slice",
            ),
            FieldDispositionRecord(
                "auth_header", FieldDisposition.REDACTED, "never captured",
            ),
            FieldDispositionRecord(
                "token_usage", FieldDisposition.UNAVAILABLE, "vendor omitted",
            ),
            FieldDispositionRecord(
                "some_field", FieldDisposition.UNSUPPORTED, "not modeled",
            ),
        ),
    )
    gen = GenerationInput(
        family="pi", adapter_version="1.0.0", contract_version="1",
        capability_digest="cap", source_manifest_id="m1",
        dataset_digest="dd",
        artifacts=(artifact,), sessions=(session,), events=(event,),
        relations=(), dispositions=(),
    )
    life = GenerationLifecycle(db)
    gen_id = "gen-pi-syn"
    life.prepare(gen, gen_id)

    report = {
        "mode": "shadow", "source_root": str(tmp_path),
        "generations": {
            "pi": {
                "family": "pi", "status": "partial", "snapshot_count": 1,
                "event_count": 1, "generation_id": gen_id,
                "source_manifest_id": "m1", "artifact_hashes": ["h" * 64],
                "dataset_digest": "dd", "fidelity": None,
                "privacy_blocked": False, "reason": None,
            },
        },
        "uncovered_sources": [],
        "summary": {"full": 0, "partial": 1, "blocked": 0, "no_source": 0},
    }
    evaluated = _evaluate(report, db, None, inventory={"pi": 1})
    pi = evaluated.families["pi"]
    assert pi.dispositions["preserved_by_reference"] == 1
    assert pi.dispositions["redacted"] == 1
    assert pi.dispositions["unavailable"] == 1
    assert pi.dispositions["unsupported"] == 1
    assert pi.disposition_coverage == 1.0
    assert pi.projection_parity["excluded_events"] == 1  # compaction not a fact


def test_source_ref_resolution_sample_resolves_within_generation(tmp_path):
    """D-06: sampled source refs resolve via the staged generation db."""
    report, db, store, _src = _shadow(tmp_path)
    evaluated = _evaluate(report, db, store, inventory={"codex": 1})
    codex = evaluated.families["codex"]
    assert codex.source_refs_sample  # non-empty metadata sample
    assert codex.unresolved_provenance == 0
    for locator in codex.source_refs_sample:
        assert isinstance(locator, str) and locator


def test_replay_digest_is_stable(tmp_path):
    """Same captured artifact re-adapted yields the same dataset digest."""
    report, db, store, _src = _shadow(tmp_path)
    evaluated = _evaluate(report, db, store, inventory={"codex": 1})
    codex = evaluated.families["codex"]
    assert codex.replay_stable is True
    assert codex.replay_digest == codex.dataset_digest


def test_compatibility_projection_parity(tmp_path):
    """D-17: shadow projection parity is reported per staged generation."""
    report, db, store, _src = _shadow(tmp_path)
    evaluated = _evaluate(report, db, store, inventory={"codex": 1})
    codex = evaluated.families["codex"]
    parity = codex.projection_parity
    assert parity["projected_sessions"] >= 1
    assert parity["projected_messages"] >= 1
    assert parity["excluded_events"] >= 1
    assert parity["fingerprint_digest"]


def test_view_coverage_counts_views_by_type(tmp_path):
    """D-21: view coverage is counted for every staged generation."""
    report, db, store, _src = _shadow(tmp_path)
    evaluated = _evaluate(report, db, store, inventory={"codex": 1})
    codex = evaluated.families["codex"]
    counts = codex.view_counts
    assert set(counts) == {
        "turn", "native_trace", "episode", "compaction_window",
        "session", "topic", "cross_session",
    }
    assert counts["turn"] >= 1
    assert counts["session"] >= 1


# ------------------------------------------------------- live metadata smoke

def test_live_metadata_smoke_mode_never_returns_bodies(tmp_path):
    """Read-only probe returns metadata only; no bodies, no secrets."""
    from personal_knowledge.evaluation.conversation.adapter_fidelity import (
        live_inventory_metadata,
    )

    live_db = tmp_path / "agentsview_like.sqlite"
    con = sqlite3.connect(live_db)
    try:
        con.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, agent TEXT)")
        con.execute(
            "CREATE TABLE auth_tokens (id TEXT PRIMARY KEY, token_value TEXT)"
        )
        con.executemany(
            "INSERT INTO sessions VALUES (?, ?)",
            [("s1", "codex"), ("s2", "codex"), ("s3", "zcode")],
        )
        con.execute("INSERT INTO auth_tokens VALUES ('t1', 'canary-token-value-1')")
        con.commit()
    finally:
        con.close()

    probe = live_inventory_metadata(agentsview_db=live_db)
    assert probe["read_only"] is True
    assert probe["forbidden_source_access"] == 0
    assert probe["read_tables"] == ["sessions"]
    assert probe["families"]["codex"]["discovered_sessions"] == 2
    assert probe["families"]["zcode"]["discovered_sessions"] == 1
    raw = json.dumps(probe, ensure_ascii=False)
    assert "canary-token-value-1" not in raw
    assert _BODY_MARKER not in raw


def test_live_metadata_smoke_aliases_and_agent_names_resolve(tmp_path):
    """Aliases (vscode-copilot) and agent names (mimocode) resolve to families."""
    from personal_knowledge.evaluation.conversation.adapter_fidelity import (
        live_inventory_metadata,
    )

    live_db = tmp_path / "agentsview_like.sqlite"
    con = sqlite3.connect(live_db)
    try:
        con.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, agent TEXT)")
        con.executemany(
            "INSERT INTO sessions VALUES (?, ?)",
            [("s1", "vscode-copilot"), ("s2", "kimi-work"), ("s3", "mimocode")],
        )
        con.commit()
    finally:
        con.close()
    probe = live_inventory_metadata(agentsview_db=live_db)
    assert probe["families"]["copilot"]["discovered_sessions"] == 1
    assert probe["families"]["kimi-work"]["discovered_sessions"] == 1
    assert probe["families"]["mimo"]["discovered_sessions"] == 1
    assert probe["unknown_agents"] == []


# ---------------------------------------------------------------- gates

def test_activation_gates_pass_for_healthy_cohort(tmp_path):
    """Healthy temp cohort satisfies every activation gate with paid_calls=0."""
    report, db, store, _src = _shadow(tmp_path)
    evaluated = _evaluate(report, db, store, inventory={"codex": 1})
    gates = evaluated.gates
    assert gates["capability_coverage"]["with_result"] == 17
    assert gates["capability_coverage"]["missing"] == []
    assert gates["native_available_captured_or_blocked"]["ok"] is True
    assert gates["unresolved_provenance"]["count"] == 0
    assert gates["forbidden_source_access"]["count"] == 0
    assert gates["replay_digest_stable"]["ok"] is True
    assert gates["current_consumers_pass"]["ok"] is True
    assert gates["partial_chatgpt_cursor_disclosed"]["ok"] is True
    assert gates["paid_calls_zero"]["ok"] is True
    assert gates["overall"] is True
    assert evaluated.paid_calls == 0


def test_consumer_evidence_deduplicates_registered_aliases(tmp_path):
    report, db, store, _src = _shadow(tmp_path)
    evaluated = _evaluate(report, db, store, inventory={"codex": 1})
    evidence = evaluated.consumer_evidence
    assert evidence["projected_sessions"] == evidence["consumer_read_sessions"]


def test_gate_flags_missing_native_available_sessions(tmp_path):
    """A native-available session that is neither captured nor blocked fails."""
    report, db, store, _src = _shadow(tmp_path)
    evaluated = _evaluate(report, db, store, inventory={"codex": 9})
    gates = evaluated.gates
    assert gates["native_available_captured_or_blocked"]["ok"] is False
    assert gates["overall"] is False
    violations = gates["native_available_captured_or_blocked"]["violations"]
    assert any("codex" in v for v in violations)


def test_chatgpt_metadata_observation_does_not_fabricate_native_sessions(tmp_path):
    """One explicit unavailable observation covers pathless ChatGPT inventory."""
    from personal_knowledge.evaluation.conversation.adapter_fidelity import (
        _native_available_gate,
    )
    from personal_knowledge.evaluation.conversation.adapter_fidelity import (
        FamilyFidelityEntry,
    )
    entry = FamilyFidelityEntry(
        family="chatgpt", status="partial", capability={},
        discovered_sessions=104, captured_artifacts=1, captured_sessions=1,
        adapted_events=1, adapted_relations=0, dataset_digest="d",
        replay_digest="d", replay_stable=True,
        dispositions={}, disposition_coverage=0.0, unresolved_provenance=0,
        source_refs_sample=("agentsview#metadata",), projection_parity={},
        view_counts={}, fidelity={"source_availability": "unavailable"},
    )
    result = _native_available_gate({"chatgpt": entry}, {"chatgpt": 104})
    assert result["ok"] is True
    assert result["violations"] == []


def test_gate_flags_unresolved_provenance(tmp_path):
    """An event without artifact/native locator fails the provenance gate."""
    report, db, store, _src = _shadow(tmp_path)
    con = sqlite3.connect(db)
    try:
        con.execute("UPDATE ce_events SET native_locator='' WHERE 1=1")
        con.commit()
    finally:
        con.close()
    evaluated = _evaluate(report, db, store, inventory={"codex": 1})
    gates = evaluated.gates
    assert gates["unresolved_provenance"]["count"] > 0
    assert gates["unresolved_provenance"]["ok"] is False
    assert gates["overall"] is False


def test_gate_replay_stability_fails_when_source_drifted(tmp_path):
    """Re-adapting a changed source artifact fails the replay gate."""
    report, db, store, _src = _shadow(tmp_path)
    blob = next((store / "artifacts").glob("*"))
    drift = (
        '\n{"type":"response_item","session_id":"sess_01","turn_id":"turn_9",'
        '"item_id":"resp_drift","role":"assistant","content":"drift content",'
        '"timestamp":"2026-07-01T11:00:00Z"}'
    )
    blob.write_bytes(blob.read_bytes() + drift.encode("utf-8"))
    evaluated = _evaluate(report, db, store, inventory={"codex": 1})
    gates = evaluated.gates
    assert gates["replay_digest_stable"]["ok"] is False
    assert gates["overall"] is False


def test_gate_current_consumers_pass_against_projection(tmp_path):
    """Projected legacy rows keep the current ConversationRepository contract."""
    report, db, store, _src = _shadow(tmp_path)
    evaluated = _evaluate(report, db, store, inventory={"codex": 1})
    consumer = evaluated.consumer_evidence
    assert consumer["projected_sessions"] >= 1
    assert consumer["consumer_read_sessions"] >= 1
    assert consumer["consumer_read_messages"] >= 1


def test_gate_partial_chatgpt_cursor_disclosed(tmp_path):
    """ChatGPT/Cursor partial limitations are disclosed, not hidden (D-14)."""
    src = tmp_path / "sources"
    src.mkdir(exist_ok=True)
    shutil.copy2(FIXTURES / "codex_agent_sessions.jsonl", src / "codex.jsonl")
    # a ChatGPT observation marker detected only by the chatgpt adapter
    (src / "agentsview_observation.jsonl").write_text(
        json.dumps({"id": "obs-1", "role": "user", "content": _BODY_MARKER}),
        encoding="utf-8",
    )
    report, db, store, _src = _shadow(tmp_path, src)
    evaluated = _evaluate(report, db, store)
    chatgpt = evaluated.families["chatgpt"]
    assert chatgpt.status in ("partial", "blocked")
    assert chatgpt.fidelity is not None  # explicit fidelity, not hidden
    disclosures = "\n".join(evaluated.partial_disclosures)
    assert "chatgpt" in disclosures.lower()
    assert "cursor" in disclosures.lower()
    # disclosure is metadata only — no bodies
    raw = json.dumps(evaluated.partial_disclosures, ensure_ascii=False)
    assert _BODY_MARKER not in raw


def test_report_summary_tallies_full_partial_blocked(tmp_path):
    report, db, store, _src = _shadow(tmp_path)
    evaluated = _evaluate(report, db, store, inventory={"codex": 1})
    summary = evaluated.summary
    assert summary["full"] >= 1
    assert summary["total_families"] == 17
    assert (
        summary["full"] + summary["partial"] + summary["blocked"]
        + summary["no_source"] == 17
    )


def test_evaluator_never_embeds_bodies_in_any_output(tmp_path):
    report, db, store, _src = _shadow(tmp_path)
    evaluated = _evaluate(report, db, store, inventory={"codex": 1})
    raw = json.dumps(evaluated.to_dict(), ensure_ascii=False)
    assert _BODY_MARKER not in raw
    assert "sk-" not in raw.lower()
