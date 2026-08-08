import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { KnowledgeDirectoryPage } from '../pages/knowledge/KnowledgeDirectoryPage';

const queryState: any = {
  isPending: false,
  isError: false,
  error: null,
  refetch: vi.fn(),
  data: {
    schema_version: 'personal_wiki_projection_v1' as const,
    operation: 'topic.list' as const,
    ok: true,
    generated_at: '2026-07-28T00:00:00Z',
    snapshot_bindings: {},
    freshness: { state: 'fresh' as const },
    authorities: { personal: 'ok' },
    partial: false,
    limitations: [],
    projection_checksum: 'c1',
    status: 'fresh' as const,
    data: {
      items: [
        { topic_id: 'topic_project', topic_type: 'project' as const, canonical_key: 'project:alpha', display_label: 'project:alpha', authority: 'ok', snapshot_id: null, freshness: 'fresh' },
        { topic_id: 'topic_goal', topic_type: 'goal' as const, canonical_key: 'goal:work:personal:ship', display_label: 'goal:ship', authority: 'ok', snapshot_id: null, freshness: 'fresh' },
        { topic_id: 'topic_decision', topic_type: 'decision' as const, canonical_key: 'decision:rec-1', display_label: 'decision:rec-1', authority: 'ok', snapshot_id: 'ds-1', freshness: 'fresh' },
      ],
      total_available: 3,
      limit: 50,
      next_cursor: null,
    },
  },
};

vi.mock('../api/hooks', () => ({ useWikiTopicList: () => queryState }));

describe('KnowledgeDirectoryPage', () => {
  beforeEach(() => {
    queryState.refetch.mockClear();
  });

  it('renders all P0 types with opaque routes and no write controls', () => {
    render(<MemoryRouter><KnowledgeDirectoryPage /></MemoryRouter>);
    expect(screen.getByRole('heading', { level: 1, name: '知识与证据' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '打开project:alpha' })).toHaveAttribute('href', '/knowledge/project/topic_project');
    expect(screen.getByRole('link', { name: '打开goal:ship' })).toHaveAttribute('href', '/knowledge/goal/topic_goal');
    expect(screen.getByRole('link', { name: '打开decision:rec-1' })).toHaveAttribute('href', '/knowledge/decision/topic_decision');
    expect(screen.getAllByText('投影：fresh')).toHaveLength(3);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByText(/不是新的事实库/)).toBeInTheDocument();
  });

  it('distinguishes partial directory from an empty directory', () => {
    queryState.data = { ...queryState.data, partial: true, status: 'partial', limitations: ['Decision authority 不可用'], authorities: { personal: 'ok', decision: 'error' } };
    render(<MemoryRouter><KnowledgeDirectoryPage /></MemoryRouter>);
    expect(screen.getByText('目录部分可用')).toBeInTheDocument();
    expect(screen.getByText('Decision authority 不可用')).toBeInTheDocument();
  });

  it('keeps a missing derived projection explicit', () => {
    queryState.data = {
      ...queryState.data,
      partial: true,
      status: 'partial',
      data: {
        ...queryState.data.data,
        items: [{ ...queryState.data.data.items[0], freshness: 'missing' }],
      },
    };
    render(<MemoryRouter><KnowledgeDirectoryPage /></MemoryRouter>);
    expect(screen.getByText('投影：missing')).toBeInTheDocument();
    expect(screen.queryByText('投影：unknown')).not.toBeInTheDocument();
  });
});
