import { describe, expect, it } from 'vitest';
import cohort from './fixtures/wiki-uat-cohort.json';
import authorityStates from './fixtures/wiki-uat-authority-states.json';
import { wikiTopicGetEnvelopeSchema } from '../api/schemas';

const forbiddenArtifactPattern = /(?:api[_-]?key\s*[:=]|bearer\s+[A-Za-z0-9._-]+|sk-[A-Za-z0-9]{12,}|https?:\/\/|[A-Za-z]:\\\\Users\\\\|raw_(?:body|content|message)|(?:preview|confirmation)[_-]?(?:token|payload))/i;

describe('Wiki P0 fixture UAT contract', () => {
  it('keeps the three P0 types and fixture/live boundary explicit', () => {
    expect(cohort.classification).toBe('fixture_only');
    expect(cohort.topics).toHaveLength(3);
    expect(new Set(cohort.topics.map((topic) => topic.topic_type))).toEqual(new Set(['project', 'goal', 'decision']));
    for (const topic of cohort.topics) {
      expect(topic.topic_id).toMatch(/^topic_fixture_[a-z_]+$/);
      expect(topic.task).toBeTruthy();
      expect(topic.expected_status).toMatch(/^(fresh|partial|stale)$/);
    }
  });

  it('covers each degraded state with a typed, non-secret reason', () => {
    const states = new Set(authorityStates.states.map((item) => item.state));
    expect(states).toEqual(new Set(['fresh', 'stale', 'partial', 'unavailable', 'privacy_sealed', 'evidence_mismatch', 'retrieval_unavailable', 'widget_unavailable']));
    expect(JSON.stringify({ cohort, authorityStates })).not.toMatch(forbiddenArtifactPattern);
    for (const item of authorityStates.states) {
      expect(item.expected_recovery).toBeTruthy();
      expect(item.reason_code === null || /^[a-z_]+$/.test(item.reason_code)).toBe(true);
    }
  });

  it('uses the server envelope vocabulary for a fixture topic response', () => {
    const result = wikiTopicGetEnvelopeSchema.safeParse({
      schema_version: 'personal_wiki_projection_v1',
      operation: 'topic.get',
      ok: true,
      status: 'partial',
      generated_at: 'fixture-time',
      snapshot_bindings: { personal: 'fixture_ps', external: null, decision: null },
      freshness: { state: 'partial' },
      authorities: { personal: 'ok', external: 'error' },
      partial: true,
      limitations: ['External authority unavailable'],
      projection_checksum: 'fixture_checksum',
      data: {
        topic: { topic_id: 'topic_fixture_goal_a', topic_type: 'goal', canonical_key: 'goal:fixture:fixture:context' },
        claims: { current: [], observations: [], inferences: [], recommendations: [], historical: [], conflicts: [], external: [], decision_feedback: [] },
        evidence_refs: [],
      },
    });
    expect(result.success).toBe(true);
  });
});
