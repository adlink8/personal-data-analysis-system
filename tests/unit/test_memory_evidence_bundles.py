"""Phase 09 Wave 3 evidence bundle tests."""

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

import personal_knowledge.application.memory.build_memory_evidence_bundles as mod  # noqa: E402


class TestMemoryEvidenceBundles(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / "test.sqlite"
        self.preview_json = Path(self.tmp.name) / "bundles.json"
        self.preview_md = Path(self.tmp.name) / "bundles.md"
        self._write_db()

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
                ('c-pref','n1','n2','s1','t1','s2','t2',0.95,'semantic','semantic_candidate',?, '2026-01-01')
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
                INSERT INTO conversation_turns_summary VALUES
                (1,'s1',1,'t1','用户明确要求默认中文输出','', 'source-a:1','输出风格'),
                (2,'s2',1,'t2','助手确认后续默认中文输出','', 'source-b:2','输出风格'),
                (3,'s3',1,'t3','用户提供结构化事件背景','', 'source-c:3','结构化证据')
                """
            )
            con.execute(
                """
                INSERT INTO unified_events_rich VALUES
                ('e1','用户要求默认中文输出，并结论先说','source-event:1'),
                ('e2','用户新增一条结构化事件证据','source-event:2')
                """
            )
            con.execute(
                """
                INSERT INTO memory_items VALUES
                ('m1','preference','output_style','输出风格','默认中文输出',0.8,2,'{}','2026-01-01')
                """
            )
            con.commit()

    def test_build_bundles_uses_graph_turn_and_event_inputs_without_memory_items_evidence(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as con:
            con.row_factory = sqlite3.Row
            bundles = mod.build_bundles(con, limit=6, created_at="2026-07-01T00:00:00Z")

        self.assertGreaterEqual(len(bundles), 3)
        bundle_types = {bundle["bundle_type"] for bundle in bundles}
        self.assertIn("accepted_graph_edge", bundle_types)
        self.assertIn("conversation_turn", bundle_types)
        self.assertIn("unified_event", bundle_types)
        for bundle in bundles:
            evidence_refs = json.loads(bundle["evidence_refs_json"])
            source_refs = json.loads(bundle["source_refs_json"])
            self.assertTrue(evidence_refs)
            self.assertTrue(source_refs)
            self.assertFalse(
                any(isinstance(ref, dict) and ref.get("table") == "memory_items" for ref in evidence_refs + source_refs)
            )

    def test_write_bundles_table_and_preview_without_touching_long_term_counts(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as con:
            before = {
                "memory_items": con.execute("SELECT COUNT(*) FROM memory_items").fetchone()[0],
            }

        preview = mod.run(
            db_path=self.db_path,
            preview_json=self.preview_json,
            preview_md=self.preview_md,
            write=True,
            limit=6,
        )

        self.assertTrue(preview["table_written"])
        self.assertTrue(self.preview_json.exists())
        self.assertTrue(self.preview_md.exists())
        with closing(sqlite3.connect(self.db_path)) as con:
            bundle_count = con.execute(f"SELECT COUNT(*) FROM {mod.TABLE_NAME}").fetchone()[0]
            source_systems = {
                row[0] for row in con.execute(f"SELECT DISTINCT source_system FROM {mod.TABLE_NAME}").fetchall()
            }
            after = {
                "memory_items": con.execute("SELECT COUNT(*) FROM memory_items").fetchone()[0],
            }

        self.assertEqual(bundle_count, preview["stats"]["total"])
        self.assertIn("accepted_graph_edge", source_systems)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)
