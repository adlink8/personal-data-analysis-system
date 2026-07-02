"""Phase 10 memory graph visualization tests."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "integration" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import query_graph as mod  # noqa: E402


class TestMemoryGraphVisualization(unittest.TestCase):
    def _base_db(self) -> sqlite3.Connection:
        con = sqlite3.connect(":memory:")
        con.executescript(
            """
            CREATE TABLE memory_items (
                memory_id TEXT PRIMARY KEY,
                memory_type TEXT NOT NULL,
                memory_subtype TEXT NOT NULL,
                subject TEXT NOT NULL,
                description TEXT NOT NULL
            );
            CREATE TABLE memory_relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_memory_id TEXT NOT NULL,
                to_memory_id TEXT NOT NULL,
                relation TEXT NOT NULL,
                strength REAL DEFAULT 1.0
            );
            INSERT INTO memory_items VALUES
                ('m1','tooling','core','Codex','agent tooling'),
                ('m2','project','active','Phase 10','llm relation graph'),
                ('m3','fact','note','Noise','should stay hidden');
            INSERT INTO memory_relations (from_memory_id, to_memory_id, relation, strength) VALUES
                ('m1','m2','uses_tool',0.8);
            """
        )
        return con

    def test_default_load_graph_only_contains_rule_edges(self) -> None:
        con = self._base_db()
        self.addCleanup(con.close)

        graph, memories, warnings = mod.load_graph(con)

        self.assertEqual(len(memories), 3)
        self.assertEqual(graph.number_of_edges(), 1)
        edge = list(graph.edges(data=True))[0][2]
        self.assertEqual(edge["edge_source"], "rule")
        self.assertEqual(warnings, [])

    def test_include_llm_relations_filters_and_formats_edges(self) -> None:
        con = self._base_db()
        self.addCleanup(con.close)
        con.executescript(
            """
            CREATE TABLE memory_relation_candidates (
                candidate_id TEXT PRIMARY KEY,
                source_memory_id TEXT NOT NULL,
                target_memory_id TEXT NOT NULL
            );
            CREATE TABLE memory_relation_judgments (
                candidate_id TEXT PRIMARY KEY,
                relation_type TEXT NOT NULL,
                gate_status TEXT NOT NULL,
                confidence REAL NOT NULL,
                reason TEXT NOT NULL
            );
            INSERT INTO memory_relation_candidates VALUES
                ('cand-accepted','m1','m2'),
                ('cand-review','m2','m1'),
                ('cand-rejected','m1','m3'),
                ('cand-none','m2','m3');
            INSERT INTO memory_relation_judgments VALUES
                ('cand-accepted','supports','accepted',0.91,'stable long-term support'),
                ('cand-review','related_topic','review',0.63,'needs human review'),
                ('cand-rejected','conflicts_with','rejected',0.95,'noise'),
                ('cand-none','no_relation','accepted',0.99,'explicitly no relation');
            """
        )

        graph, _, warnings = mod.load_graph(con, include_llm_relations=True)
        llm_edges = [data for _, _, data in graph.edges(data=True) if data.get("edge_source") == "llm_judgment"]

        self.assertEqual(len(llm_edges), 2)
        self.assertEqual(warnings, [])
        candidate_ids = {edge["candidate_id"] for edge in llm_edges}
        self.assertEqual(candidate_ids, {"cand-accepted", "cand-review"})
        for edge in llm_edges:
            self.assertTrue(edge["label"].startswith("LLM:"))
            self.assertIn(f"candidate_id: {edge['candidate_id']}", edge["title"])
            self.assertIn("status:", edge["title"])
            self.assertIn("confidence:", edge["title"])
            self.assertIn("reason:", edge["title"])

    def test_include_llm_relations_missing_tables_warns_without_crashing(self) -> None:
        con = self._base_db()
        self.addCleanup(con.close)

        graph, _, warnings = mod.load_graph(con, include_llm_relations=True)

        self.assertEqual(graph.number_of_edges(), 1)
        self.assertEqual(len(warnings), 1)
        self.assertIn("缺少表", warnings[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
