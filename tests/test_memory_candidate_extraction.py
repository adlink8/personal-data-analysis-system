"""Phase 09 Wave 4 memory candidate extraction tests."""

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

import extract_memory_candidates_from_bundles as mod  # noqa: E402


class TestMemoryCandidateExtraction(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "test.sqlite"
        self.report_json = Path(self.tmp.name) / "report.json"
        self.report_md = Path(self.tmp.name) / "report.md"
        self._write_db()

    def _write_db(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as con:
            con.executescript(
                f"""
                CREATE TABLE memory_evidence_bundles (
                    bundle_id TEXT PRIMARY KEY,
                    bundle_type TEXT NOT NULL,
                    source_system TEXT NOT NULL,
                    bundle_label TEXT NOT NULL,
                    bundle_summary TEXT NOT NULL,
                    primary_ref TEXT NOT NULL,
                    evidence_refs_json TEXT NOT NULL,
                    source_refs_json TEXT NOT NULL,
                    duplicate_check_targets_json TEXT NOT NULL,
                    conflict_check_targets_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
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
                CREATE TABLE unified_events_rich (
                    event_id TEXT PRIMARY KEY,
                    content_rich TEXT,
                    content_rich_source TEXT
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
                INSERT INTO conversation_turns_summary VALUES
                (1,'sess-1',1,'t1','用户要求默认中文输出，且结论先说。','', 'source-a:1','输出风格')
                """
            )
            con.execute(
                """
                INSERT INTO unified_events_rich VALUES
                ('evt-1','用户要求默认中文输出，且结论先说。','source-event:1')
                """
            )
            con.execute(
                f"""
                INSERT INTO memory_evidence_bundles VALUES
                ('meb-turn','conversation_turn','conversation_turn','sess-1:t1','用户要求默认中文输出，且结论先说。','source-a:1',?,?,?,?, '2026-07-01T00:00:00Z')
                """,
                (
                    json.dumps(
                        [
                            {
                                "table": "conversation_turns_summary",
                                "session_id": "sess-1",
                                "turn_no": 1,
                                "turn_id": "t1",
                                "main_topic": "输出风格",
                                "excerpt": "用户要求默认中文输出，且结论先说。",
                            }
                        ],
                        ensure_ascii=False,
                    ),
                    json.dumps(
                        [
                            "source-a:1",
                            {
                                "table": "conversation_turns_summary",
                                "session_id": "sess-1",
                                "turn_no": 1,
                                "turn_id": "t1",
                            },
                        ],
                        ensure_ascii=False,
                    ),
                    json.dumps(["mem-dup-1"], ensure_ascii=False),
                    json.dumps(["mem-conflict-1"], ensure_ascii=False),
                ),
            )
            con.execute(
                """
                INSERT INTO memory_promotion_candidates VALUES
                ('existing-graph','graph_relation_candidate','grcand-1',NULL,'sess-0','t0',NULL,'project','project','已有图谱候选',0.8,'[]','[]',NULL,NULL,'review_required','keep existing graph candidate','2026-07-01T00:00:00Z')
                """
            )
            con.commit()

    def _load_first_bundle(self) -> dict[str, object]:
        with closing(sqlite3.connect(self.db_path)) as con:
            con.row_factory = sqlite3.Row
            bundles = mod.load_bundle_inputs(con, limit=1)
        return bundles[0]

    def test_run_write_blocks_without_live_llm_and_keeps_existing_candidates(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            report = mod.run(
                db_path=self.db_path,
                report_json=self.report_json,
                report_md=self.report_md,
                write=True,
                limit=10,
            )

        self.assertEqual(report["llm_status"], "blocked:no_live_llm")
        self.assertEqual(report["counts"]["bundle_count"], 1)
        self.assertEqual(report["counts"]["candidate_count"], 0)
        self.assertEqual(report["counts"]["written_count"], 0)
        self.assertTrue(report["blocked_reason"])
        self.assertTrue(self.report_json.exists())
        self.assertTrue(self.report_md.exists())
        with closing(sqlite3.connect(self.db_path)) as con:
            counts = con.execute(
                "SELECT source_system, COUNT(*) FROM memory_promotion_candidates GROUP BY source_system ORDER BY source_system"
            ).fetchall()
        self.assertEqual(counts, [("graph_relation_candidate", 1)])

    def test_validate_claim_fields_rejects_refs_outside_bundle_input(self) -> None:
        bundle = self._load_first_bundle()
        claim = {
            "candidate_id": "mcc-1",
            "candidate_claim": "用户偏好默认中文输出。",
            "memory_type": "preference",
            "subject": "user",
            "extraction_status": "proposed",
            "long_term_value_reason": "这是稳定输出风格偏好。",
            "one_time_task_risk": "low",
            "duplicate_check_hint": "",
            "conflict_check_hint": "",
            "evidence_refs": ["missing:9"],
            "source_refs": ["source-a:1"],
            "event_ids": [],
            "session_ids": ["sess-1"],
            "turn_ids": ["t1"],
            "confidence": 0.88,
            "risk_flags": [],
            "needs_human_review": False,
        }

        normalized, schema_error, evidence_error = mod.validate_claim_fields(claim, bundle)
        self.assertIsNone(normalized)
        self.assertIsNone(schema_error)
        self.assertIn("outside bundle input", evidence_error)

    def test_parse_hint_memory_id_does_not_guess_when_hint_has_no_id(self) -> None:
        self.assertIsNone(mod.parse_hint_memory_id("可能重复但不确定", ["mem-dup-1", "mem-dup-2"]))
        self.assertEqual(mod.parse_hint_memory_id("duplicate of mem-dup-2", ["mem-dup-1", "mem-dup-2"]), "mem-dup-2")

    def test_run_write_live_call_failure_preserves_existing_llm_candidates(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as con:
            con.execute(
                """
                INSERT INTO memory_promotion_candidates VALUES
                ('existing-llm','llm_memory_candidate','mcc-old',NULL,'sess-old','t-old',NULL,'preference','user','已有 LLM 候选',0.8,'[]','[]',NULL,NULL,'review_required','keep existing llm candidate','2026-07-01T00:00:00Z')
                """
            )
            con.commit()

        runtime = mod.LLMRuntime(
            llm_status="live_api_key_present",
            model="gpt-test",
            temperature=0.2,
            client=object(),
        )
        with patch.object(mod, "resolve_llm_runtime", return_value=runtime), patch.object(
            mod, "call_llm", side_effect=RuntimeError("blocked")
        ):
            report = mod.run(
                db_path=self.db_path,
                report_json=self.report_json,
                report_md=self.report_md,
                write=True,
                limit=1,
                model="gpt-test",
                temperature=0.2,
            )

        self.assertEqual(report["counts"]["llm_error_count"], 1)
        self.assertEqual(report["counts"]["written_count"], 0)
        with closing(sqlite3.connect(self.db_path)) as con:
            rows = con.execute(
                "SELECT promotion_id FROM memory_promotion_candidates WHERE source_system='llm_memory_candidate'"
            ).fetchall()
        self.assertEqual(rows, [("existing-llm",)])

    def test_run_write_live_inserts_llm_candidates_and_preserves_graph_candidates(self) -> None:
        bundle = self._load_first_bundle()
        allowed_turn_ref = "conversation_turns_summary:turn_id/t1"
        self.assertIn(allowed_turn_ref, bundle["allowed_ref_tokens"])
        parsed = {
            "prompt_version": mod.PROMPT_VERSION,
            "model": "gpt-test",
            "temperature": 0.2,
            "llm_status": "live_api_key_present",
            "bundle_id": "meb-turn",
            "candidate_claims": [
                {
                    "candidate_id": "mcc-turn-1",
                    "candidate_claim": "用户偏好默认中文输出，并希望结论先说。",
                    "memory_type": "preference",
                    "subject": "user",
                    "extraction_status": "proposed",
                    "long_term_value_reason": "这是可复用的长期沟通偏好。",
                    "one_time_task_risk": "low",
                    "duplicate_check_hint": "mem-dup-1",
                    "conflict_check_hint": "",
                    "evidence_refs": [allowed_turn_ref],
                    "source_refs": ["source-a:1", allowed_turn_ref],
                    "event_ids": [],
                    "session_ids": ["sess-1"],
                    "turn_ids": ["t1"],
                    "confidence": 0.91,
                    "risk_flags": [],
                    "needs_human_review": False,
                }
            ],
        }

        runtime = mod.LLMRuntime(
            llm_status="live_api_key_present",
            model="gpt-test",
            temperature=0.2,
            client=object(),
        )
        with patch.object(mod, "resolve_llm_runtime", return_value=runtime), patch.object(mod, "call_llm", return_value=parsed):
            report = mod.run(
                db_path=self.db_path,
                report_json=self.report_json,
                report_md=self.report_md,
                write=True,
                limit=1,
                model="gpt-test",
                temperature=0.2,
            )

        self.assertEqual(report["llm_status"], "live_api_key_present")
        self.assertEqual(report["counts"]["candidate_count"], 1)
        self.assertEqual(report["counts"]["written_count"], 1)
        with closing(sqlite3.connect(self.db_path)) as con:
            rows = con.execute(
                "SELECT source_system, source_candidate_id, proposed_claim, duplicate_of_memory_id, promotion_status "
                "FROM memory_promotion_candidates ORDER BY source_system, source_candidate_id"
            ).fetchall()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], "graph_relation_candidate")
        self.assertEqual(rows[1][0], "llm_memory_candidate")
        self.assertEqual(rows[1][1], "mcc-turn-1")
        self.assertEqual(rows[1][2], "用户偏好默认中文输出，并希望结论先说。")
        self.assertEqual(rows[1][3], "mem-dup-1")
        self.assertEqual(rows[1][4], "review_required")


if __name__ == "__main__":
    unittest.main(verbosity=2)
