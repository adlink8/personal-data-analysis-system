"""Phase 09 Wave 5 gate repair loop tests."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "integration" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import personal_knowledge.domains.memory.evaluate_memory_promotion_candidates as eval_mod  # noqa: E402
import personal_knowledge.domains.memory.repair_memory_promotion_candidates as repair_mod  # noqa: E402


class TestMemoryGateRepairLoop(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)
        self.db_path = self.tmp_path / "test.sqlite"
        self.promotion_report_json = self.tmp_path / "memory_promotion_report.json"
        self.promotion_report_md = self.tmp_path / "memory_promotion_report.md"
        self.repair_report_json = self.tmp_path / "memory_gate_repair_report.json"
        self.repair_report_md = self.tmp_path / "memory_gate_repair_report.md"
        self._write_db()

    def _write_db(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as con:
            con.executescript(
                """
                CREATE TABLE memory_items (
                    memory_id TEXT PRIMARY KEY,
                    memory_type TEXT NOT NULL,
                    memory_subtype TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    description TEXT NOT NULL,
                    confidence REAL DEFAULT 0.5,
                    evidence_count INTEGER DEFAULT 0,
                    metadata TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE memory_links (
                    id INTEGER PRIMARY KEY,
                    memory_id TEXT NOT NULL,
                    target_type TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    relation TEXT NOT NULL
                );
                CREATE TABLE memory_relations (
                    id INTEGER PRIMARY KEY,
                    from_memory_id TEXT NOT NULL,
                    to_memory_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    strength REAL DEFAULT 1.0
                );
                CREATE TABLE unified_events_rich (
                    event_id TEXT PRIMARY KEY,
                    content_rich TEXT,
                    content_rich_source TEXT
                );
                CREATE TABLE conversation_turns_summary (
                    id INTEGER PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    turn_no INTEGER NOT NULL,
                    turn_id TEXT,
                    narrative TEXT NOT NULL,
                    tools_used TEXT,
                    source_ref TEXT,
                    main_topic TEXT
                );
                CREATE TABLE memory_promotion_candidates (
                    promotion_id TEXT PRIMARY KEY,
                    source_system TEXT NOT NULL,
                    source_candidate_id TEXT,
                    source_memory_id TEXT,
                    session_id TEXT,
                    turn_id TEXT,
                    relation_type TEXT,
                    proposed_memory_type TEXT NOT NULL,
                    proposed_subject TEXT NOT NULL,
                    proposed_claim TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_refs_json TEXT NOT NULL,
                    source_refs_json TEXT NOT NULL,
                    duplicate_of_memory_id TEXT,
                    conflict_with_memory_id TEXT,
                    promotion_status TEXT NOT NULL,
                    review_reason TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            con.execute(
                """
                INSERT INTO memory_items VALUES
                ('m1','preference','output','user','用户偏好中文输出',0.8,1,'{}','2026-01-01')
                """
            )
            con.execute("INSERT INTO memory_links VALUES (1,'m1','event','e1','evidenced_by')")
            con.execute("INSERT INTO memory_relations VALUES (1,'m1','m1','related',1.0)")
            con.execute("INSERT INTO unified_events_rich VALUES ('e1','用户偏好中文输出','test')")
            con.execute(
                """
                INSERT INTO conversation_turns_summary
                VALUES (1,'s1',1,'t1','用户稳定偏好中文输出和结论先说。','', 'source-a:1','输出风格')
                """
            )
            con.execute(
                """
                INSERT INTO memory_promotion_candidates VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    "p-review",
                    "llm_memory_candidate",
                    "cand-1",
                    None,
                    "s1",
                    "t1",
                    "preference_signal",
                    "preference",
                    "user",
                    "用户稳定偏好中文输出和结论先说",
                    0.9,
                    json.dumps([{"table": "unified_events_rich", "event_id": "e1"}], ensure_ascii=False),
                    json.dumps(
                        [
                            {"table": "conversation_turns_summary", "session_id": "s1", "turn_no": 1, "turn_id": "t1"},
                            "source-a:1",
                        ],
                        ensure_ascii=False,
                    ),
                    None,
                    None,
                    "needs_live_llm_review",
                    "test",
                    "2026-07-01T00:00:00Z",
                ),
            )
            con.commit()

    def _write_promotion_report(self, *, llm_status: str) -> dict[str, object]:
        with closing(sqlite3.connect(self.db_path)) as con:
            con.row_factory = sqlite3.Row
            report = eval_mod.build_report(con, llm_status=llm_status)
        eval_mod.write_report(report, self.promotion_report_json, self.promotion_report_md)
        return report

    def test_run_without_live_llm_is_blocked_and_repairs_nothing(self) -> None:
        self._write_promotion_report(llm_status="fallback:no_api_key")

        with patch.dict("os.environ", {}, clear=True):
            report = repair_mod.run(
                db_path=self.db_path,
                promotion_report_json=self.promotion_report_json,
                report_json=self.repair_report_json,
                report_md=self.repair_report_md,
                dry_run=True,
                write=False,
                limit=10,
            )

        self.assertEqual(report["llm_status"], "blocked:no_live_llm")
        self.assertEqual(report["counts"]["repair_count"], 0)
        self.assertEqual(report["counts"]["downgrade_count"], 0)
        self.assertEqual(report["counts"]["reject_count"], 0)
        self.assertEqual(report["counts"]["blocked_count"], 1)
        self.assertEqual(report["candidate_results"][0]["status"], "blocked")
        self.assertTrue(self.repair_report_json.exists())
        self.assertTrue(self.repair_report_md.exists())

    def test_validate_repair_output_rejects_new_refs_outside_candidate_input(self) -> None:
        source_report = self._write_promotion_report(llm_status="fallback:no_api_key")
        review = source_report["reviews"][0]
        payload = repair_mod.build_repair_payload(review)
        parsed = {
            "prompt_version": repair_mod.PROMPT_VERSION,
            "model": "gpt-test",
            "temperature": 0.0,
            "llm_status": "live_api_key_present",
            "candidate_kind": "memory_candidate",
            "candidate_id": review["promotion_id"],
            "repair_action": "downgrade",
            "repaired_status": "needs_human_review",
            "kept_evidence_refs": ["outside:1"],
            "kept_source_refs": ["source-a:1"],
            "event_ids": [],
            "session_ids": ["s1"],
            "turn_ids": ["t1"],
            "repaired_fields": {"needs_human_review": True},
            "unresolved_gate_reasons": ["no_live_llm"],
            "repair_reason": "不能新增输入外 refs。",
        }

        validated, error = repair_mod.validate_repair_output(parsed, payload, review)
        self.assertIsNone(validated)
        self.assertIn("outside the candidate input", error)

    def test_validate_repair_output_accepts_original_ref_objects_from_candidate_input(self) -> None:
        source_report = self._write_promotion_report(llm_status="fallback:no_api_key")
        review = source_report["reviews"][0]
        payload = repair_mod.build_repair_payload(review)
        parsed = {
            "prompt_version": repair_mod.PROMPT_VERSION,
            "model": "gpt-test",
            "temperature": 0.0,
            "llm_status": "live_api_key_present",
            "candidate_kind": "memory_candidate",
            "candidate_id": review["promotion_id"],
            "repair_action": "downgrade",
            "repaired_status": "needs_human_review",
            "kept_evidence_refs": [{"table": "unified_events_rich", "event_id": "e1"}],
            "kept_source_refs": [
                {"table": "conversation_turns_summary", "session_id": "s1", "turn_no": 1, "turn_id": "t1"},
                "source-a:1",
            ],
            "event_ids": ["e1"],
            "session_ids": ["s1"],
            "turn_ids": ["t1"],
            "repaired_fields": {"needs_human_review": True},
            "unresolved_gate_reasons": ["no_live_llm"],
            "repair_reason": "保留输入中的原始 ref 对象并降级。",
        }

        validated, error = repair_mod.validate_repair_output(parsed, payload, review)
        self.assertIsNotNone(validated)
        self.assertIsNone(error)

    def test_validate_repair_output_rejects_raised_final_score(self) -> None:
        source_report = self._write_promotion_report(llm_status="fallback:no_api_key")
        review = source_report["reviews"][0]
        payload = repair_mod.build_repair_payload(review)
        parsed = {
            "prompt_version": repair_mod.PROMPT_VERSION,
            "model": "gpt-test",
            "temperature": 0.0,
            "llm_status": "live_api_key_present",
            "candidate_kind": "memory_candidate",
            "candidate_id": review["promotion_id"],
            "repair_action": "downgrade",
            "repaired_status": "needs_human_review",
            "kept_evidence_refs": ["unified_events_rich:event_id/e1"],
            "kept_source_refs": ["conversation_turns_summary:turn_id/t1", "source-a:1"],
            "event_ids": ["e1"],
            "session_ids": ["s1"],
            "turn_ids": ["t1"],
            "repaired_fields": {"final_score": float(review["final_score"]) + 0.01},
            "unresolved_gate_reasons": ["no_live_llm"],
            "repair_reason": "不能提高 gate 分数。",
        }

        validated, error = repair_mod.validate_repair_output(parsed, payload, review)
        self.assertIsNone(validated)
        self.assertIn("cannot raise final_score", error)

    def test_live_llm_downgrade_output_is_accepted(self) -> None:
        source_report = self._write_promotion_report(llm_status="fallback:no_api_key")
        review = source_report["reviews"][0]
        runtime = repair_mod.LLMRuntime(
            llm_status="live_api_key_present",
            model="gpt-test",
            temperature=0.0,
            client=object(),
        )
        parsed = {
            "prompt_version": repair_mod.PROMPT_VERSION,
            "model": "gpt-test",
            "temperature": 0.0,
            "llm_status": "live_api_key_present",
            "candidate_kind": "memory_candidate",
            "candidate_id": review["promotion_id"],
            "repair_action": "downgrade",
            "repaired_status": "needs_human_review",
            "kept_evidence_refs": ["unified_events_rich:event_id/e1"],
            "kept_source_refs": ["conversation_turns_summary:turn_id/t1", "source-a:1"],
            "event_ids": ["e1"],
            "session_ids": ["s1"],
            "turn_ids": ["t1"],
            "repaired_fields": {
                "canonical_claim": "用户偏好中文输出，但仍需人工复核。",
                "needs_human_review": True,
                "risk_flags": ["no_live_llm"],
            },
            "unresolved_gate_reasons": ["no_live_llm", "upstream_requires_review"],
            "repair_reason": "证据不足以自动通过，只能降级到人工复核。",
        }

        with patch.object(repair_mod, "resolve_llm_runtime", return_value=runtime), patch.object(
            repair_mod, "call_llm", return_value=parsed
        ):
            report = repair_mod.run(
                db_path=self.db_path,
                promotion_report_json=self.promotion_report_json,
                report_json=self.repair_report_json,
                report_md=self.repair_report_md,
                dry_run=True,
                write=False,
                limit=10,
                model="gpt-test",
                temperature=0.0,
            )

        self.assertEqual(report["llm_status"], "live_api_key_present")
        self.assertEqual(report["counts"]["repair_count"], 0)
        self.assertEqual(report["counts"]["downgrade_count"], 1)
        self.assertEqual(report["counts"]["reject_count"], 0)
        self.assertEqual(report["candidate_results"][0]["status"], "downgrade")
        self.assertEqual(report["candidate_results"][0]["repair_action"], "downgrade")

    def test_live_llm_schema_candidate_claim_field_is_accepted(self) -> None:
        source_report = self._write_promotion_report(llm_status="fallback:no_api_key")
        review = source_report["reviews"][0]
        runtime = repair_mod.LLMRuntime(
            llm_status="live_api_key_present",
            model="gpt-test",
            temperature=0.0,
            client=object(),
        )
        parsed = {
            "prompt_version": repair_mod.PROMPT_VERSION,
            "model": "gpt-test",
            "temperature": 0.0,
            "llm_status": "live_api_key_present",
            "candidate_kind": "memory_candidate",
            "candidate_id": review["promotion_id"],
            "repair_action": "downgrade",
            "repaired_status": "needs_human_review",
            "kept_evidence_refs": ["unified_events_rich:event_id/e1"],
            "kept_source_refs": ["conversation_turns_summary:turn_id/t1", "source-a:1"],
            "event_ids": ["e1"],
            "session_ids": ["s1"],
            "turn_ids": ["t1"],
            "repaired_fields": {
                "candidate_claim": "用户可能偏好中文输出，但证据仍需人工复核。",
                "needs_human_review": True,
                "risk_flags": ["no_live_llm"],
            },
            "unresolved_gate_reasons": ["no_live_llm", "upstream_requires_review"],
            "repair_reason": "按 schema 示例输出 candidate_claim，并降级到人工复核。",
        }

        with patch.object(repair_mod, "resolve_llm_runtime", return_value=runtime), patch.object(
            repair_mod, "call_llm", return_value=parsed
        ):
            report = repair_mod.run(
                db_path=self.db_path,
                promotion_report_json=self.promotion_report_json,
                report_json=self.repair_report_json,
                report_md=self.repair_report_md,
                dry_run=True,
                write=False,
                limit=10,
                model="gpt-test",
                temperature=0.0,
            )

        self.assertEqual(report["counts"]["downgrade_count"], 1)
        self.assertEqual(
            report["candidate_results"][0]["repair_output"]["repaired_fields"]["candidate_claim"],
            "用户可能偏好中文输出，但证据仍需人工复核。",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
