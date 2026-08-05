import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
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
  piOperations: queryOk({ schema_version: 'pi_operation_projection_v1', ok: true, state: 'ready', operations: [], observed_at: '2026-08-05T00:00:00Z', recovery_action: 'none' }),
  personalState: queryOk(PERSONAL_STATE_ENVELOPE),
  externalDelta: queryOk(EXTERNAL_DELTA_ENVELOPE),
  decisionQueue: queryOk(DECISION_QUEUE_ENVELOPE),
  decisionWorkspace: queryOk(DECISION_WORKSPACE_ENVELOPE),
  actionsRecent: queryOk(ACTIONS_RECENT_ENVELOPE),
  proactiveSummary: queryOk(PROACTIVE_SUMMARY_ENVELOPE),
  calibrationOverview: queryOk(CALIBRATION_OVERVIEW_ENVELOPE),
  wikiTopicList: queryOk({
    schema_version: 'personal_wiki_projection_v1', operation: 'topic.list', ok: true,
    generated_at: '2026-07-28T00:00:00Z', snapshot_bindings: {}, freshness: { state: 'fresh' },
    authorities: {}, partial: false, limitations: [], projection_checksum: 'wiki-list', status: 'fresh',
    data: { items: [{ topic_id: 'topic_goal', topic_type: 'goal', canonical_key: 'goal:work:personal:ship', display_label: 'goal:ship', authority: 'ok', snapshot_id: 'ps', freshness: 'fresh' }], total_available: 1, limit: 50, next_cursor: null },
  }),
  wikiTopic: queryOk({
    schema_version: 'personal_wiki_projection_v1', operation: 'topic.get', ok: true,
    generated_at: '2026-07-28T00:00:00Z', snapshot_bindings: { personal: 'ps' }, freshness: { state: 'fresh' },
    authorities: { personal: 'ok' }, partial: false, limitations: [], projection_checksum: 'wiki-get', status: 'fresh',
    data: { topic: { topic_id: 'topic_goal', topic_type: 'goal', canonical_key: 'goal:work:personal:ship', display_label: 'goal:ship' }, claims: { current: [], observations: [], inferences: [], recommendations: [], historical: [], conflicts: [], external: [], decision_feedback: [] }, evidence_refs: [] },
  }),
  wikiTopicBacklinks: queryOk({
    schema_version: 'personal_wiki_projection_v1', operation: 'topic.backlinks', ok: true,
    snapshot_bindings: {}, freshness: { state: 'fresh' }, authorities: {}, partial: false, limitations: [], projection_checksum: 'wiki-links', status: 'fresh',
    data: { topic: { topic_id: 'topic_goal', topic_type: 'goal', canonical_key: 'goal:work:personal:ship' }, links: [] },
  }),
  wikiTopicResolve: queryOk({
    schema_version: 'personal_wiki_projection_v1', operation: 'topic.resolve', ok: true,
    snapshot_bindings: {}, freshness: { state: 'fresh' }, authorities: {}, partial: false, limitations: [], projection_checksum: 'wiki-resolve', status: 'fresh',
    data: { selected_source: 'fresh_wiki', attempted_sources: ['wiki'], fallback_reason: null, source: {}, topic: { topic_id: 'topic_goal', topic_type: 'goal', canonical_key: 'goal:work:personal:ship' } },
  }),
});

let hooksState = defaultHooksState();

vi.mock('../api/hooks', () => ({
  useOverview: () => hooksState.overview,
  useSystemStatus: () => hooksState.systemStatus,
  usePiOperations: () => hooksState.piOperations,
  usePiOperationMutation: () => ({ isPending: false, mutate: vi.fn() }),
  usePersonalState: () => hooksState.personalState,
  useExternalDelta: () => hooksState.externalDelta,
  useDecisionQueue: () => hooksState.decisionQueue,
  useDecisionWorkspace: () => hooksState.decisionWorkspace,
  useActionsRecent: () => hooksState.actionsRecent,
  useProactiveSummary: () => hooksState.proactiveSummary,
  useCalibrationOverview: () => hooksState.calibrationOverview,
  useWikiTopicList: () => hooksState.wikiTopicList,
  useWikiTopic: () => hooksState.wikiTopic,
  useWikiTopicBacklinks: () => hooksState.wikiTopicBacklinks,
  useWikiTopicResolve: () => hooksState.wikiTopicResolve,
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
  { path: '/knowledge', heading: '知识与证据', markerText: 'P0 主题目录' },
  { path: '/knowledge/goal/topic_goal', heading: 'goal:ship', markerText: '当前上下文' },
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

  it('解析失败（schema_mismatch）时总览页只显示安全 code/message，不把响应 body 打到 console（D-36-06）', () => {
    const logSpy = vi.spyOn(console, 'log').mockImplementation(() => undefined);
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    // 模拟响应格式与投影契约不一致：hooks 层已把这类失败归一为 ApiError('schema_mismatch', ...)，
    // 页面只应渲染安全消息，绝不重新打印原始响应体（poisoned 片段仅存在于此断言里，不应出现在 DOM）。
    const poisonedFragment = 'confirmation_token=abcd1234;HMAC-SHA256=deadbeef;C:\\secret\\personal.sqlite';
    hooksState = {
      ...defaultHooksState(),
      overview: {
        isPending: false,
        isError: true,
        error: new ApiError('schema_mismatch', '响应格式与投影契约 decision_cockpit_projection_v1 不一致'),
        data: undefined,
        refetch: vi.fn(),
      },
    };
    renderRoute('/');
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('响应格式与投影契约');
    expect(alert.textContent).not.toContain(poisonedFragment);
    expect(logSpy).not.toHaveBeenCalled();
    expect(errorSpy).not.toHaveBeenCalled();
    expect(warnSpy).not.toHaveBeenCalled();
    logSpy.mockRestore();
    errorSpy.mockRestore();
    warnSpy.mockRestore();
  });
});

/**
 * Now Stack 真实 confirmation_state / importance.final_score 词汇回归（D-36-05）：
 * 修正前 OverviewPage 用旧假设 `confirmation_state === 'confirmed'` 与
 * `importance.score >= 0.7` 派生"现在最重要"，而权威真实词汇是
 * {proposed, accepted, rejected, deferred, revoked} 与 `importance.final_score`
 * （见 ui_projection.py `_KNOWN_CONFIRMATION_STATES` / `_proactive_inbox_section`）。
 * 这里只验证页面展示，不调用任何 ranking/lifecycle/confirmation 写接口。
 */
describe('OverviewPage：Now Stack 使用真实 confirmation_state 与 importance.final_score', () => {
  beforeEach(() => {
    hooksState = defaultHooksState();
  });

  /** Now Stack 与 ProactiveCard/DecisionQueueCard 会重复展示同一候选/决策，必须限定在"现在最重要"卡片内断言。 */
  function nowStackSection(): HTMLElement {
    return screen.getByRole('heading', { level: 2, name: '现在最重要' }).closest('section') as HTMLElement;
  }

  function overviewWith(decisionItems: unknown[], proactiveItems: unknown[]) {
    return {
      ...OVERVIEW_ENVELOPE,
      data: {
        ...OVERVIEW_ENVELOPE.data,
        decision: { total_available: decisionItems.length, queue: {}, items: decisionItems },
        proactive: { total_available: proactiveItems.length, items: proactiveItems },
      },
    };
  }

  it('proposed/accepted 决策项进入 Now Stack；rejected 被排除', () => {
    const decisionItems = [
      {
        recommendation_id: 'rec_proposed_now',
        domain: 'career',
        recommendation_kind: 'time_allocation',
        horizon: '8w',
        confidence: 0.6,
        confirmation_state: 'proposed',
        action_state: null,
        expires_at: '2026-08-01T00:00:00Z',
      },
      {
        recommendation_id: 'rec_accepted_now',
        domain: 'project',
        recommendation_kind: 'scope_control',
        horizon: '2w',
        confidence: 0.9,
        confirmation_state: 'accepted',
        action_state: 'started',
        expires_at: '2026-08-05T00:00:00Z',
      },
      {
        recommendation_id: 'rec_rejected_hidden',
        domain: 'learning',
        recommendation_kind: 'habit_change',
        horizon: '12w',
        confidence: 0.4,
        confirmation_state: 'rejected',
        action_state: 'not_taken',
        expires_at: '2026-06-01T00:00:00Z',
      },
    ];
    hooksState = { ...defaultHooksState(), overview: queryOk(overviewWith(decisionItems, [])) };
    renderRoute('/');
    const nowStack = within(nowStackSection());
    // 已接受语义正确展示（不是"待确认”话术，直接透出真实状态值）
    expect(nowStack.getByText((text) => text.includes('确认状态：proposed'))).toBeInTheDocument();
    expect(nowStack.getByText((text) => text.includes('确认状态：accepted'))).toBeInTheDocument();
    expect(nowStack.queryByText((text) => text.includes('确认状态：rejected'))).not.toBeInTheDocument();
  });

  it('deferred/revoked 决策项不出现在 Now Stack（结案不等于待确认）', () => {
    const decisionItems = [
      {
        recommendation_id: 'rec_deferred_hidden',
        domain: 'finance',
        recommendation_kind: 'budget_shift',
        horizon: '4w',
        confidence: 0.5,
        confirmation_state: 'deferred',
        action_state: null,
        expires_at: '2026-07-01T00:00:00Z',
      },
      {
        recommendation_id: 'rec_revoked_hidden',
        domain: 'health',
        recommendation_kind: 'routine_change',
        horizon: '2w',
        confidence: 0.3,
        confirmation_state: 'revoked',
        action_state: null,
        expires_at: '2026-06-15T00:00:00Z',
      },
    ];
    hooksState = { ...defaultHooksState(), overview: queryOk(overviewWith(decisionItems, [])) };
    renderRoute('/');
    const nowStack = within(nowStackSection());
    expect(nowStack.queryByText((text) => text.includes('确认状态：deferred'))).not.toBeInTheDocument();
    expect(nowStack.queryByText((text) => text.includes('确认状态：revoked'))).not.toBeInTheDocument();
    // 无未结案决策、无高重要主动提醒 → 空态提示，而非白屏或误判为待处理
    expect(nowStack.getByText('暂无需要立即关注的事项')).toBeInTheDocument();
  });

  it('只有 importance.final_score >= 阈值才进入 Now Stack；缺失/低于阈值/旧 score 字段一律不算', () => {
    const proactiveItems = [
      {
        candidate_id: 'cand_h1',
        domains: ['career'],
        importance: { final_score: 0.8, score: 0.1 }, // final_score 高但旧 score 字段低：必须读 final_score
        candidate_class: 'opportunity',
        expires_at: '2026-08-01T00:00:00Z',
        reason_codes: ['marker_final_score_high'],
      },
      {
        candidate_id: 'cand_l1',
        domains: ['learning'],
        importance: { score: 0.99, level: 'high' }, // 只有旧字段，没有 final_score：不应被当作高重要
        candidate_class: 'opportunity',
        expires_at: '2026-08-01T00:00:00Z',
        reason_codes: ['marker_legacy_field_only'],
      },
      {
        candidate_id: 'cand_b1',
        domains: ['project'],
        importance: { final_score: 0.2 },
        candidate_class: 'maintenance',
        expires_at: '2026-08-01T00:00:00Z',
        reason_codes: ['marker_below_threshold'],
      },
    ];
    hooksState = { ...defaultHooksState(), overview: queryOk(overviewWith([], proactiveItems)) };
    renderRoute('/');
    const nowStack = within(nowStackSection());
    expect(nowStack.getByText((text) => text.includes('marker_final_score_high'))).toBeInTheDocument();
    expect(nowStack.queryByText((text) => text.includes('marker_legacy_field_only'))).not.toBeInTheDocument();
    expect(nowStack.queryByText((text) => text.includes('marker_below_threshold'))).not.toBeInTheDocument();
  });
});
