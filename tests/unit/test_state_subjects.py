from pathlib import Path

import pytest

from personal_knowledge.application.knowledge.state_subjects import (
    DEFAULT_STATE_SUBJECTS,
    StateSubjectsError,
    load_state_subjects,
    match_state_subject,
    normalize_subject,
)


def test_normalize_subject_is_deterministic_and_preserves_cjk():
    assert normalize_subject("  Git 分支/Dev ") == normalize_subject("git分支dev")
    assert normalize_subject(None) == ""
    assert normalize_subject("  !!! ") == ""


def test_match_prefers_exact_and_prefix_is_one_directional():
    rules = {
        "families": [
            {"name": "path", "subjects": [{"pattern": "工作目录", "match": "prefix"}]},
            {"name": "exact", "subjects": [{"pattern": "工作目录", "match": "exact"}]},
        ]
    }
    assert match_state_subject("工作目录", rules) == "exact"
    assert match_state_subject("工作目录/数据分析", rules) == "path"
    assert match_state_subject("工作", rules) is None
    assert match_state_subject("未知 subject", rules) is None


def test_load_errors_are_typed(tmp_path: Path):
    with pytest.raises(StateSubjectsError) as missing:
        load_state_subjects(tmp_path / "missing.yaml")
    assert missing.value.reason == "registry_unreadable"

    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("families: [{name: x, subjects: [{pattern: x, match: suffix}]}]", encoding="utf-8")
    with pytest.raises(StateSubjectsError) as bad:
        load_state_subjects(invalid)
    assert bad.value.reason == "invalid_match_mode"


def test_seed_registry_has_all_five_families_and_a_matching_sample():
    rules = load_state_subjects(DEFAULT_STATE_SUBJECTS)
    names = {family["name"] for family in rules["families"]}
    assert names == {
        "directory_path",
        "git_branch",
        "project_phase",
        "current_plan",
        "device_environment",
    }
    for family in rules["families"]:
        sample = family["subjects"][0]["pattern"]
        assert match_state_subject(sample, rules) == family["name"]
