"""Phase 09 Wave 5 promotion review gate tests."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "integration" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import apply_memory_promotions as apply_mod  # noqa: E402
import evaluate_memory_promotion_candidates as eval_mod  # noqa: E402


class TestMemoryPromotionReview(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)
        self.db_path = self.tmp_path / "test.sqlite"
        self.report_json = self.tmp_path / "report.json"
        self.report_md = self.tmp_path / "report.md"
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
                CREATE TABLE graph_relation_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    source_node_id TEXT,
                    target_node_id TEXT
                );
                CREATE TABLE graph_relation_judgments (
                    candidate_id TEXT PRIMARY KEY,
                    relation_type TEXT
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
            con.execute("INSERT INTO graph_relation_candidates VALUES ('c1','n1','n2')")
            con.execute("INSERT INTO graph_relation_judgments VALUES ('c1','preference_signal')")
            con.executemany(
                """
                INSERT INTO conversation_turns_summary
                (id, session_id, turn_no, turn_id, narrative, tools_used, source_ref, main_topic)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                [
                    (1, "s1", 1, "t1", "用户稳定偏好中文输出和结论先说。", "", "source-a:1", "输出风格"),
                    (2, "s2", 1, "t2", "另一会话再次确认默认中文输出。", "", "source-b:1", "输出风格"),
                ],
            )
            self._insert_candidate(
                con,
                promotion_id="p-review",
                source_system="llm_memory_candidate",
                relation_type="preference_signal",
                claim="用户稳定偏好中文输出和结论先说",
                confidence=0.9,
                upstream_status="needs_live_llm_review",
                source_refs=json.dumps(
                    [
                        {"table": "memory_items", "memory_id": "m1"},
                        {"table": "graph_relation_candidates", "candidate_id": "c1"},
                        "Agent/sessions/example.jsonl:4",
                    ],
                    ensure_ascii=False,
                ),
            )
            self._insert_candidate(
                con,
                promotion_id="p-one-time",
                source_system="llm_memory_candidate",
                relation_type="same_problem",
                claim="同一具体任务的需求与解法",
                confidence=0.95,
                upstream_status="reject_or_review",
            )
            self._insert_candidate(
                con,
                promotion_id="p-bad-ref",
                source_system="llm_memory_candidate",
                relation_type="preference_signal",
                claim="证据格式损坏",
                confidence=0.95,
                upstream_status="needs_live_llm_review",
                evidence_refs="not-json",
            )
            self._insert_candidate(
                con,
                promotion_id="p-auto",
                source_system="llm_memory_candidate",
                relation_type="preference_signal",
                claim="用户在多个会话中稳定要求默认中文输出，并希望结论先说。",
                confidence=0.92,
                upstream_status="proposed",
                evidence_refs=json.dumps(
                    [
                        {"table": "unified_events_rich", "event_id": "e1"},
                        {"table": "conversation_turns_summary", "session_id": "s1", "turn_no": 1, "turn_id": "t1"},
                        {"table": "conversation_turns_summary", "session_id": "s2", "turn_no": 1, "turn_id": "t2"},
                    ],
                    ensure_ascii=False,
                ),
                source_refs=json.dumps(
                    [
                        {"table": "conversation_turns_summary", "session_id": "s1", "turn_no": 1, "turn_id": "t1"},
                        {"table": "conversation_turns_summary", "session_id": "s2", "turn_no": 1, "turn_id": "t2"},
                        "source-a:1",
                        "source-b:1",
                    ],
                    ensure_ascii=False,
                ),
            )
            self._insert_candidate(
                con,
                promotion_id="p-inactive-source",
                source_system="historical_candidate_source",
                relation_type="preference_signal",
                claim="历史候选来源不应再被视为 active promotion source。",
                confidence=0.8,
                upstream_status="review_required",
            )
            con.commit()

    def _insert_candidate(
        self,
        con: sqlite3.Connection,
        *,
        promotion_id: str,
        source_system: str,
        relation_type: str,
        claim: str,
        confidence: float,
        upstream_status: str,
        evidence_refs: object | None = None,
        source_refs: object | None = None,
    ) -> None:
        refs = evidence_refs if evidence_refs is not None else json.dumps([{"table": "unified_events_rich", "event_id": "e1"}])
        src = source_refs if source_refs is not None else json.dumps(
            [
                {"table": "conversation_turns_summary", "session_id": "s1", "turn_no": 1, "turn_id": "t1"},
                "source-a:1",
            ],
            ensure_ascii=False,
        )
        con.execute(
            """
            INSERT INTO memory_promotion_candidates VALUES
            (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                promotion_id,
                source_system,
                "c1",
                None,
                "s1",
                "t1",
                relation_type,
                "preference",
                "user",
                claim,
                confidence,
                refs,
                src,
                None,
                None,
                upstream_status,
                "test",
                "2026-07-01T00:00:00Z",
            ),
        )

    def test_no_api_key_never_auto_approves_and_preserves_score_fields(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "", "MEM0_API_KEY": ""}, clear=False):
            with closing(sqlite3.connect(self.db_path)) as con:
                con.row_factory = sqlite3.Row
                report = eval_mod.build_report(con, llm_status="fallback:no_api_key")

        self.assertEqual(report["approved_count"], 0)
        self.assertEqual(report["auto_approval_eligible_count"], 0)
        review = {item["promotion_id"]: item for item in report["reviews"]}["p-review"]
        self.assertEqual(review["promotion_status"], "review_required")
        self.assertTrue(review["human_review_required"])
        self.assertFalse(review["auto_approval_eligible"])
        self.assertIn("no_live_llm", review["risk_flags"])
        self.assertIn("score_components", review)
        self.assertIn("evidence_completeness", review["score_components"])
        self.assertGreater(review["final_score"], 0.60)

    def test_one_time_and_bad_refs_are_hard_risk_rejected(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as con:
            con.row_factory = sqlite3.Row
            report = eval_mod.build_report(con, llm_status="fallback:no_api_key")

        reviews = {item["promotion_id"]: item for item in report["reviews"]}
        self.assertEqual(reviews["p-one-time"]["promotion_status"], "rejected")
        self.assertTrue(reviews["p-one-time"]["hard_risk_blocked"])
        self.assertIn("one_time_task", reviews["p-one-time"]["hard_risk_flags"])
        self.assertEqual(reviews["p-bad-ref"]["promotion_status"], "rejected")
        self.assertTrue(reviews["p-bad-ref"]["hard_risk_blocked"])
        self.assertIn("schema_invalid", reviews["p-bad-ref"]["hard_risk_flags"])

    def test_inactive_candidate_source_is_soft_blocked_without_legacy_literal(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as con:
            con.row_factory = sqlite3.Row
            report = eval_mod.build_report(con, llm_status="fallback:no_api_key")

        reviews = {item["promotion_id"]: item for item in report["reviews"]}
        inactive = reviews["p-inactive-source"]
        self.assertIn("inactive_candidate_source", inactive["risk_flags"])
        self.assertNotIn("legacy_candidate_source", inactive["risk_flags"])

    def test_live_llm_with_multi_session_traceability_can_be_auto_approved(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as con:
            con.row_factory = sqlite3.Row
            report = eval_mod.build_report(con, llm_status="live_api_key_present")

        reviews = {item["promotion_id"]: item for item in report["reviews"]}
        auto = reviews["p-auto"]
        self.assertEqual(auto["promotion_status"], "approved")
        self.assertFalse(auto["human_review_required"])
        self.assertTrue(auto["auto_approval_eligible"])
        self.assertGreaterEqual(auto["final_score"], 0.85)
        self.assertEqual(auto["hard_risk_flags"], [])

    def test_write_report_outputs_weighted_gate_summary(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as con:
            con.row_factory = sqlite3.Row
            report = eval_mod.build_report(con, llm_status="fallback:no_api_key")
        eval_mod.write_report(report, self.report_json, self.report_md)

        saved = json.loads(self.report_json.read_text(encoding="utf-8"))
        self.assertIn("auto_approval_eligible_count", saved)
        self.assertEqual(saved["approved_count"], 0)
        md = self.report_md.read_text(encoding="utf-8")
        self.assertIn("Hard Risk Flags", md)
        self.assertIn("Why Approved Is 0", md)

    def test_apply_dry_run_approved_only_uses_auto_approval_eligibility(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as con:
            con.row_factory = sqlite3.Row
            report = eval_mod.build_report(con, llm_status="fallback:no_api_key")
        eval_mod.write_report(report, self.report_json, self.report_md)

        preview = apply_mod.run(
            db_path=self.db_path,
            report_path=self.report_json,
            dry_run=True,
            write=False,
            approved_only=True,
        )

        self.assertEqual(preview["eligible_count"], 0)
        self.assertFalse(preview["long_term_tables_changed"])
        self.assertEqual(preview["before_counts"], preview["after_counts"])
        self.assertEqual(preview["before_counts"], {"memory_items": 1, "memory_links": 1, "memory_relations": 1})

    def test_apply_preview_reports_custom_report_path(self) -> None:
        custom_report = self.tmp_path / "custom-promotion-report.json"
        custom_md = self.tmp_path / "custom-promotion-report.md"
        with closing(sqlite3.connect(self.db_path)) as con:
            con.row_factory = sqlite3.Row
            report = eval_mod.build_report(con, llm_status="fallback:no_api_key")
        eval_mod.write_report(report, custom_report, custom_md)

        preview = apply_mod.run(
            db_path=self.db_path,
            report_path=custom_report,
            dry_run=True,
            write=False,
            approved_only=True,
        )

        self.assertEqual(preview["report_path"], apply_mod.rel(custom_report))


if __name__ == "__main__":
    unittest.main(verbosity=2)
