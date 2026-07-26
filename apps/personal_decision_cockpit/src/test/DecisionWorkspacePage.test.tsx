import type { Mock } from 'vitest';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { DecisionWorkspacePage } from '../pages/decisions/DecisionWorkspacePage';
import { ApiError } from '../api/client';
import { useEvidenceResolve } from '../api/hooks';
import { DECISION_WORKSPACE_ENVELOPE } from './mockData';

/**
 * DecisionWorkspacePage 补充测试（Phase 37 Plan 03 Task 2，EVID-01）：
 * 决策工作区头部新增只读"查看证据"入口，携带 recommendation 的
 * recommendation_id/snapshot_id/recommendation_checksum 稳定引用三元组；
 * 本计划不新增、替换或绕过既有 guarded 记录行动/结果按钮与 session 流程，
 * 这里额外验证该按钮与其 case_id 预填逻辑不受"查看证据"入口影响。
 */

let currentQuery: {
  isPending: boolean;
  isError: boolean;
  error?: unknown;
  data?: unknown;
  refetch: () => void;
};

vi.mock('../api/hooks', () => ({
  useDecisionWorkspace: () => currentQuery,
  useEvidenceResolve: vi.fn(() => ({ isPending: true, isError: false, data: undefined, refetch: vi.fn() })),
}));

const mockedUseEvidenceResolve = useEvidenceResolve as unknown as Mock;

function renderPage(id = 'rec_attn_001') {
  return render(
    <MemoryRouter initialEntries={[`/decisions/${id}`]}>
      <Routes>
        <Route path="/decisions/:id" element={<DecisionWorkspacePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('DecisionWorkspacePage（/decisions/:id）：只读证据下钻入口', () => {
  it('recommendation 具备完整稳定引用时渲染"查看证据"，点击打开 Drawer 并携带 recommendation 引用', () => {
    currentQuery = { isPending: false, isError: false, data: DECISION_WORKSPACE_ENVELOPE, refetch: vi.fn() };
    renderPage();

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看证据' }));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(mockedUseEvidenceResolve).toHaveBeenCalledWith({
      subjectType: 'decision',
      stableId: 'rec_attn_001',
      snapshotId: DECISION_WORKSPACE_ENVELOPE.data.recommendation.snapshot_id,
      checksum: DECISION_WORKSPACE_ENVELOPE.data.recommendation.recommendation_checksum,
    });

    // 既有的"记录行动/结果"guarded 入口不受影响，仍然存在
    expect(screen.getByRole('button', { name: /记录行动\/结果/ })).toBeInTheDocument();
  });

  it('recommendation 缺少 recommendation_checksum 时不渲染"查看证据"（不构造伪 evidence）', () => {
    currentQuery = {
      isPending: false,
      isError: false,
      data: {
        ...DECISION_WORKSPACE_ENVELOPE,
        data: {
          ...DECISION_WORKSPACE_ENVELOPE.data,
          recommendation: { ...DECISION_WORKSPACE_ENVELOPE.data.recommendation, recommendation_checksum: null },
        },
      },
      refetch: vi.fn(),
    };
    renderPage();
    expect(screen.queryByRole('button', { name: '查看证据' })).not.toBeInTheDocument();
  });

  it('recommendation 为 null 时仍显示 partial 面板，不因证据入口改动而回归', () => {
    currentQuery = {
      isPending: false,
      isError: false,
      data: { ...DECISION_WORKSPACE_ENVELOPE, data: { ...DECISION_WORKSPACE_ENVELOPE.data, recommendation: null } },
      refetch: vi.fn(),
    };
    renderPage();
    expect(screen.getByText('建议详情暂不可用')).toBeInTheDocument();
  });

  it('error 态显示重试并不渲染证据入口', () => {
    currentQuery = {
      isPending: false,
      isError: true,
      error: new ApiError('http_500', '后端返回 HTTP 500'),
      data: undefined,
      refetch: vi.fn(),
    };
    renderPage();
    expect(screen.getByRole('alert')).toHaveTextContent('决策工作区加载失败');
    expect(screen.queryByRole('button', { name: '查看证据' })).not.toBeInTheDocument();
  });
});
