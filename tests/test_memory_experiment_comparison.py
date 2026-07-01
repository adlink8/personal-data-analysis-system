"""Wave 2 comparison 的纯逻辑测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNIFIED_SCRIPTS = ROOT / "integration" / "scripts"
if str(UNIFIED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(UNIFIED_SCRIPTS))

import compare_memory_experiments as mod  # noqa: E402


class TestMemoryExperimentComparison(unittest.TestCase):
    def test_choose_old_memory_sample_round_robins_by_type(self):
        rows = [
            {"memory_id": "a1", "memory_type": "capability"},
            {"memory_id": "a2", "memory_type": "capability"},
            {"memory_id": "b1", "memory_type": "preference"},
            {"memory_id": "b2", "memory_type": "preference"},
            {"memory_id": "c1", "memory_type": "tooling"},
        ]
        picked = mod.choose_old_memory_sample(rows, 4)
        self.assertEqual([row["memory_id"] for row in picked], ["a1", "b1", "c1", "a2"])

    def test_extract_json_handles_fenced_payload(self):
        parsed = mod.extract_json("```json\n{\"record_kind\":\"old_memory_sample\"}\n```")
        self.assertEqual(parsed["record_kind"], "old_memory_sample")

    def test_normalize_result_filters_invalid_refs(self):
        payload = {
            "record_kind": "accepted_graph_edge",
            "focus": {"new_candidate_id": "c1"},
            "allowed_evidence_refs": ["ref:1", "ref:2"],
        }
        parsed = {
            "record_kind": "accepted_graph_edge",
            "new_candidate_id": "c1",
            "judgment": "graph_promotion_candidate",
            "long_term_value_score": 9,
            "duplicate_status": "distinct",
            "conflict_status": "no_conflict",
            "recommended_action": "promote_candidate",
            "dimension_scores": {"evidence_coverage": 5},
            "evidence_refs": ["bad:9"],
            "reason": "x",
            "risk_flags": [],
        }
        out = mod.normalize_result(parsed, payload, "live", "gpt-5.4", 0.1)
        self.assertEqual(out["evidence_refs"], ["ref:1", "ref:2"])
        self.assertIn("invalid_evidence_refs_filtered", out["risk_flags"])

    def test_fallback_decision_marks_non_live_status(self):
        payload = {
            "record_kind": "old_memory_sample",
            "focus": {
                "old_memory_id": "m1",
                "memory_type": "tooling",
                "memory_link_evidence": [{"evidence_ref": "unified_events:e1"}],
                "evidence_count": 12,
            },
            "graph_context": [],
            "allowed_evidence_refs": ["unified_events:e1"],
        }
        out = mod.fallback_decision(payload, "fallback:no_api_key", "gpt-5.4", 0.1)
        self.assertEqual(out["llm_status"], "fallback:no_api_key")
        self.assertNotEqual(out["recommended_action"], "promote_candidate")


if __name__ == "__main__":
    unittest.main(verbosity=2)
