from __future__ import annotations

from personal_knowledge.core.project_paths import KNOWLEDGE_ACTIVE_POINTER, UNIFIED_DB
from personal_knowledge.intelligence.proactive.cli import build_parser, run_acceptance, _guard


def test_live_target_d_acceptance_is_metadata_only_and_two_verdict() -> None:
    result = run_acceptance(UNIFIED_DB, pointer_path=KNOWLEDGE_ACTIVE_POINTER)
    assert result["technical_status"] == "passed"
    assert result["release_status"] == "release_blocked" and result["release_ready"] is False
    assert result["unchanged"] and result["before_fingerprint"] == result["after_fingerprint"]
    assert result["mutations"] == result["persisted_rows"] == result["private_bodies"] == 0
    assert result["external_actions"] == result["network_calls"] == result["paid_calls"] == 0
    assert set(result["domain_counts"]) == {"learning", "career", "project", "health", "finance", "relationship", "time", "energy"}
    assert result["phase24"]["human_review_strict"]["ok"] is False
    assert result["phase24"]["lifecycle_strict"]["ok"] is False


def test_local_write_requires_all_guards() -> None:
    base = ["--db", str(UNIFIED_DB), "control", "--candidate-id", "candidate", "--candidate-checksum", "1"*64,
            "--operation", "suppress", "--reason-code", "user", "--created-at", "2026-07-18T00:00:00Z",
            "--actor-class", "user", "--actor-identity-hash", "2"*64, "--expected-sequence", "0", "--idempotency-key", "one"]
    args = build_parser().parse_args(base)
    assert _guard(args)["error"]["code"] == "write_required"
    args = build_parser().parse_args(base + ["--write"])
    assert _guard(args)["error"]["code"] == "confirmation_required"
    args = build_parser().parse_args(base + ["--write", "--i-confirm", "other"])
    assert _guard(args)["error"]["code"] == "confirmation_mismatch"
    args = build_parser().parse_args(base + ["--write", "--i-confirm", "candidate"])
    assert _guard(args) is None
