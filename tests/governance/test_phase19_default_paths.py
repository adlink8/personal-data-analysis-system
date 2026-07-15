"""Real-checkout regressions for Phase 19 migrated default paths."""

from personal_knowledge.core.project_paths import (
    KNOWLEDGE_ACTIVE_POINTER,
    KNOWLEDGE_EVAL_DIR,
    PACKAGE_DIR,
)
from personal_knowledge.domains.knowledge import build_canonical_knowledge_units as canonical
from personal_knowledge.domains.knowledge import evaluate_knowledge_unit_rag as rag
from personal_knowledge.domains.memory import audit_memory_experiments as memory_audit
from personal_knowledge.retrieval import compare_vector_generations as vector_compare


def test_real_default_eval_dataset_and_merge_gate_are_resolved() -> None:
    assert rag.EVAL_DIR == KNOWLEDGE_EVAL_DIR
    assert len(rag._load_eval_dataset("frozen-test")) > 0
    gate = canonical.evaluate_merge_gate()
    assert gate.get("error") != "eval pairs not found"


def test_real_active_collection_and_query_sources_are_canonical() -> None:
    active = vector_compare.read_active_collection()
    assert KNOWLEDGE_ACTIVE_POINTER.is_file()
    assert active
    assert vector_compare.EVAL_DIR == KNOWLEDGE_EVAL_DIR
    sources = vector_compare.default_query_sources()
    assert sources == {
        "events": "personal_events",
        "turns": "conversation_turns",
        "ku": active,
    }
    suites = {case["_suite"] for case in vector_compare.load_eval_queries()}
    assert {"frozen", "dev", "profile"} <= suites


def test_memory_audit_scans_canonical_src_tree() -> None:
    scan = memory_audit.scan_script_references()
    assert memory_audit.SCRIPTS_DIR == PACKAGE_DIR
    assert scan["scan_root"] == str(PACKAGE_DIR)
    assert any(info["references"] for info in scan["targets"].values())
