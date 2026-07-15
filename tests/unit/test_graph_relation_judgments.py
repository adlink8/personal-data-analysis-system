"""Wave 9.2/9.3 gate tests."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNIFIED_SCRIPTS = ROOT / 'integration' / 'scripts'
if str(UNIFIED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(UNIFIED_SCRIPTS))

import personal_knowledge.domains.graph.judge_graph_relations as judge_mod  # noqa: E402
import personal_knowledge.domains.graph.evaluate_graph_relation_judgments as eval_mod  # noqa: E402


class TestGraphRelationJudgments(unittest.TestCase):
    def test_normalize_invalid_relation_to_no_relation(self):
        row = judge_mod.normalize_judgment('c1', {
            'relation_type': 'bad_type', 'confidence': 2, 'evidence_refs': 'x', 'risk_flags': '', 'reason': ''
        })
        self.assertEqual(row['relation_type'], 'no_relation')
        self.assertEqual(row['confidence'], 1.0)
        self.assertEqual(row['evidence_refs'], [])

    def test_refs_match(self):
        self.assertTrue(eval_mod.refs_match(['a\\b:1'], ['a/b:1', 'x:2']))
        self.assertFalse(eval_mod.refs_match([], ['a/b:1']))

    def test_classify_accept_review_reject(self):
        rows = [
            {
                'candidate_id': 'c1', 'relation_type': 'same_problem', 'confidence': 0.9,
                'evidence_refs_json': json.dumps(['a:1']), 'reason': 'ok', 'risk_flags_json': json.dumps([]),
                'source_node_id': 'n1', 'target_node_id': 'n2', 'source_refs_json': json.dumps(['a:1','b:2'])
            },
            {
                'candidate_id': 'c2', 'relation_type': 'same_problem', 'confidence': 0.6,
                'evidence_refs_json': json.dumps(['a:1']), 'reason': 'mid', 'risk_flags_json': json.dumps([]),
                'source_node_id': 'n3', 'target_node_id': 'n4', 'source_refs_json': json.dumps(['a:1'])
            },
            {
                'candidate_id': 'c3', 'relation_type': 'no_relation', 'confidence': 0.2,
                'evidence_refs_json': json.dumps([]), 'reason': 'none', 'risk_flags_json': json.dumps([]),
                'source_node_id': 'n5', 'target_node_id': 'n6', 'source_refs_json': json.dumps(['z:9'])
            },
        ]
        review_items, stats = eval_mod.classify_rows(rows)
        self.assertEqual(stats['accepted'], 1)
        self.assertEqual(stats['review'], 1)
        self.assertEqual(stats['rejected'], 1)
        self.assertEqual(len(review_items), 1)

    def test_pair_conflict_goes_review(self):
        rows = [
            {
                'candidate_id': 'c1', 'relation_type': 'same_problem', 'confidence': 0.9,
                'evidence_refs_json': json.dumps(['a:1']), 'reason': 'ok', 'risk_flags_json': json.dumps([]),
                'source_node_id': 'n1', 'target_node_id': 'n2', 'source_refs_json': json.dumps(['a:1'])
            },
            {
                'candidate_id': 'c2', 'relation_type': 'contradiction', 'confidence': 0.88,
                'evidence_refs_json': json.dumps(['a:1']), 'reason': 'conflict', 'risk_flags_json': json.dumps([]),
                'source_node_id': 'n2', 'target_node_id': 'n1', 'source_refs_json': json.dumps(['a:1'])
            },
        ]
        review_items, stats = eval_mod.classify_rows(rows)
        self.assertEqual(stats['review'], 2)
        self.assertEqual(len(review_items), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
