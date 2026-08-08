import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { TopicPage } from '../pages/knowledge/TopicPage';

const topicEnvelope = {
  schema_version: 'personal_wiki_projection_v1' as const,
  operation: 'topic.get' as const,
  ok: true,
  generated_at: '2026-07-28T00:00:00Z',
  snapshot_bindings: { personal: 'ps-1', external: 'ex-1', decision: null },
  freshness: { state: 'fresh' as const },
  authorities: { personal: 'ok', external: 'ok', decision: 'empty' },
  partial: false,
  limitations: ['Decision 结果保留 non-causal 限制'],
  projection_checksum: 'projection-1',
  status: 'fresh' as const,
  data: {
    topic: { topic_id: 'topic_goal', topic_type: 'goal' as const, canonical_key: 'goal:work:personal:ship', display_label: 'goal:ship' },
    claims: {
      current: [{ claim_type: 'current', key: { assertion_kind: 'goal', subject: 'user', domain: 'work', scope: 'personal', predicate: 'ship' }, status: 'current', authority_ref: { authority_id: 'a.personal_state', record_type: 'assertion', record_id: 'a-1', snapshot_id: 'ps-1', checksum: 'c-1' }, evidence_refs: [{ ref: 'ev-1', artifact_type: 'knowledge_unit' }], uncertainty: [] }],
      observations: [], inferences: [], recommendations: [], historical: [], conflicts: [], external: [{ claim_type: 'external', authority_ref: { authority_id: 'a.external_context', record_type: 'fact', record_id: 'f-1', snapshot_id: 'ex-1', checksum: 'f-c' }, evidence_refs: [], uncertainty: [] }], decision_feedback: [],
    },
    evidence_refs: [{ ref: 'ev-1', artifact_type: 'knowledge_unit' }],
  },
};

vi.mock('../api/hooks', () => ({
  useWikiTopic: () => ({ isPending: false, isError: false, error: null, refetch: vi.fn(), data: topicEnvelope }),
  useWikiTopicBacklinks: () => ({ isPending: false, isError: false, error: null, data: { schema_version: 'personal_wiki_projection_v1', operation: 'topic.backlinks', ok: true, snapshot_bindings: {}, freshness: { state: 'fresh' }, authorities: {}, partial: false, limitations: [], projection_checksum: 'b', status: 'fresh', data: { topic: topicEnvelope.data.topic, links: [] } } }),
  useWikiTopicResolve: () => ({ isPending: false, isError: false, error: null, data: { schema_version: 'personal_wiki_projection_v1', operation: 'topic.resolve', ok: true, snapshot_bindings: {}, freshness: { state: 'fresh' }, authorities: {}, partial: false, limitations: [], projection_checksum: 'r', status: 'fresh', data: { selected_source: 'fresh_wiki', attempted_sources: ['wiki'], fallback_reason: null, source: {}, topic: topicEnvelope.data.topic } } }),
}));

describe('TopicPage', () => {
  it('separates current, external and evidence metadata without write controls', () => {
    const router = createMemoryRouter([{ path: '/knowledge/:topicType/:topicId', element: <TopicPage /> }], { initialEntries: ['/knowledge/goal/topic_goal'] });
    render(<RouterProvider router={router} />);
    expect(screen.getByRole('heading', { level: 1, name: 'goal:ship' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '当前上下文' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'External context' })).toBeInTheDocument();
    expect(screen.getByText('projection-1')).toBeInTheDocument();
    expect(screen.queryByText('主题投影已偏旧')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '查看受限证据引用' })).toHaveAttribute('href', '/evidence');
    expect(screen.getAllByRole('button', { name: '打开只读证据抽屉' })).toHaveLength(2);
  });
});
