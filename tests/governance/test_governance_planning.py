from pathlib import Path
import yaml

from integration.scripts.governance import check_planning_consistency as planning

ROOT = Path(__file__).resolve().parents[2]


def test_planning_truth_hierarchy():
    policy = yaml.safe_load((ROOT / "governance/policies/planning.yaml").read_text(encoding="utf-8"))
    assert policy["authoritative"] == ".planning"
    assert policy["historical_read_only"] == ".gsd"


def test_phase17_remains_open_and_consistent():
    assert planning.check(ROOT) == []
    # Phase 17 is kept in the v1.1 milestone archive; the active roadmap
    # intentionally contains only the current milestone ordering.
    roadmap = (ROOT / ".planning/milestones/v1.1-ROADMAP.md").read_text(encoding="utf-8")
    assert "17 | 4/4 code" in roadmap
    assert "Executing" in roadmap


def test_checker_reports_known_drift(tmp_path: Path):
    (tmp_path / "governance/policies").mkdir(parents=True)
    (tmp_path / ".planning").mkdir()
    (tmp_path / "governance/policies/planning.yaml").write_text((ROOT / "governance/policies/planning.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / ".planning/STATE.md").write_text("Phase 17 code complete; human checkpoints\nPlan: 1 of 6", encoding="utf-8")
    (tmp_path / ".planning/ROADMAP.md").write_text("Phase 17: open\n**Plans:** 17-01..04 planned\n18 | 0/6", encoding="utf-8")
    assert any("Phase 17 plans" in item for item in planning.check(tmp_path))


def test_checker_rejects_completed_phase_with_stale_context(tmp_path: Path):
    (tmp_path / "governance/policies").mkdir(parents=True)
    phase_dir = tmp_path / ".planning/phases/18-full-repository-governance"
    phase_dir.mkdir(parents=True)
    (tmp_path / "governance/policies/planning.yaml").write_text(
        (ROOT / "governance/policies/planning.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / ".planning/STATE.md").write_text(
        "Phase 17 code complete; human checkpoints\nPlan: 6 of 6", encoding="utf-8"
    )
    (tmp_path / ".planning/ROADMAP.md").write_text(
        "- [ ] Phase 17: open\n- [x] Phase 18: complete\n| 18 | 6/6 | **Complete** | today |",
        encoding="utf-8",
    )
    (phase_dir / "18-CONTEXT.md").write_text(
        "---\nphase: 18\nstatus: planned\n---\n", encoding="utf-8"
    )
    assert any("CONTEXT status" in item for item in planning.check(tmp_path))
