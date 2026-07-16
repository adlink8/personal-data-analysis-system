"""pk-ku product CLI surface — thin wrapper, policy on flags not code edits."""

from __future__ import annotations

import pytest

from personal_knowledge.application.ku import build_parser, main


def test_parser_subcommands_exist():
    p = build_parser()
    # required=True subparsers: parse known commands without crashing
    for cmd in (
        "inspect", "prepare", "extract", "status", "extract-gate",
        "canonical", "publish", "vector", "canary", "promote", "watermark",
        "workflow",
    ):
        # --help exits SystemExit 0
        with pytest.raises(SystemExit) as ei:
            p.parse_args([cmd, "--help"])
        assert ei.value.code == 0


def test_workflow_prints_and_exits_0(capsys):
    code = main(["workflow"])
    assert code == 0
    out = capsys.readouterr().out
    assert "pk-ku inspect" in out
    assert "Forbidden" in out or "forbidden" in out.lower()
    assert "full inventory" in out.lower() or "build_knowledge_inventory" in out


def test_prepare_requires_model():
    p = build_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["prepare"])  # missing --model


def test_extract_rejects_non_incremental_run_id(capsys):
    code = main(["extract", "--run", "6f3da1eec10c4fee6fb1509c83cfb85b", "--max-items", "1"])
    assert code == 2
    err = capsys.readouterr().err
    assert "ir_" in err or "incremental" in err.lower()


def test_promote_without_args_exits_2(capsys):
    code = main(["promote"])
    assert code == 2


def test_watermark_show_json(capsys):
    code = main(["watermark"])
    assert code == 0
    out = capsys.readouterr().out
    assert "committed" in out
    assert "current_source_checksum" in out


def test_watermark_advance_requires_source(capsys):
    code = main(["watermark", "--advance"])
    assert code == 2
    err = capsys.readouterr().err
    assert "--from-canonical" in err or "--checksum" in err


def test_watermark_advance_dry_run_from_canonical(capsys):
    code = main(["watermark", "--advance", "--from-canonical"])
    assert code == 0
    out = capsys.readouterr().out
    assert "dry-run" in out or '"write": false' in out.lower() or '"write": false' in out
