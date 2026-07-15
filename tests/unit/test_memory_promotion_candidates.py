"""Phase 09 Wave 3 promotion candidate boundary tests."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "integration" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import personal_knowledge.domains.memory.build_memory_promotion_candidates as mod  # noqa: E402


class TestMemoryPromotionCandidates(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "test.sqlite"
        self.matrix_path = Path(self.tmp.name) / "memory_mechanism_matrix.json"
        self.preview_json = Path(self.tmp.name) / "preview.json"
        self.preview_md = Path(self.tmp.name) / "preview.md"
        self._write_matrix()
        self._write_db()

    def _write_matrix(self) -> None:
        self.matrix_path.write_text(
            json.dumps(
                {
                    "llm_status": "fallback:no_api_key",
                    "prompt_version": "memory_mechanism_judge/v1",
                    "mechanism_steps": [
                        {"mechanism_step": "candidate_generation", "merged_method": "graph candidates only"},
                        {"mechanism_step": "evidence_gate", "merged_method": "must have refs"},
                        {"mechanism_step": "promotion_policy", "merged_method": "review only"},
                        {"mechanism_step": "storage_boundary", "merged_method": "candidate table only"},
                    ],
                }
            ),
            encoding="utf-8",
        )

    def _write_db(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as con:
            con.executescript(
                """
                CREATE TABLE graph_relation_candidates (
                    candidate_id TEXT PRIMARY KEY,
                    source_node_id TEXT NOT NULL,
                    target_node_id TEXT NOT NULL,
                    source_session_id TEXT NOT NULL,
                    source_turn_id TEXT,
                    target_session_id TEXT NOT NULL,
                    target_turn_id TEXT,
                    similarity REAL,
                    candidate_reason TEXT NOT NULL,
                    candidate_type TEXT NOT NULL,
                    source_refs_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE graph_relation_judgments (
                    candidate_id TEXT PRIMARY KEY,
                    relation_type TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_refs_json TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    risk_flags_json TEXT NOT NULL,
                    model TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    temperature REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    gate_status TEXT NOT NULL DEFAULT 'pending'
                );
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
                """
            )
            con.execute(
                """
                INSERT INTO graph_relation_candidates VALUES
                ('c-pref','n1','n2','s1','t1','s2','t2',0.91,'semantic','semantic_candidate',?, '2026-01-01')
                """,
                (json.dumps(["source-a:1", "source-b:2"]),),
            )
            con.execute(
                """
                INSERT INTO graph_relation_judgments VALUES
                ('c-pref','preference_signal',0.9,?,'stable preference signal','[]','gpt-5.4','v1',0.1,'2026-01-01','accepted')
                """,
                (json.dumps(["source-a:1", "source-b:2"]),),
            )
            con.execute(
                """
                INSERT INTO graph_relation_candidates VALUES
                ('c-task','n3','n4','s3','t3','s4','t4',0.88,'semantic','semantic_candidate',?, '2026-01-01')
                """,
                (json.dumps(["source-c:3"]),),
            )
            con.execute(
                """
                INSERT INTO graph_relation_judgments VALUES
                ('c-task','same_problem',0.92,?,'同一具体任务，不应自动晋级','[]','gpt-5.4','v1',0.1,'2026-01-01','accepted')
                """,
                (json.dumps(["source-c:3"]),),
            )
            con.execute(
                """
                INSERT INTO graph_relation_candidates VALUES
                ('c-empty','n5','n6','s5','t5','s6','t6',0.8,'semantic','semantic_candidate',?, '2026-01-01')
                """,
                (json.dumps(["source-empty:1"]),),
            )
            con.execute(
                """
                INSERT INTO graph_relation_judgments VALUES
                ('c-empty','preference_signal',0.8,?,'empty evidence should be skipped','[]','gpt-5.4','v1',0.1,'2026-01-01','accepted')
                """,
                (json.dumps([]),),
            )
            con.execute(
                """
                INSERT INTO memory_items VALUES
                ('m1','preference','output_style','中文输出','用户偏好中文、结论前置',0.8,2,'{}','2026-01-01')
                """
            )
            con.execute(
                "INSERT INTO memory_links VALUES (1,'m1','event','e1','evidenced_by')"
            )
            con.execute(
                "INSERT INTO unified_events_rich VALUES ('e1','用户要求默认中文输出，并结论先说','test-source')"
            )
            con.execute(
                """
                INSERT INTO conversation_turns_summary VALUES
                (1,'s1',1,'t1','用户明确要求默认中文输出','', 'source-a:1','输出风格'),
                (2,'s2',1,'t2','助手确认后续默认中文输出','', 'source-b:2','输出风格'),
                (3,'s3',1,'t3','用户继续追问同一具体任务','', 'source-c:3','具体任务')
                """
            )
            con.commit()

    def _build_candidates(self, **kwargs: object) -> list[dict[str, object]]:
        with closing(sqlite3.connect(self.db_path)) as con:
            con.row_factory = sqlite3.Row
            policy = mod.load_mechanism_policy(self.matrix_path)
            return mod.build_candidates(con, policy, **kwargs)

    def test_build_candidates_removes_legacy_candidate_path(self) -> None:
        candidates = self._build_candidates(max_graph=10, max_legacy=10, evidence_per_legacy=99, created_at="2026-07-01T00:00:00Z")

        self.assertEqual(len(candidates), 2)
        self.assertNotIn("c-empty", {candidate["source_candidate_id"] for candidate in candidates})
        self.assertEqual({candidate["source_system"] for candidate in candidates}, {"graph_relation_candidate"})
        self.assertTrue(all(candidate["source_memory_id"] is None for candidate in candidates))
        statuses = {candidate["promotion_status"] for candidate in candidates}
        self.assertLessEqual(statuses, mod.ALLOWED_STATUSES)
        self.assertTrue(statuses.isdisjoint(mod.DISALLOWED_STATUSES))
        self.assertIn("reject_or_review", statuses)
        self.assertIn("needs_live_llm_review", statuses)

    def test_legacy_parameters_are_ignored_and_no_candidate_uses_memory_items_as_source(self) -> None:
        baseline = self._build_candidates(max_graph=10, max_legacy=0, evidence_per_legacy=1)
        variant = self._build_candidates(max_graph=10, max_legacy=999, evidence_per_legacy=999)

        self.assertEqual(
            [(candidate["promotion_id"], candidate["source_candidate_id"]) for candidate in baseline],
            [(candidate["promotion_id"], candidate["source_candidate_id"]) for candidate in variant],
        )
        for candidate in variant:
            source_refs = json.loads(candidate["source_refs_json"])
            self.assertFalse(
                any(isinstance(ref, dict) and ref.get("table") == "memory_items" for ref in source_refs)
            )

    def test_structured_evidence_does_not_promote_directly(self) -> None:
        candidates = self._build_candidates(max_graph=10, max_legacy=10, evidence_per_legacy=10)

        promoted_refs = {
            ref.get("event_id")
            for candidate in candidates
            for ref in json.loads(candidate["evidence_refs_json"])
            if isinstance(ref, dict)
        }
        self.assertNotIn("e1", promoted_refs)
        self.assertTrue(all(candidate["source_system"] != "legacy_evidence_candidate" for candidate in candidates))

    def test_write_candidates_table_is_idempotent_and_review_only(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as con:
            con.row_factory = sqlite3.Row
            policy = mod.load_mechanism_policy(self.matrix_path)
            candidates = mod.build_candidates(con, policy, max_graph=10, max_legacy=10, evidence_per_legacy=10)
            mod.write_candidates_table(con, candidates)
            first_count = con.execute(f"SELECT COUNT(*) FROM {mod.TABLE_NAME}").fetchone()[0]
            mod.write_candidates_table(con, candidates)
            second_count = con.execute(f"SELECT COUNT(*) FROM {mod.TABLE_NAME}").fetchone()[0]
            disallowed = con.execute(
                f"SELECT COUNT(*) FROM {mod.TABLE_NAME} WHERE promotion_status IN ('approved','promotion_ready')"
            ).fetchone()[0]
            sources = {
                row[0] for row in con.execute(f"SELECT DISTINCT source_system FROM {mod.TABLE_NAME}").fetchall()
            }

        self.assertEqual(first_count, 2)
        self.assertEqual(second_count, 2)
        self.assertEqual(disallowed, 0)
        self.assertEqual(sources, {"graph_relation_candidate"})

    def test_write_candidates_table_preserves_other_candidate_sources(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as con:
            con.row_factory = sqlite3.Row
            policy = mod.load_mechanism_policy(self.matrix_path)
            candidates = mod.build_candidates(con, policy, max_graph=10, max_legacy=10, evidence_per_legacy=10)
            mod.create_candidates_table(con)
            con.executemany(
                f"INSERT INTO {mod.TABLE_NAME} ({','.join(mod.REQUIRED_FIELDS)}) VALUES ({','.join('?' for _ in mod.REQUIRED_FIELDS)})",
                [
                    (
                        "mpc-llm-existing",
                        "llm_memory_candidate",
                        "mcc-1",
                        None,
                        "s-old",
                        "t-old",
                        None,
                        "preference",
                        "user",
                        "已有 LLM 候选",
                        0.8,
                        "[]",
                        "[]",
                        None,
                        None,
                        "review_required",
                        "keep llm candidate",
                        "2026-07-01T00:00:00Z",
                    ),
                    (
                        "mpc-manual-existing",
                        "manual_review_import",
                        "manual-1",
                        None,
                        "s-manual",
                        "t-manual",
                        None,
                        "project",
                        "user",
                        "已有人工导入候选",
                        0.9,
                        "[]",
                        "[]",
                        None,
                        None,
                        "review_required",
                        "keep manual candidate",
                        "2026-07-01T00:00:00Z",
                    ),
                ],
            )
            con.commit()

            mod.write_candidates_table(con, candidates)
            sources = {
                row[0]: row[1]
                for row in con.execute(
                    f"SELECT source_system, COUNT(*) FROM {mod.TABLE_NAME} GROUP BY source_system"
                ).fetchall()
            }

        self.assertEqual(sources["graph_relation_candidate"], 2)
        self.assertEqual(sources["llm_memory_candidate"], 1)
        self.assertEqual(sources["manual_review_import"], 1)

    def test_run_dry_run_does_not_write_preview_files_or_table(self) -> None:
        preview = mod.run(
            db_path=self.db_path,
            matrix_path=self.matrix_path,
            preview_json=self.preview_json,
            preview_md=self.preview_md,
            write=False,
            max_graph=10,
            max_legacy=10,
            evidence_per_legacy=5,
        )

        self.assertFalse(preview["table_written"])
        self.assertFalse(self.preview_json.exists())
        self.assertFalse(self.preview_md.exists())
        with closing(sqlite3.connect(self.db_path)) as con:
            self.assertFalse(mod.table_exists(con, mod.TABLE_NAME))


if __name__ == "__main__":
    unittest.main(verbosity=2)
