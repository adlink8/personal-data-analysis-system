import { describe, expect, it } from 'vitest';
import {
  wikiTopicBacklinksEnvelopeSchema,
  wikiTopicGetEnvelopeSchema,
  wikiTopicListEnvelopeSchema,
} from '../api/schemas';

const base = {
  schema_version: 'personal_wiki_projection_v1' as const,
  generated_at: '2026-07-28T00:00:00Z',
  snapshot_bindings: { personal: 'ps-1', external: null, decision: null },
  freshness: { state: 'fresh' as const },
  authorities: { personal: 'ok' },
  partial: false,
  limitations: [],
  projection_checksum: 'checksum-1',
  status: 'fresh' as const,
};

function topic() {
  return { topic_id: 'topic_123', topic_type: 'goal' as const, canonical_key: 'goal:work:personal:ship', display_label: 'goal:work · personal · ship' };
}

describe('personal_wiki_projection_v1 schemas', () => {
  it('locks literal schema and operation for list/get/backlinks', () => {
    expect(wikiTopicListEnvelopeSchema.safeParse({ ...base, operation: 'topic.list', ok: true, data: { items: [topic()], total_available: 1, limit: 50, next_cursor: null } }).success).toBe(true);
    expect(wikiTopicGetEnvelopeSchema.safeParse({ ...base, operation: 'topic.get', ok: true, data: { topic: topic(), claims: {}, evidence_refs: [] } }).success).toBe(true);
    expect(wikiTopicBacklinksEnvelopeSchema.safeParse({ ...base, operation: 'topic.backlinks', ok: true, data: { topic: topic(), links: [] } }).success).toBe(true);
  });

  it('rejects wrong version, wrong operation and missing opaque identity', () => {
    const valid = { ...base, operation: 'topic.list', ok: true, data: { items: [topic()], total_available: 1 } };
    expect(wikiTopicListEnvelopeSchema.safeParse({ ...valid, schema_version: 'decision_cockpit_projection_v1' }).success).toBe(false);
    expect(wikiTopicListEnvelopeSchema.safeParse({ ...valid, operation: 'topic.get' }).success).toBe(false);
    expect(wikiTopicListEnvelopeSchema.safeParse({ ...valid, data: { items: [{ ...topic(), topic_id: '' }] } }).success).toBe(false);
  });

  it('accepts honest unavailable envelope only with typed reason and null data', () => {
    const result = wikiTopicGetEnvelopeSchema.safeParse({
      ...base,
      operation: 'topic.get',
      ok: false,
      status: 'unavailable',
      error: 'authority_unavailable',
      data: null,
      partial: false,
    });
    expect(result.success).toBe(true);
  });
});
