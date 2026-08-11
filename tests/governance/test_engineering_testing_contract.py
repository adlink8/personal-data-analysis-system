from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _policy(name: str) -> dict:
    return yaml.safe_load(
        (ROOT / "governance" / "policies" / name).read_text(encoding="utf-8")
    )


def test_behavior_changes_are_bound_to_public_seams_and_red_green() -> None:
    policy = _policy("testing.yaml")

    assert policy["seams"]["declaration_required"] is True
    assert policy["seams"]["test_target"] == "public_behavior"
    assert policy["tdd"]["sequence"] == ["red", "green", "focused_regression"]
    assert policy["tdd"]["one_vertical_slice_at_a_time"] is True
    assert "bug_fix" in policy["tdd"]["required_for"]
    assert policy["change_gates"]["bug_fix_requires_regression_test"] is True


def test_contract_prefers_real_local_adapters_over_internal_mocks() -> None:
    policy = _policy("testing.yaml")

    assert "internal_project_module" in policy["mocking"]["forbidden_targets"]
    assert "temporary_sqlite" in policy["mocking"]["preferred_test_doubles"]
    assert "deterministic_replay_provider" in policy["mocking"]["preferred_test_doubles"]
    assert policy["coverage"]["critical_policy_branch_percent"] == 100
    assert policy["coverage"]["changed_line_percent"] == 85


def test_module_design_has_hard_split_triggers_and_review_thresholds() -> None:
    policy = _policy("architecture.yaml")["module_design"]

    assert policy["one_primary_responsibility_per_module"] is True
    assert "second_independent_reason_to_change" in policy["required_split_triggers"]
    assert "mixed_ui_transport_domain_and_persistence" in policy["required_split_triggers"]
    assert policy["review_thresholds"]["production_file_lines"] == 500
    assert policy["review_thresholds"]["function_lines"] == 80
    assert policy["threshold_behavior"] == "justify_or_split_before_adding_behavior"


def test_agent_instructions_route_engineering_changes_to_the_contract() -> None:
    pointer = "docs/architecture/engineering-and-testing-contract.md"
    root_agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    manual = (ROOT / "docs" / "AGENTS.md").read_text(encoding="utf-8")

    assert pointer in root_agents
    assert "architecture/engineering-and-testing-contract.md" in manual

