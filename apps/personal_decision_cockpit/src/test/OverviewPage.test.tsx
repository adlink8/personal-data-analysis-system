import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { OverviewPage } from '../pages/overview/OverviewPage';
import { ApiError } from '../api/client';
import { OVERVIEW_ENVELOPE } from './mockData';

/**
 * OverviewPage 补充测试（Phase 37 Plan 02 Task 2）：appSmoke.test.tsx 已覆盖 Now Stack 的
 * confirmation_state/importance.final_score 词汇回归；这里补充本计划新增的行为——
 * ConfirmationStateBadge/LifecycleBadge 的图标+文字渲染、offline 与 error 的区分、
 * 单节 Authority 失败时其余卡片仍可读。
 */

let currentQuery: {
  isPending: boolean;
  isError: boolean;
  error?: unknown;
  data?: unknown;
  refetch: () => void;
};

vi.mock('../api/hooks', () => ({
  useOverview: () => currentQuery,
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <OverviewPage />
    </MemoryRouter>,
  );
}

describe('OverviewPage（/）：claim/lifecycle/confirmation 视觉语义', () => {
  it('Now Stack 决策项渲染 ConfirmationStateBadge（图标 + 文字，而非只有颜色）', () => {
    currentQuery = { isPending: false, isError: false, data: OVERVIEW_ENVELOPE, refetch: vi.fn() };
    renderPage();
    const nowStack = within(screen.getByRole('heading', { level: 2, name: '现在最重要' }).closest('section')!);
    // OVERVIEW_ENVELOPE 的决策项 confirmation_state='proposed' → "待确认"徽标
    expect(nowStack.getByText('待确认')).toBeInTheDocument();
    const badge = nowStack.getByText('待确认').closest('span');
    expect(badge?.querySelector('svg')).toBeInTheDocument();
  });

  it('待决策事项卡片用 ConfirmationStateBadge 展示 queue 分组与单条状态', () => {
    currentQuery = { isPending: false, isError: false, data: OVERVIEW_ENVELOPE, refetch: vi.fn() };
    renderPage();
    const queueSection = within(screen.getByRole('heading', { level: 2, name: '待决策事项' }).closest('section')!);
    // queue: { proposed: 1 } → 分组徽标"待确认"；卡片内单条 confirmation_state 同样是 proposed
    expect(queueSection.getAllByText('待确认').length).toBeGreaterThanOrEqual(2);
  });

  it('主要变化与风险卡片用 LifecycleBadge（图标 + 文字）取代纯色文字 pill', () => {
    currentQuery = { isPending: false, isError: false, data: OVERVIEW_ENVELOPE, refetch: vi.fn() };
    renderPage();
    const changesSection = within(screen.getByRole('heading', { level: 2, name: '主要变化与风险' }).closest('section')!);
    // status_counts: { current: 30, stale: 5, conflict: 2 }
    expect(changesSection.getByText('当前')).toBeInTheDocument();
    expect(changesSection.getByText('偏旧')).toBeInTheDocument();
    expect(changesSection.getByText('冲突')).toBeInTheDocument();
    const conflictBadge = changesSection.getByText('冲突').closest('span');
    expect(conflictBadge?.querySelector('svg')).toBeInTheDocument();
  });

  it('外部环境摘要卡片始终展示"外部事实不会自动成为个人事实"隔离提示', () => {
    currentQuery = { isPending: false, isError: false, data: OVERVIEW_ENVELOPE, refetch: vi.fn() };
    renderPage();
    expect(screen.getByText('外部事实不会自动成为个人事实。')).toBeInTheDocument();
  });
});

describe('OverviewPage：offline 与 error 是不同的用户可见状态（D-37-03）', () => {
  it('network_error 渲染 offline 态：说明整个 API 不可达，不代表数据已被清空', () => {
    currentQuery = {
      isPending: false,
      isError: true,
      error: new ApiError('network_error', '无法连接后端服务，请确认 rag-api 是否在 127.0.0.1:8000 运行'),
      data: undefined,
      refetch: vi.fn(),
    };
    renderPage();
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('今日总览加载失败');
    expect(alert).toHaveTextContent('不代表数据已被清空');
    expect(screen.getByRole('button', { name: /重试/ })).toBeInTheDocument();
  });

  it('schema_mismatch 等非网络错误仍渲染普通 error 态（不误判为 offline）', () => {
    currentQuery = {
      isPending: false,
      isError: true,
      error: new ApiError('schema_mismatch', '响应格式与投影契约不一致'),
      data: undefined,
      refetch: vi.fn(),
    };
    renderPage();
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('今日总览加载失败');
    expect(alert.textContent).not.toContain('不代表数据已被清空');
  });
});

describe('OverviewPage：单一 Authority 失败只降级对应卡片（D-37-03 partial 隔离）', () => {
  it('decision 为 null 时 Now Stack/决策队列显示 partial，其余卡片仍正常渲染', () => {
    currentQuery = {
      isPending: false,
      isError: false,
      data: {
        ...OVERVIEW_ENVELOPE,
        partial: true,
        limitations: ['决策分析 Authority 本次不可用'],
        data: { ...OVERVIEW_ENVELOPE.data, decision: null },
      },
      refetch: vi.fn(),
    };
    renderPage();
    // 决策队列卡片显式列出不可用 Authority（Now Stack 也会因同一原因显示 partial，此处允许多处出现）
    expect(screen.getByText('决策队列暂不可用')).toBeInTheDocument();
    expect(screen.getAllByText('决策分析').length).toBeGreaterThanOrEqual(1);
    // 个人状态/外部环境卡片仍正常渲染（不整页白）
    expect(screen.getByText('当前目标与约束')).toBeInTheDocument();
    expect(screen.getByText('外部环境摘要')).toBeInTheDocument();
  });
});
