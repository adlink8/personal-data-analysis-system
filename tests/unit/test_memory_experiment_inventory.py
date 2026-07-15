"""Wave 1 inventory 的纯逻辑测试。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNIFIED_SCRIPTS = ROOT / "integration" / "scripts"
if str(UNIFIED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(UNIFIED_SCRIPTS))

import personal_knowledge.domains.memory.audit_memory_experiments as mod  # noqa: E402


class TestMemoryExperimentInventory(unittest.TestCase):
    def test_classify_object_status_marks_review_queue_as_remove_candidate_without_reader(self):
        status = mod.classify_object_status("graph_relation_review_queue", readers=[], writers=["writer.py"])
        self.assertEqual(status, "remove_candidate")

    def test_classify_object_status_keeps_other_objects_active(self):
        status = mod.classify_object_status("memory_items", readers=["reader.py"], writers=["writer.py"])
        self.assertEqual(status, "active")

    def test_compute_overall_status_prefers_blocked_over_degraded(self):
        status = mod.compute_overall_status(
            [
                {"status": "healthy"},
                {"status": "degraded"},
                {"status": "blocked"},
            ]
        )
        self.assertEqual(status, "blocked")

    def test_compute_overall_status_marks_degraded_when_any_store_degraded(self):
        status = mod.compute_overall_status(
            [
                {"status": "healthy"},
                {"status": "degraded"},
            ]
        )
        self.assertEqual(status, "degraded")


if __name__ == "__main__":
    unittest.main(verbosity=2)
