"""Phase 62-04 Task 3: pk-sync conversations v2 dry-run / shadow / activation.

RED/GREEN tests for the v2 orchestration seam in
:mod:`personal_knowledge.application.run_pipeline` and the
:mod:`personal_knowledge.application.sync` command wiring:

  - dry-run probes every registered family's capability and estimates
    snapshot/event counts (metadata-only, no canonical writes)
  - explicit shadow captures artifacts, adapts, and writes a NON-active
    generation plus a metadata-only report
  - explicit activation delegates ONLY to :mod:`.event_generations` and is
    blocked by unknown family, source drift, missing family coverage,
    uncovered sources, or a blocked privacy gate
  - the default ``pk-sync conversations`` behavior is unchanged (flag surface
    is additive; legacy path untouched)
  - post-commit delta fires only after successful activation and carries no
    conversation bodies

All tests run against temporary SQLite files under tmp_path. No live database,
no var/, no data/canonical writes, no network, no provider calls (D-31).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from personal_knowledge.adapters.conversation_sources.registry import known_families
from personal_knowledge.application.conversation.event_generations import (
    GenerationActivationError,
    GenerationLifecycle,
)
from personal_knowledge.application.conversation.event_repository import (
    EventRepository,
)
from personal_knowledge.application.run_pipeline import (
    activate_conversation_generation,
    probe_conversation_sources,
    shadow_conversation_generation,
)
from personal_knowledge.application.sync import build_parser, main

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "conversation_sources"


def _make_source(tmp_path: Path) -> Path:
    src = tmp_path / "sources"
    src.mkdir(exist_ok=True)
    shutil.copy2(FIXTURES / "codex_agent_sessions.jsonl", src / "codex.jsonl")
    return src


def _shadow(tmp_path: Path) -> tuple[dict, Path, Path, Path]:
    src = _make_source(tmp_path)
    db = tmp_path / "v2.sqlite"
    store = tmp_path / "artifacts"
    report_path = tmp_path / "report.json"
    report = shadow_conversation_generation(
        source_root=src, db=db, artifact_store=store, report_path=report_path,
    )
    return report, db, src, report_path


# -------------------------------------------------------------------- dry-run

def test_dry_run_probes_every_registered_family(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    report = probe_conversation_sources(source_root=src)
    assert report["mode"] == "dry-run"
    names = {item["family"] for item in report["probed_families"]}
    assert names == set(known_families())  # all 17 registered families probed
    codex = next(i for i in report["probed_families"] if i["family"] == "codex")
    assert codex["status"] == "detected"
    assert codex["snapshot_estimate"] >= 1
    assert codex["event_estimate"] >= 1  # estimated by adapting the fixture
    zcode = next(i for i in report["probed_families"] if i["family"] == "zcode")
    assert zcode["status"] == "no_source"
    # metadata-only capability surface
    assert codex["event_kind_count"] >= 1
    assert codex["adapter_version"]


# --------------------------------------------------------------------- shadow

def test_shadow_stages_non_active_generation_and_report(tmp_path: Path) -> None:
    report, db, _src, report_path = _shadow(tmp_path)
    assert report_path.exists()
    codex = report["generations"]["codex"]
    assert codex["status"] == "full"
    assert codex["snapshot_count"] == 1
    assert codex["event_count"] >= 1
    gen_id = codex["generation_id"]
    # shadow writes a staged generation but NEVER activates
    life = GenerationLifecycle(db)
    assert life.authority_generation_id() is None
    assert EventRepository(db).validate_generation(gen_id)["ok"] is True


def test_shadow_report_is_metadata_only(tmp_path: Path) -> None:
    report, _db, _src, report_path = _shadow(tmp_path)
    raw = report_path.read_text(encoding="utf-8")
    # hashes/fidelity/counts only; no conversation bodies
    assert "dataset_digest" in raw
    assert "fidelity" in raw
    assert "hello world" not in raw  # fixture body text never in the report
    assert all("content" not in entry for entry in report["generations"].values())


def test_shadow_reports_uncovered_sources(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    (src / "mystery.bin").write_bytes(b"\x00 no adapter knows this")
    report, db, _src, report_path = _shadow(tmp_path)
    assert any("mystery.bin" in s for s in report["uncovered_sources"])


# ---------------------------------------------------------------- activation

def test_activation_delegates_and_writes_projection(tmp_path: Path) -> None:
    report, db, _src, _rp = _shadow(tmp_path)
    gen_id = report["generations"]["codex"]["generation_id"]
    result = activate_conversation_generation(
        db=db, generation_id=gen_id, report=report,
        expected_adapter_families=("codex",),
    )
    life = GenerationLifecycle(db)
    assert life.authority_generation_id() == gen_id
    con = __import__("sqlite3").connect(str(db))
    assert con.execute("SELECT COUNT(*) FROM canonical_sessions").fetchone()[0] >= 1
    con.close()
    assert result["generation_id"] == gen_id


def test_activation_blocks_unknown_family(tmp_path: Path) -> None:
    report, db, _src, _rp = _shadow(tmp_path)
    gen_id = report["generations"]["codex"]["generation_id"]
    with pytest.raises(GenerationActivationError, match="unknown_adapter"):
        activate_conversation_generation(
            db=db, generation_id=gen_id, report=report,
            expected_adapter_families=("codex", "ghost-family"),
        )
    assert GenerationLifecycle(db).authority_generation_id() is None


def test_activation_blocks_missing_family_coverage(tmp_path: Path) -> None:
    report, db, _src, _rp = _shadow(tmp_path)
    gen_id = report["generations"]["codex"]["generation_id"]
    with pytest.raises(GenerationActivationError, match="missing_family_coverage"):
        activate_conversation_generation(
            db=db, generation_id=gen_id, report=report,
            expected_adapter_families=("codex", "pi"),
        )
    assert GenerationLifecycle(db).authority_generation_id() is None


def test_activation_blocks_source_drift_stale_manifest(tmp_path: Path) -> None:
    report, db, _src, _rp = _shadow(tmp_path)
    gen_id = report["generations"]["codex"]["generation_id"]
    # source changed between shadow and activation: manifest no longer matches
    report["generations"]["codex"]["source_manifest_id"] = "stale-manifest"
    with pytest.raises(GenerationActivationError, match="stale_source_manifest"):
        activate_conversation_generation(
            db=db, generation_id=gen_id, report=report,
            expected_adapter_families=("codex",),
        )
    assert GenerationLifecycle(db).authority_generation_id() is None


def test_activation_blocks_privacy_gate(tmp_path: Path) -> None:
    report, db, _src, _rp = _shadow(tmp_path)
    gen_id = report["generations"]["codex"]["generation_id"]
    report["generations"]["codex"]["status"] = "blocked"
    report["generations"]["codex"]["privacy_blocked"] = True
    with pytest.raises(GenerationActivationError, match="privacy_gate_blocked"):
        activate_conversation_generation(
            db=db, generation_id=gen_id, report=report,
            expected_adapter_families=("codex",),
        )
    assert GenerationLifecycle(db).authority_generation_id() is None


def test_activation_blocks_uncovered_sources(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    (src / "mystery.bin").write_bytes(b"\x00 no adapter knows this")
    report, db, _src, _rp = _shadow(tmp_path)
    gen_id = report["generations"]["codex"]["generation_id"]
    with pytest.raises(GenerationActivationError, match="uncovered_sources"):
        activate_conversation_generation(
            db=db, generation_id=gen_id, report=report,
            expected_adapter_families=("codex",),
        )
    assert GenerationLifecycle(db).authority_generation_id() is None


def test_activation_delta_fires_only_after_success(tmp_path: Path) -> None:
    report, db, _src, _rp = _shadow(tmp_path)
    gen_id = report["generations"]["codex"]["generation_id"]
    calls: list[dict] = []

    def delta_publisher(meta: dict) -> dict:
        calls.append(meta)
        assert "content" not in meta and "summary" not in meta  # no bodies
        return {"published": True, "status": "appended"}

    result = activate_conversation_generation(
        db=db, generation_id=gen_id, report=report,
        expected_adapter_families=("codex",), delta_publisher=delta_publisher,
    )
    assert result["delta"]["published"] is True
    assert len(calls) == 1

    # blocked activation never publishes a delta
    blocked_report = json.loads(_rp.read_text(encoding="utf-8"))
    blocked_report["generations"]["codex"]["privacy_blocked"] = True
    with pytest.raises(GenerationActivationError):
        activate_conversation_generation(
            db=db, generation_id=gen_id, report=blocked_report,
            expected_adapter_families=("codex",), delta_publisher=delta_publisher,
        )
    assert len(calls) == 1  # no extra delta for the failed attempt


# ------------------------------------------------------------- CLI wiring

def test_cli_v2_dry_run_and_shadow(tmp_path: Path) -> None:
    src = _make_source(tmp_path)
    assert main(["conversations", "--v2-dry-run", "--v2-source", str(src)]) == 0
    db = tmp_path / "v2.sqlite"
    store = tmp_path / "artifacts"
    report = tmp_path / "report.json"
    assert main([
        "conversations", "--v2-shadow",
        "--v2-source", str(src), "--v2-db", str(db),
        "--v2-artifact-store", str(store), "--v2-report", str(report),
    ]) == 0
    assert report.exists()
    data = json.loads(report.read_text(encoding="utf-8"))
    assert "codex" in data["generations"]
    # still not activated through the CLI shadow
    assert GenerationLifecycle(db).authority_generation_id() is None


def test_cli_v2_activation_and_blocked_privacy(tmp_path: Path) -> None:
    report, db, _src, report_path = _shadow(tmp_path)
    gen_id = report["generations"]["codex"]["generation_id"]
    assert main([
        "conversations", "--v2-activate", gen_id,
        "--v2-db", str(db), "--v2-report", str(report_path),
        "--v2-families", "codex",
    ]) == 0
    assert GenerationLifecycle(db).authority_generation_id() == gen_id
    # a blocked privacy gate makes the CLI fail closed
    report2 = json.loads(report_path.read_text(encoding="utf-8"))
    report2["generations"]["codex"]["privacy_blocked"] = True
    report_path.write_text(json.dumps(report2), encoding="utf-8")
    assert main([
        "conversations", "--v2-activate", gen_id,
        "--v2-db", str(db), "--v2-report", str(report_path),
        "--v2-families", "codex",
    ]) != 0


def test_default_flag_surface_unchanged() -> None:
    p = build_parser()
    args = p.parse_args(["conversations", "--write"])
    assert args.write is True
    assert getattr(args, "v2_dry_run", False) is False
    assert getattr(args, "v2_shadow", False) is False
    assert getattr(args, "v2_activate", None) is None
    # no v2 defaults point at the live canonical database
    assert str(args.v2_db) != "agent_conversations.sqlite"
    assert "personal_system" not in str(args.v2_db)
