"""Wave 9.2: graph relation candidate v2 逻辑测试。"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
UNIFIED_SCRIPTS = ROOT / "integration" / "scripts"
if str(UNIFIED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(UNIFIED_SCRIPTS))

import build_graph_relation_candidates_v2 as mod  # noqa: E402


def make_package() -> dict:
    return {
        "package_id": "grpkg:test",
        "source_node_id": "s1#t1",
        "target_node_id": "s2#t2",
        "source_turn": {
            "node_id": "s1#t1",
            "session_id": "s1",
            "turn_id": "t1",
            "turn_no": 1,
            "main_topic": "topic-a",
            "narrative": "source narrative",
            "source_refs": ["a:1"],
            "tools_used": [],
        },
        "target_turn": {
            "node_id": "s2#t2",
            "session_id": "s2",
            "turn_id": "t2",
            "turn_no": 2,
            "main_topic": "topic-b",
            "narrative": "target narrative",
            "source_refs": ["b:2"],
            "tools_used": [],
        },
        "coarse_recall_signals": ["vector_topk", "same_session_adjacent"],
        "signal_reasons": ["cross_session_semantic_topk:6", "adjacent_turn"],
        "signal_scores": {"vector_topk": 0.91, "same_session_adjacent": 1.0},
        "allowed_source_refs": ["a:1", "b:2"],
        "allowed_session_ids": ["s1", "s2"],
        "allowed_turn_ids": ["t1", "t2"],
        "allowed_event_ids": [],
    }


class TestGraphRelationCandidatesV2(unittest.TestCase):
    def test_detect_llm_status_without_api_key(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            status, live = mod.detect_llm_status()
        self.assertEqual(status, "fallback:no_api_key")
        self.assertFalse(live)

    def test_blocked_row_for_package_uses_blocked_status(self):
        row = mod.blocked_row_for_package(
            make_package(),
            "fallback:no_api_key",
            model="gpt-test",
            temperature=0.2,
            reason="no api key",
        )
        self.assertEqual(row["proposal_status"], "blocked")
        self.assertEqual(row["llm_status"], "fallback:no_api_key")
        self.assertEqual(row["proposed_relation_type"], "no_relation")
        self.assertEqual(json.loads(row["source_refs_json"]), ["a:1", "b:2"])

    def test_validate_proposal_fields_rejects_unknown_refs(self):
        proposal = {
            "candidate_id": "grcp:test",
            "candidate_type": "semantic_relation_candidate",
            "source_node_id": "s1#t1",
            "target_node_id": "s2#t2",
            "proposed_relation_type": "follow_up",
            "proposal_status": "proposed",
            "why_candidate": "有追问关系，但只是候选。",
            "evidence_refs": ["missing:9"],
            "source_refs": ["a:1", "b:2"],
            "event_ids": [],
            "session_ids": ["s1", "s2"],
            "turn_ids": ["t1", "t2"],
            "risk_flags": [],
            "needs_human_review": False,
        }
        normalized, schema_error, evidence_error = mod.validate_proposal_fields(proposal, make_package())
        self.assertIsNone(normalized)
        self.assertIsNone(schema_error)
        self.assertIn("outside package", evidence_error)

    def test_normalize_llm_response_counts_schema_rejection(self):
        rows, schema_rejected, evidence_rejected = mod.normalize_llm_response(
            {"package_id": "wrong", "candidate_proposals": []},
            make_package(),
            "live_api_key_present",
            model="gpt-test",
            temperature=0.2,
        )
        self.assertEqual(schema_rejected, 1)
        self.assertEqual(evidence_rejected, 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["proposal_status"], "reject")

    def test_graph_candidate_row_only_written_for_proposed_with_refs(self):
        package = make_package()
        proposal_row = mod.build_audit_row(
            package=package,
            source_node_id="s1#t1",
            target_node_id="s2#t2",
            relation_type="follow_up",
            proposal_status="proposed",
            candidate_type="semantic_relation_candidate",
            why_candidate="source turn 触发 target turn 的后续动作，但仍需后续判边。",
            evidence_refs=["a:1", "b:2"],
            source_refs=["a:1", "b:2"],
            risk_flags=[],
            event_ids=[],
            session_ids=["s1", "s2"],
            turn_ids=["t1", "t2"],
            needs_human_review=False,
            model="gpt-test",
            temperature=0.2,
            llm_status="live_api_key_present",
        )
        turn_map = {
            "s1#t1": {"session_id": "s1", "turn_id": "t1"},
            "s2#t2": {"session_id": "s2", "turn_id": "t2"},
        }
        row = mod.graph_candidate_row_from_proposal(
            proposal_row,
            turn_map,
            {package["package_id"]: package},
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["candidate_type"], "semantic_candidate_v2")
        self.assertEqual(row["source_session_id"], "s1")
        self.assertEqual(row["target_session_id"], "s2")

    def test_graph_candidate_row_rejects_non_proposed(self):
        package = make_package()
        proposal_row = mod.blocked_row_for_package(
            package,
            "fallback:no_api_key",
            model="gpt-test",
            temperature=0.2,
            reason="no api key",
        )
        turn_map = {
            "s1#t1": {"session_id": "s1", "turn_id": "t1"},
            "s2#t2": {"session_id": "s2", "turn_id": "t2"},
        }
        row = mod.graph_candidate_row_from_proposal(
            proposal_row,
            turn_map,
            {package["package_id"]: package},
        )
        self.assertIsNone(row)


if __name__ == "__main__":
    unittest.main(verbosity=2)
