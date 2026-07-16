"""Phase 22-04: pk-ku doctor read-only health checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from personal_knowledge.application.knowledge.doctor_ku import (
    format_human,
    report_to_dict,
    run_doctor,
    scan_facade_imports,
)
from personal_knowledge.application.ku import build_parser, main as ku_main


def _healthy_layout(tmp_path: Path) -> dict[str, Path]:
    db = tmp_path / "personal_system.sqlite"
    conv = tmp_path / "agent_conversations.sqlite"
    pointer = tmp_path / "knowledge_index_active.txt"
    db.write_bytes(b"")  # existence only; watermark handles missing schema softly
    conv.write_bytes(b"")
    pointer.write_text("knowledge_units_test_collection\n", encoding="utf-8")
    return {"db": db, "conv": conv, "pointer": pointer}


def test_doctor_ok_when_critical_paths_present(tmp_path: Path):
    paths = _healthy_layout(tmp_path)
    report = run_doctor(
        unified_db=paths["db"],
        conversations_db=paths["conv"],
        active_pointer=paths["pointer"],
        skip_ports=True,
        include_facade=False,
    )
    assert report.ok is True
    assert report.exit_code == 0
    by_id = {c.id: c for c in report.checks}
    assert by_id["unified_db"].ok
    assert by_id["agent_conversations_db"].ok
    assert by_id["active_pointer"].ok
    assert by_id["active_pointer"].detail["collection"] == "knowledge_units_test_collection"


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
    paths = _healthy_layout(tmp_path)

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


def test_pk_ku_doctor_cli_with_temp_paths(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
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
