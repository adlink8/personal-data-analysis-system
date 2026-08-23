"""Phase 08 Wave 2 mechanism matrix tests."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "integration" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import personal_knowledge.evaluation.memory.analyze_memory_mechanisms as mod  # noqa: E402


class TestMemoryMechanismAnalysis(unittest.TestCase):
    def test_matrix_has_required_steps_in_order(self) -> None:
        rows = mod.build_mechanism_matrix(llm_status="fallback:no_api_key")
        self.assertEqual([row["mechanism_step"] for row in rows], mod.MECHANISM_STEPS)

    def test_each_row_has_required_fields_and_evidence(self) -> None:
        rows = mod.build_mechanism_matrix(llm_status="fallback:no_api_key")
        for row in rows:
            for field in mod.REQUIRED_ROW_FIELDS:
                self.assertIn(field, row)
            self.assertTrue(row["evidence_refs"], row["mechanism_step"])
            self.assertTrue(row["source_files"], row["mechanism_step"])
            self.assertEqual(row["prompt_version"], mod.PROMPT_VERSION)
            self.assertEqual(row["llm_status"], "fallback:no_api_key")

    def test_no_api_key_status_is_explicit_fallback(self) -> None:
        with patch.dict(os.environ, {"OPENAI_API_KEY": "", "MEM0_API_KEY": ""}, clear=False):
            self.assertEqual(mod.detect_llm_status(use_llm=False), "fallback:no_api_key")

    def test_report_declares_legacy_comparison_not_main_output(self) -> None:
        report = mod.build_report(llm_status="fallback:no_api_key")
        self.assertEqual(
            report["legacy_comparison_disposition"]["status"],
            "old_scope_counterexample_not_main_output",
        )
        md = mod.render_matrix_md(report)
        self.assertIn("legacy-scope counterexamples", md)
        self.assertIn("not used as the main Wave 2 conclusion", md)

    def test_target_pipeline_is_single_pipeline_not_record_ranking(self) -> None:
        report = mod.build_report(llm_status="fallback:no_api_key")
        pipeline = report["target_pipeline"]
        self.assertEqual(pipeline["name"], "target_memory_pipeline_v1")
        self.assertGreaterEqual(len(pipeline["ordered_stages"]), 5)
        rendered = mod.render_target_design_md(report)
        self.assertIn("single auditable memory pipeline", rendered)
        self.assertNotIn("Old Memory Decisions", rendered)
        self.assertNotIn("Accepted Graph Edge Decisions", rendered)


if __name__ == "__main__":
    unittest.main(verbosity=2)
