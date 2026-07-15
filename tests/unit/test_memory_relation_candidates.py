"""Phase 10 memory relation candidate and gate tests."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "integration" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import personal_knowledge.domains.memory.build_memory_relation_candidates as build_mod  # noqa: E402
import personal_knowledge.domains.memory.evaluate_memory_relation_candidates as eval_mod  # noqa: E402


def make_package() -> dict:
    return {
        "package_id": "mrpkg:test",
        "source_memory_id": "m1",
        "target_memory_id": "m2",
        "source_memory": {
            "memory_id": "m1",
            "memory_type": "tooling",
            "memory_subtype": "editor",
            "subject": "Codex",
            "description": "CLI coding agent",
            "confidence": 0.9,
            "evidence_count": 2,
            "linked_refs": ["source-a:1"],
        },
        "target_memory": {
            "memory_id": "m2",
            "memory_type": "capability",
            "memory_subtype": "workflow",
            "subject": "Codex workflow",
            "description": "Uses Codex for phased execution",
            "confidence": 0.8,
            "evidence_count": 3,
            "linked_refs": ["source-a:1"],
        },
        "coarse_recall_signals": ["shared_linked_ref", "subject_token_overlap"],
        "signal_reasons": ["shared_linked_refs:source-a:1", "shared_subject_tokens:codex"],
        "signal_scores": {"shared_linked_ref": 0.9, "subject_token_overlap": 0.6},
        "shared_tokens": ["codex"],
        "shared_linked_refs": ["source-a:1"],
        "existing_rule_relations": [{"relation": "uses_tool", "strength": 0.7}],
        "allowed_refs": [
            "memory_id:m1",
            "memory_id:m2",
            "memory_field:m1:subject",
            "memory_field:m2:subject",
            "memory_field:m1:description",
            "memory_field:m2:description",
            "linked_ref:source-a:1",
            "rule_relation:uses_tool",
        ],
    }


class TestMemoryRelationCandidates(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)
        self.db_path = self.tmp_path / "test.sqlite"
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
                CREATE TABLE memory_relations (
                    id INTEGER PRIMARY KEY,
                    from_memory_id TEXT NOT NULL,
                    to_memory_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    strength REAL DEFAULT 1.0
                );
                """
            )
            con.executemany(
                """
                INSERT INTO memory_items VALUES (?,?,?,?,?,?,?,?,?)
                """,
                [
                    (
                        "m1",
                        "tooling",
                        "editor",
                        "Codex",
                        "CLI coding agent",
                        0.9,
                        2,
                        json.dumps({"source_refs": ["source-a:1"], "linked_event_ids": ["e1"]}),
                        "2026-07-01T00:00:00",
                    ),
                    (
                        "m2",
                        "capability",
                        "workflow",
                        "Codex workflow",
                        "Uses Codex for phased execution",
                        0.8,
                        3,
                        json.dumps({"source_refs": ["source-a:1", "source-b:2"]}),
                        "2026-07-01T00:00:00",
                    ),
                    (
                        "m3",
                        "project",
                        "task",
                        "Math homework",
                        "One-off task",
                        0.6,
                        1,
                        json.dumps({"source_refs": ["source-c:3"]}),
                        "2026-07-01T00:00:00",
                    ),
                ],
            )
            con.execute(
                "INSERT INTO memory_relations VALUES (1,'m1','m2','uses_tool',0.7)"
            )
            con.commit()

    def test_validate_proposal_fields_rejects_unknown_refs(self) -> None:
        proposal = {
            "candidate_id": "mrcand:test",
            "candidate_type": "semantic_relation_candidate",
            "source_memory_id": "m1",
            "target_memory_id": "m2",
            "proposed_relation_type": "uses_tool",
            "proposal_status": "proposed",
            "confidence": 0.9,
            "why_candidate": "这只是候选，需要后续 gate。",
            "evidence_refs": ["linked_ref:missing:9"],
            "source_refs": ["memory_id:m1", "memory_id:m2"],
            "risk_flags": [],
            "needs_human_review": False,
        }
        normalized, schema_error, evidence_error = build_mod.validate_proposal_fields(proposal, make_package())
        self.assertIsNone(normalized)
        self.assertIsNone(schema_error)
        self.assertIn("outside package", evidence_error)

    def test_normalize_llm_response_counts_schema_rejection(self) -> None:
        rows, schema_rejected, evidence_rejected = build_mod.normalize_llm_response(
            {"package_id": "wrong", "candidate_proposals": []},
            make_package(),
            "live_api_key_present",
            "gpt-test",
            0.2,
        )
        self.assertEqual(schema_rejected, 1)
        self.assertEqual(evidence_rejected, 0)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["proposal_status"], "reject")

    def test_write_mode_without_api_key_writes_blocked_proposals_only(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as con:
            before_relations = con.execute("SELECT COUNT(*) FROM memory_relations").fetchone()[0]

        with mock.patch.dict("os.environ", {}, clear=True):
            report = build_mod.run_pipeline(
                db_path=self.db_path,
                dry_run=False,
                write=True,
                limit=5,
                model="gpt-test",
                temperature=0.2,
            )

        self.assertGreater(report["coarse_packages"], 0)
        self.assertEqual(report["written_candidates"], 0)
        self.assertEqual(report["proposal_status_counts"]["blocked"], report["proposal_rows"])
        with closing(sqlite3.connect(self.db_path)) as con:
            proposal_count = con.execute("SELECT COUNT(*) FROM memory_relation_candidate_proposals").fetchone()[0]
            candidate_count = con.execute("SELECT COUNT(*) FROM memory_relation_candidates").fetchone()[0]
            after_relations = con.execute("SELECT COUNT(*) FROM memory_relations").fetchone()[0]

        self.assertEqual(proposal_count, report["proposal_rows"])
        self.assertEqual(candidate_count, 0)
        self.assertEqual(before_relations, after_relations)

    def test_candidate_row_only_written_for_proposed_rows(self) -> None:
        row = build_mod.build_audit_row(
            package=make_package(),
            source_memory_id="m1",
            target_memory_id="m2",
            relation_type="uses_tool",
            proposal_status="proposed",
            candidate_type="semantic_relation_candidate",
            confidence=0.88,
            why_candidate="工具能力关系，但仍只是候选。",
            evidence_refs=["memory_id:m1", "memory_field:m2:subject", "linked_ref:source-a:1"],
            source_refs=["memory_id:m1", "memory_id:m2", "linked_ref:source-a:1"],
            risk_flags=[],
            model="gpt-test",
            temperature=0.2,
            llm_status="live_api_key_present",
        )
        candidate = build_mod.candidate_row_from_proposal(row, {"mrpkg:test": make_package()})
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate["relation_type"], "uses_tool")
        self.assertIn("memory_id:m1", json.loads(candidate["allowed_refs_json"]))

    def test_gate_classification_accepts_review_and_rejects(self) -> None:
        rows = [
            {
                "candidate_id": "c-accepted",
                "package_id": "p1",
                "source_memory_id": "m1",
                "target_memory_id": "m2",
                "relation_type": "uses_tool",
                "confidence": 0.9,
                "candidate_reason": "strong evidence",
                "evidence_refs_json": json.dumps(["memory_id:m1", "memory_id:m2"]),
                "source_refs_json": json.dumps(["memory_id:m1", "memory_id:m2"]),
                "allowed_refs_json": json.dumps(["memory_id:m1", "memory_id:m2"]),
                "risk_flags_json": "[]",
                "llm_status": "live_api_key_present",
                "model": "gpt-test",
                "prompt_version": "memory_relation_proposal/v1",
                "created_at": "2026-07-02T00:00:00",
            },
            {
                "candidate_id": "c-review",
                "package_id": "p2",
                "source_memory_id": "m1",
                "target_memory_id": "m3",
                "relation_type": "supports",
                "confidence": 0.7,
                "candidate_reason": "mid confidence",
                "evidence_refs_json": json.dumps(["memory_id:m1"]),
                "source_refs_json": json.dumps(["memory_id:m1", "memory_id:m3"]),
                "allowed_refs_json": json.dumps(["memory_id:m1", "memory_id:m3"]),
                "risk_flags_json": "[]",
                "llm_status": "live_api_key_present",
                "model": "gpt-test",
                "prompt_version": "memory_relation_proposal/v1",
                "created_at": "2026-07-02T00:00:00",
            },
            {
                "candidate_id": "c-reject",
                "package_id": "p3",
                "source_memory_id": "m2",
                "target_memory_id": "m2",
                "relation_type": "unknown_relation",
                "confidence": 0.95,
                "candidate_reason": "bad",
                "evidence_refs_json": json.dumps(["memory_id:m2"]),
                "source_refs_json": json.dumps(["memory_id:m2"]),
                "allowed_refs_json": json.dumps(["memory_id:m2"]),
                "risk_flags_json": "[]",
                "llm_status": "live_api_key_present",
                "model": "gpt-test",
                "prompt_version": "memory_relation_proposal/v1",
                "created_at": "2026-07-02T00:00:00",
            },
        ]
        judgments, review_items, stats = eval_mod.classify_candidates(rows)
        by_id = {row["candidate_id"]: row for row in judgments}
        self.assertEqual(by_id["c-accepted"]["gate_status"], "accepted")
        self.assertEqual(by_id["c-review"]["gate_status"], "review")
        self.assertEqual(by_id["c-reject"]["gate_status"], "rejected")
        self.assertEqual(stats["accepted"], 1)
        self.assertEqual(stats["review"], 1)
        self.assertEqual(stats["rejected"], 1)
        self.assertEqual(len(review_items), 1)

    def test_eval_write_does_not_modify_memory_relations(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as con:
            con.executescript(build_mod.CANDIDATE_SCHEMA_SQL)
            con.execute(
                """
                INSERT INTO memory_relation_candidates VALUES
                ('c1','pkg','m1','m2','uses_tool',0.9,'reason',?,?,?,'[]','live_api_key_present','gpt-test','memory_relation_proposal/v1','2026-07-02T00:00:00')
                """,
                (
                    json.dumps(["memory_id:m1", "memory_id:m2"]),
                    json.dumps(["memory_id:m1", "memory_id:m2"]),
                    json.dumps(["memory_id:m1", "memory_id:m2"]),
                ),
            )
            before_relations = con.execute("SELECT COUNT(*) FROM memory_relations").fetchone()[0]
            con.commit()

        report = eval_mod.run(db_path=self.db_path, write=True)
        self.assertEqual(report["accepted"], 1)
        with closing(sqlite3.connect(self.db_path)) as con:
            judgment_count = con.execute("SELECT COUNT(*) FROM memory_relation_judgments").fetchone()[0]
            review_count = con.execute("SELECT COUNT(*) FROM memory_relation_review_queue").fetchone()[0]
            after_relations = con.execute("SELECT COUNT(*) FROM memory_relations").fetchone()[0]

        self.assertEqual(judgment_count, 1)
        self.assertEqual(review_count, 0)
        self.assertEqual(before_relations, after_relations)


if __name__ == "__main__":
    unittest.main(verbosity=2)
