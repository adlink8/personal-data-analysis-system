"""Wave 9.1: graph relation candidate 纯逻辑测试。"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNIFIED_SCRIPTS = ROOT / 'integration' / 'scripts'
if str(UNIFIED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(UNIFIED_SCRIPTS))

import personal_knowledge.application.graph.build_graph_relation_candidates as mod  # noqa: E402


class TestGraphRelationCandidates(unittest.TestCase):
    def test_canonical_pair_sorts(self):
        self.assertEqual(mod.canonical_pair('b', 'a'), ('a', 'b'))

    def test_candidate_id_stable_for_swapped_order(self):
        a = mod.candidate_id_for('n1', 'n2', 'semantic_candidate')
        b = mod.candidate_id_for('n2', 'n1', 'semantic_candidate')
        self.assertEqual(a, b)

    def test_filter_removes_self_duplicate_and_low_similarity(self):
        candidates = [
            {
                'source_node_id': 'n1', 'target_node_id': 'n1',
                'source_session_id': 's1', 'source_turn_id': 't1',
                'target_session_id': 's1', 'target_turn_id': 't1',
                'similarity': 0.9, 'candidate_reason': 'x',
                'candidate_type': 'semantic_candidate',
                'source_refs_json': json.dumps(['a:1']),
            },
            {
                'source_node_id': 'n1', 'target_node_id': 'n2',
                'source_session_id': 's1', 'source_turn_id': 't1',
                'target_session_id': 's2', 'target_turn_id': 't2',
                'similarity': 0.5, 'candidate_reason': 'x',
                'candidate_type': 'semantic_candidate',
                'source_refs_json': json.dumps(['a:1']),
            },
            {
                'source_node_id': 'n1', 'target_node_id': 'n2',
                'source_session_id': 's1', 'source_turn_id': 't1',
                'target_session_id': 's2', 'target_turn_id': 't2',
                'similarity': 0.91, 'candidate_reason': 'x',
                'candidate_type': 'semantic_candidate',
                'source_refs_json': json.dumps(['a:1', 'a:1', 'b:2']),
            },
            {
                'source_node_id': 'n2', 'target_node_id': 'n1',
                'source_session_id': 's2', 'source_turn_id': 't2',
                'target_session_id': 's1', 'target_turn_id': 't1',
                'similarity': 0.92, 'candidate_reason': 'x',
                'candidate_type': 'semantic_candidate',
                'source_refs_json': json.dumps(['a:1', 'b:2']),
            },
        ]
        kept, stats = mod.filter_candidates(candidates, 0.78)
        self.assertEqual(len(kept), 1)
        self.assertEqual(stats['self_pair'], 1)
        self.assertEqual(stats['low_similarity'], 1)
        self.assertEqual(stats['duplicate_pair'], 1)
        refs = json.loads(kept[0]['source_refs_json'])
        self.assertEqual(refs, ['a:1', 'b:2'])

    def test_temporal_candidates_use_adjacent_turns(self):
        turn_map = {
            's#t1': {'node_id': 's#t1', 'session_id': 's', 'turn_id': 't1', 'turn_no': 1, 'source_refs': ['a:1']},
            's#t2': {'node_id': 's#t2', 'session_id': 's', 'turn_id': 't2', 'turn_no': 2, 'source_refs': ['a:2']},
            'x#t1': {'node_id': 'x#t1', 'session_id': 'x', 'turn_id': 't1', 'turn_no': 1, 'source_refs': ['x:1']},
        }
        order = ['s#t1', 's#t2', 'x#t1']
        out = mod.build_temporal_candidates(turn_map, order)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]['source_node_id'], 's#t1')
        self.assertEqual(out[0]['target_node_id'], 's#t2')
        self.assertEqual(out[0]['candidate_type'], 'temporal_candidate')


if __name__ == '__main__':
    unittest.main(verbosity=2)
