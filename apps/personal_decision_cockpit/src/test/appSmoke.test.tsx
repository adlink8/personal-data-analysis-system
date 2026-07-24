import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';
import { appRoutes } from '../app/router';
import { AppProviders } from '../app/providers';
import { ApiError } from '../api/client';
import {
  ACTIONS_RECENT_ENVELOPE,
  CALIBRATION_OVERVIEW_ENVELOPE,
  DECISION_QUEUE_ENVELOPE,
  DECISION_WORKSPACE_ENVELOPE,
  EXTERNAL_DELTA_ENVELOPE,
  OVERVIEW_ENVELOPE,
  PERSONAL_STATE_ENVELOPE,
  PROACTIVE_SUMMARY_ENVELOPE,
  SYSTEM_STATUS_ENVELOPE,
} from './mockData';

/**
 * 全路由渲染冒烟（Phase 40，spec §17）：mock 全部 API hooks（与既有页面测试同法，
 * 返回 mockData 手工信封），用 createMemoryRouter 复用生产路由表 appRoutes 逐个挂载
 * 11 条路由，断言每条都渲染出页面 h1 / 标志文案且不抛错——在无浏览器环境下抓运行时渲染崩溃。
 * 另有 REST 离线用例：hooks 抛网络错误时总览页显示 role="alert" + 重试，不白屏。
 */

interface QueryState {
  isPending: boolean;
  isError: boolean;
  error: unknown;
  data: unknown;
  refetch: () => void;
}

const queryOk = (data: unknown): QueryState => ({
  isPending: false,
  isError: false,
  error: null,
  data,
  refetch: vi.fn(),
});

const defaultHooksState = (): Record<string, QueryState> => ({
  overview: queryOk(OVERVIEW_ENVELOPE),
  systemStatus: queryOk(SYSTEM_STATUS_ENVELOPE),
  personalState: queryOk(PERSONAL_STATE_ENVELOPE),
  externalDelta: queryOk(EXTERNAL_DELTA_ENVELOPE),
  decisionQueue: queryOk(DECISION_QUEUE_ENVELOPE),
  decisionWorkspace: queryOk(DECISION_WORKSPACE_ENVELOPE),
  actionsRecent: queryOk(ACTIONS_RECENT_ENVELOPE),
  proactiveSummary: queryOk(PROACTIVE_SUMMARY_ENVELOPE),
  calibrationOverview: queryOk(CALIBRATION_OVERVIEW_ENVELOPE),
});

let hooksState = defaultHooksState();

vi.mock('../api/hooks', () => ({
  useOverview: () => hooksState.overview,
  useSystemStatus: () => hooksState.systemStatus,
  usePersonalState: () => hooksState.personalState,
  useExternalDelta: () => hooksState.externalDelta,
  useDecisionQueue: () => hooksState.decisionQueue,
  useDecisionWorkspace: () => hooksState.decisionWorkspace,
  useActionsRecent: () => hooksState.actionsRecent,
  useProactiveSummary: () => hooksState.proactiveSummary,
  useCalibrationOverview: () => hooksState.calibrationOverview,
  // 按需触发的直读 hooks：冒烟场景不展开，返回静止态
  useProactiveCandidateExplain: () => ({ isPending: false, isError: false, data: undefined }),
  useProactiveControlStatus: () => ({ isPending: false, isError: false, data: undefined }),
}));

function renderRoute(path: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] });
  return render(
    <AppProviders>
      <RouterProvider router={router} />
    </AppProviders>,
  );
}

// 11 条路由：八项主导航 + 领域详情 + 决策工作区 + 会话新建
const ROUTES: ReadonlyArray<{ path: string; heading: string; markerText?: string }> = [
  { path: '/', heading: '今日总览', markerText: '现在最重要' },
  { path: '/state', heading: '个人状态', markerText: '八领域状态' },
  { path: '/state/project', heading: '项目领域' },
  { path: '/decisions', heading: '决策中心', markerText: '需要关注' },
  { path: '/decisions/rec_attn_001', heading: 'rec_attn_001', markerText: '决策工作区' },
  { path: '/actions', heading: '行动与结果', markerText: '最近行动' },
  { path: '/external', heading: '外部环境', markerText: '外部事实不会自动成为个人事实。' },
  { path: '/proactive', heading: '主动提醒', markerText: '需要现在处理' },
  { path: '/evidence', heading: '证据中心', markerText: '数据浏览器' },
  { path: '/system', heading: '系统状态', markerText: '运行概览' },
  { path: '/sessions/new', heading: '新建决策会话', markerText: '定义决策问题' },
];

describe('全路由渲染冒烟（appSmoke）', () => {
  beforeEach(() => {
    hooksState = defaultHooksState();
  });

  it.each(ROUTES)('路由 $path 渲染页面标志元素且不抛错', ({ path, heading, markerText }) => {
    renderRoute(path);
    expect(screen.getByRole('heading', { level: 1, name: heading })).toBeInTheDocument();
    if (markerText) {
      expect(screen.getAllByText(markerText).length).toBeGreaterThanOrEqual(1);
    }
  });

  it('REST 离线（hooks 抛网络错误）时总览页显示 role="alert" 与重试路径，不白屏', () => {
    hooksState = {
      ...defaultHooksState(),
      overview: {
        isPending: false,
        isError: true,
        error: new ApiError('network_error', '无法连接后端服务，请确认 rag-api 是否在 127.0.0.1:8000 运行'),
        data: undefined,
        refetch: vi.fn(),
      },
    };
    renderRoute('/');
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('今日总览加载失败');
    expect(alert).toHaveTextContent('无法连接后端服务');
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument();
  });
});
