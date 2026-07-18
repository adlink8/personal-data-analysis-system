"""Phase 22-04: pk-ku doctor read-only health checks."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from personal_knowledge.application.knowledge.doctor_ku import (
    _check_source_watermarks,
    format_human,
    report_to_dict,
    run_doctor,
    scan_facade_imports,
)
from personal_knowledge.application.ku import build_parser, main as ku_main
from personal_knowledge.application.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL
from personal_knowledge.application.serving.snapshots import activate_snapshot, prepare_snapshot, validate_snapshot
from personal_knowledge.application.serving.versions import record_publication


def _healthy_layout(tmp_path: Path) -> dict[str, Path]:
    db = tmp_path / "personal_system.sqlite"
    conv = tmp_path / "agent_conversations.sqlite"
    pointer = tmp_path / "knowledge_index_active.txt"
    db.write_bytes(b"")  # existence only; watermark handles missing schema softly
    conv.write_bytes(b"")
    pointer.write_text("knowledge_units_test_collection\n", encoding="utf-8")
    return {"db": db, "conv": conv, "pointer": pointer}


def _composite_layout(tmp_path: Path) -> dict[str, Path]:
    paths = _healthy_layout(tmp_path)
    paths["db"].unlink()
    paths["conv"].unlink()
    con = sqlite3.connect(paths["db"])
    con.executescript(SCHEMA_SQL)
    con.close()
    con = sqlite3.connect(paths["conv"])
    con.execute("CREATE TABLE canonical_sessions(canonical_session_id TEXT PRIMARY KEY,evidence_eligible INTEGER)")
    con.execute("CREATE TABLE canonical_messages(canonical_message_id TEXT PRIMARY KEY,canonical_session_id TEXT,role TEXT,content TEXT,evidence_scope TEXT,is_system INTEGER)")
    con.execute("INSERT INTO canonical_sessions VALUES ('s1',1)")
    con.execute("INSERT INTO canonical_messages VALUES ('cm|probe','s1','user','safe','user',0)")
    con.commit(); con.close()

    definitions = [
        ("canonical_conversation", "d.canonical_conversation", "sqlite_store", "conversation"),
        ("canonical_message", "d.canonical_message", "sqlite_view", "messages"),
        ("turn_summary", "s.turn_summary", "json_artifact", "turns"),
        ("google_normalized", "d.google_normalized", "sqlite_store", "google"),
        ("google_assertion", "s.google_assertion", "sqlite_table", "assertions"),
        ("canonical_knowledge", "s.knowledge_unit", "sqlite_table", "knowledge"),
        ("turn_retrieval", "r.turn_vector", "chroma_collection", "turn_collection"),
        ("knowledge_retrieval", "r.knowledge_index", "chroma_collection", "knowledge_units_test_collection"),
        ("product_retrieval", "r.layered_search", "service_contract", "layered_search"),
        ("knowledge_evaluation", "a.knowledge_evaluation", "evaluation_run", "gate"),
    ]
    members = {}
    for role, registry_id, kind, ref in definitions:
        recorded = record_publication(
            paths["db"], registry_id=registry_id, version="v1", checksum="ck",
            location_kind=kind, location_ref=ref, source_key=role,
            watermark_value="wm-v1", metadata={"count": 2} if kind == "chroma_collection" else {},
        )
        members[role] = {
            "artifact_version_id": recorded["artifact_version_id"], "version": "v1",
            "checksum": "ck", "location_kind": kind, "location_ref": ref,
            "watermark_id": recorded["watermark_id"],
            "metadata": {"count": 2} if kind == "chroma_collection" else {},
        }
    draft = prepare_snapshot(paths["db"], members, eval_gate_ref="gate", write=True)
    inspected = lambda _: {"exists": True, "checksum": "ck", "count": 2}
    assert validate_snapshot(paths["db"], draft["snapshot_id"], collection_inspector=inspected, required_roles=set(members))["ok"]
    activate_snapshot(paths["db"], draft["snapshot_id"], pointer_path=paths["pointer"])
    return paths


def test_doctor_ok_when_critical_paths_present(tmp_path: Path):
    paths = _composite_layout(tmp_path)
    report = run_doctor(
        unified_db=paths["db"],
        conversations_db=paths["conv"],
        active_pointer=paths["pointer"],
        skip_ports=True,
        include_facade=False,
        collection_inspector=lambda _: {"exists": True, "checksum": "ck", "count": 2},
    )
    assert report.ok is True
    assert report.exit_code == 0
    by_id = {c.id: c for c in report.checks}
    assert by_id["unified_db"].ok
    assert by_id["agent_conversations_db"].ok
    assert by_id["active_pointer"].ok
    assert by_id["sqlite_foreign_keys"].ok
    assert by_id["active_pointer"].detail["collection"] == "knowledge_units_test_collection"


def test_source_watermarks_allow_version_bound_historical_rollback(tmp_path: Path):
    paths = _composite_layout(tmp_path)
    active = sqlite3.connect(paths["db"]).execute(
        "SELECT active_snapshot_id FROM serving_authority WHERE singleton_id=1"
    ).fetchone()[0]
    for registry_id, source_key in (
        ("s.knowledge_unit", "canonical_knowledge"),
        ("r.knowledge_index", "knowledge_retrieval"),
    ):
        record_publication(
            paths["db"],
            registry_id=registry_id,
            version="v2",
            checksum="ck-v2",
            location_kind="sqlite_table" if registry_id.startswith("s.") else "chroma_collection",
            location_ref="new-location",
            source_key=source_key,
            watermark_value="wm-v2",
        )
    con = sqlite3.connect(paths["db"])
    con.execute(
        "UPDATE source_watermarks SET recorded_at='9999-12-31T23:59:59Z' "
        "WHERE value='wm-v2'"
    )
    con.commit()
    con.close()
    assert _check_source_watermarks(paths["db"]).ok is False
    con = sqlite3.connect(paths["db"])
    con.execute(
        "INSERT INTO serving_snapshot_events VALUES (?,?,?,?,?,?)",
        ("se_rollback", active, "rollback", "newer", "{}", "now"),
    )
    con.commit()
    con.close()
    check = _check_source_watermarks(paths["db"])
    assert check.ok is True
    assert check.detail["rollback_active"] is True


def test_doctor_fails_on_foreign_key_violations(tmp_path: Path):
    paths = _healthy_layout(tmp_path)
    con = sqlite3.connect(paths["db"])
    con.executescript(
        "CREATE TABLE parent (id INTEGER PRIMARY KEY);"
        "CREATE TABLE child (parent_id INTEGER REFERENCES parent(id));"
        "INSERT INTO child(parent_id) VALUES (42);"
    )
    con.commit()
    con.close()

    report = run_doctor(
        unified_db=paths["db"],
        conversations_db=paths["conv"],
        active_pointer=paths["pointer"],
        skip_ports=True,
        include_facade=False,
    )
    assert report.ok is False
    assert report.exit_code == 1
    check = next(c for c in report.checks if c.id == "sqlite_foreign_keys")
    assert check.ok is False
    assert check.detail["violations_total"] == 1
    assert check.detail["violations_by_table"] == {"child": 1}


def test_doctor_fails_when_unified_db_missing(tmp_path: Path):
    conv = tmp_path / "agent_conversations.sqlite"
    pointer = tmp_path / "knowledge_index_active.txt"
    conv.write_bytes(b"")
    pointer.write_text("coll\n", encoding="utf-8")
    report = run_doctor(
        unified_db=tmp_path / "missing.sqlite",
        conversations_db=conv,
        active_pointer=pointer,
        skip_ports=True,
        include_facade=False,
    )
    assert report.ok is False
    assert report.exit_code == 1
    assert any(c.id == "unified_db" and not c.ok for c in report.checks)


def test_doctor_fails_when_active_pointer_missing(tmp_path: Path):
    paths = _healthy_layout(tmp_path)
    report = run_doctor(
        unified_db=paths["db"],
        conversations_db=paths["conv"],
        active_pointer=tmp_path / "no_pointer.txt",
        skip_ports=True,
        include_facade=False,
    )
    assert report.ok is False
    assert report.exit_code == 1
    assert any(c.id == "active_pointer" and not c.ok for c in report.checks)


def test_doctor_fails_when_active_pointer_empty(tmp_path: Path):
    paths = _healthy_layout(tmp_path)
    paths["pointer"].write_text("   \n", encoding="utf-8")
    report = run_doctor(
        unified_db=paths["db"],
        conversations_db=paths["conv"],
        active_pointer=paths["pointer"],
        skip_ports=True,
        include_facade=False,
    )
    assert report.ok is False
    assert report.exit_code == 1


def test_doctor_fails_when_conversations_db_missing(tmp_path: Path):
    paths = _healthy_layout(tmp_path)
    report = run_doctor(
        unified_db=paths["db"],
        conversations_db=tmp_path / "no_conv.sqlite",
        active_pointer=paths["pointer"],
        skip_ports=True,
        include_facade=False,
    )
    assert report.ok is False
    assert report.exit_code == 1


def test_ports_down_are_warn_not_fail(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    paths = _composite_layout(tmp_path)

    def _never_listen(host: str, port: int, timeout: float = 0.4) -> bool:
        return False

    monkeypatch.setattr(
        "personal_knowledge.application.knowledge.doctor_ku._tcp_listening",
        _never_listen,
    )
    report = run_doctor(
        unified_db=paths["db"],
        conversations_db=paths["conv"],
        active_pointer=paths["pointer"],
        skip_ports=False,
        include_facade=False,
        collection_inspector=lambda _: {"exists": True, "checksum": "ck", "count": 2},
    )
    assert report.ok is True
    assert report.exit_code == 0
    port_checks = [c for c in report.checks if c.id.startswith("port_")]
    assert port_checks
    assert all(c.severity == "warn" for c in port_checks)
    assert all(c.ok for c in port_checks)


def test_scan_facade_imports_counts_domains(tmp_path: Path):
    app = tmp_path / "application"
    (app / "knowledge").mkdir(parents=True)
    (app / "knowledge" / "a.py").write_text(
        "from personal_knowledge.domains.knowledge.foo import x\n"
        "import personal_knowledge.domains.bar\n"
        "from personal_knowledge.core.project_paths import ROOT\n",
        encoding="utf-8",
    )
    (app / "knowledge" / "b.py").write_text(
        "from personal_knowledge.domains.x import y\n",
        encoding="utf-8",
    )
    inv = scan_facade_imports(app)
    assert inv["total_import_lines"] == 3
    assert inv["files_with_imports"] == 2
    assert inv["top_files"][0]["path"] == "knowledge/a.py"
    assert inv["top_files"][0]["count"] == 2


def test_report_json_serializable(tmp_path: Path):
    paths = _healthy_layout(tmp_path)
    report = run_doctor(
        unified_db=paths["db"],
        conversations_db=paths["conv"],
        active_pointer=paths["pointer"],
        skip_ports=True,
        include_facade=False,
    )
    doc = report_to_dict(report)
    raw = json.dumps(doc)
    assert "exit_code" in raw
    human = format_human(report)
    assert "pk-ku doctor" in human
    assert "OK" in human or "FAIL" in human


def test_pk_ku_doctor_cli_parser():
    p = build_parser()
    args = p.parse_args(["doctor", "--json", "--skip-ports", "--no-facade"])
    assert args.command == "doctor"
    assert args.json is True
    assert args.skip_ports is True
    assert args.no_facade is True


def test_pk_ku_doctor_cli_with_temp_paths(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch):
    paths = _composite_layout(tmp_path)
    monkeypatch.setattr("personal_knowledge.application.knowledge.doctor_ku._default_collection_inspector", lambda _: {"exists": True, "checksum": "ck", "count": 2})
    code = ku_main(
        [
            "doctor",
            "--json",
            "--skip-ports",
            "--no-facade",
            "--db",
            str(paths["db"]),
            "--canonical-db",
            str(paths["conv"]),
            "--active-pointer",
            str(paths["pointer"]),
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    doc = json.loads(out)
    assert doc["ok"] is True
    assert doc["exit_code"] == 0
    assert "read-only" in doc.get("note", "").lower() or "promote" in doc.get("note", "").lower()


def test_pk_ku_doctor_cli_fail_missing_pointer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    paths = _healthy_layout(tmp_path)
    code = ku_main(
        [
            "doctor",
            "--json",
            "--skip-ports",
            "--no-facade",
            "--db",
            str(paths["db"]),
            "--canonical-db",
            str(paths["conv"]),
            "--active-pointer",
            str(tmp_path / "gone.txt"),
        ]
    )
    assert code == 1
    doc = json.loads(capsys.readouterr().out)
    assert doc["ok"] is False


def test_composite_defects_fail_corresponding_critical_checks(tmp_path: Path) -> None:
    paths = _composite_layout(tmp_path)
    inspect_ok = lambda _: {"exists": True, "checksum": "ck", "count": 2}

    paths["pointer"].write_text("wrong_collection", encoding="utf-8")
    report = run_doctor(unified_db=paths["db"], conversations_db=paths["conv"], active_pointer=paths["pointer"], skip_ports=True, include_facade=False, collection_inspector=inspect_ok)
    assert next(c for c in report.checks if c.id == "snapshot_pointer_parity").ok is False

    # Restore projection, then inject collection and evidence failures independently.
    paths["pointer"].write_text("knowledge_units_test_collection", encoding="utf-8")
    report = run_doctor(unified_db=paths["db"], conversations_db=paths["conv"], active_pointer=paths["pointer"], skip_ports=True, include_facade=False, collection_inspector=lambda _: {"exists": True, "checksum": "bad", "count": 2})
    assert next(c for c in report.checks if c.id == "serving_snapshot").ok is False
    report = run_doctor(unified_db=paths["db"], conversations_db=paths["conv"], active_pointer=paths["pointer"], skip_ports=True, include_facade=False, collection_inspector=inspect_ok, evidence_probe=lambda: {"status": "missing"})
    assert next(c for c in report.checks if c.id == "evidence_resolver").ok is False


def test_registry_and_watermark_drift_fail_closed(tmp_path: Path) -> None:
    paths = _composite_layout(tmp_path)
    inspect_ok = lambda _: {"exists": True, "checksum": "ck", "count": 2}
    registry = tmp_path / "bad_registry.yaml"
    source = Path("governance/policies/artifact_layers.yaml").read_text(encoding="utf-8")
    registry.write_text(source.replace("authority_role: canonical_message", "authority_role: canonical_conversation", 1), encoding="utf-8")
    report = run_doctor(unified_db=paths["db"], conversations_db=paths["conv"], active_pointer=paths["pointer"], skip_ports=True, include_facade=False, collection_inspector=inspect_ok, registry_path=registry)
    assert next(c for c in report.checks if c.id == "artifact_registry").ok is False

    con = sqlite3.connect(paths["db"])
    con.execute("INSERT INTO artifact_versions VALUES ('future-av','d.canonical_conversation','v2','ck2','sqlite_store','conversation','published','R4',NULL,NULL,'{}','2099-01-01T00:00:00Z')")
    con.execute("INSERT INTO source_watermarks VALUES ('future-wm','d.canonical_conversation','canonical_conversation','wm-v2','future-av','2099-01-01T00:00:00Z')")
    con.commit(); con.close()
    report = run_doctor(unified_db=paths["db"], conversations_db=paths["conv"], active_pointer=paths["pointer"], skip_ports=True, include_facade=False, collection_inspector=inspect_ok)
    assert next(c for c in report.checks if c.id == "source_watermarks").ok is False
