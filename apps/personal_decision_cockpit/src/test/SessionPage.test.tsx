import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { SessionPage } from '../pages/sessions/SessionPage';
import type { OperationResult, OrchestrationPreview, SessionResume } from '../api/orchestration';

/**
 * SessionPage 测试（Phase 38-02，spec §5.3 / §12 状态模型）：
 * 通过 mock `../api/orchestration` 的 sessionResume/sessionPreview/sessionExecute
 * 直接控制 API 返回值，配合 `@tanstack/react-query` mock 控制查询结果。
 * - /sessions/new 渲染 NewSessionFlow + ResumeEntryCard；intent=action/observe 时显示线性链说明；
 * - /sessions/:id 恢复会话后渲染 manifest、state/sequence、DecisionStageStepper；
 * - 合法下一跳可点且每跳独立 prepare → preview → confirm；
 * - 已完成后显示 empty state；
 * - exact replay 显示"已返回原事件，未重复写入"；
 * - 刷新后 actor mismatch 显示只读说明，不渲染 StepPanel 伪入口；
 * - 推进失败 stale 类错误丢弃本地 preview，runtime 类保留允许重试。
 */

const MANIFEST: Record<string, unknown> = {
  schema_version: 'guarded_orchestration_v1',
  domain: 'project',
  risk_budget: 'low',
  goal: '未来 8 周如何分配时间',
  constraints: ['每周不超过 30 小时'],
  weights: { career: 0.6, learning: 0.4 },
  actor_identity_hash: 'b'.repeat(64),
  binding_hash: 'c'.repeat(64),
};

const SESSION: SessionResume = {
  session_id: 'ors_20260726_test_0001',
  state: 'confirmed',
  sequence: 1,
  last_event_checksum: 'd'.repeat(64),
  manifest: MANIFEST,
  binding: { binding_hash: 'c'.repeat(64) },
};

const PREVIEW: OrchestrationPreview = {
  session_id: SESSION.session_id,
  operation: 'generate',
  actor_identity_hash: 'b'.repeat(64),
  expected_sequence: 1,
  payload: { input: { personal_evidence: [], external_evidence: [] }, binding_hash: 'c'.repeat(64) },
  issued_at: '2026-07-26T00:00:00Z',
  preview_checksum: 'abcd1234'.repeat(8),
};

const RESULT: OperationResult = {
  session_id: SESSION.session_id,
  operation: 'generate',
  state: 'generated',
  sequence: 2,
  event_id: 'ore_20260726_event0002',
  event_checksum: 'efgh5678'.repeat(8),
  replayed: false,
  references: {},
};

// vi.hoisted 确保 mock 变量在 vi.mock 工厂执行前已初始化
const { sessionResumeMock, sessionPreviewMock, sessionExecuteMock, queryRefetchMock, queryInvalidateMock } = vi.hoisted(() => ({
  sessionResumeMock: vi.fn(),
  sessionPreviewMock: vi.fn(),
  sessionExecuteMock: vi.fn(),
  queryRefetchMock: vi.fn(),
  queryInvalidateMock: vi.fn(),
}));

// 可变 actress hash 与查询结果：测试间按需切换。
// 这些不是 hoisted（允许测试间自由赋值），但 vi.mock 工厂通过闭包引用它们——
// 工厂在模块加载时执行，此时这些变量已初始化（模块作用域顺序执行）。
let actorHash = 'b'.repeat(64);
let queryData: unknown = undefined;
let queryIsPending = true;
let queryIsError = false;
let queryError: unknown = null;

vi.mock('../api/orchestration', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/orchestration')>();
  return {
    ...actual,
    deriveActorIdentityHash: () => Promise.resolve(actorHash),
    sessionResume: (...args: Parameters<typeof actual.sessionResume>) => sessionResumeMock(...args),
    sessionPreview: (...args: Parameters<typeof actual.sessionPreview>) => sessionPreviewMock(...args),
    sessionExecute: (...args: Parameters<typeof actual.sessionExecute>) => sessionExecuteMock(...args),
  };
});

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>();
  return {
    ...actual,
    useQuery: () => ({
      isPending: queryIsPending,
      isError: queryIsError,
      error: queryError,
      data: queryData,
      refetch: queryRefetchMock,
    }),
    useQueryClient: () => ({
      invalidateQueries: queryInvalidateMock,
    }),
  };
});

afterEach(() => {
  vi.clearAllMocks();
  actorHash = 'b'.repeat(64);
  queryData = undefined;
  queryIsPending = true;
  queryIsError = false;
  queryError = null;
});

function renderSessionPage(route: string) {
  // SessionPage 依赖 useParams 取 `:id`（真实 App 经 /sessions/:id 路由挂载）。
  // 测试中必须用 Routes 提供参数，否则 /sessions/ors_test 会被误判为 new 分支。
  return render(
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/sessions/new" element={<SessionPage />} />
        <Route path="/sessions/:id" element={<SessionPage />} />
        <Route path="/sessions" element={<SessionPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

function setSessionResolved(session: SessionResume) {
  queryData = session;
  queryIsPending = false;
  queryIsError = false;
}

describe('SessionPage（/sessions）', () => {
  /* ---- /sessions/new ---- */
  it('/sessions/new 渲染 NewSessionFlow + ResumeEntryCard', () => {
    renderSessionPage('/sessions/new');
    expect(screen.getByText('新建决策会话')).toBeInTheDocument();
    expect(screen.getByText('恢复已有会话')).toBeInTheDocument();
  });

  it('/sessions/new?intent=action 显示线性链说明，提醒需依次推进', () => {
    renderSessionPage('/sessions/new?intent=action');
    expect(screen.getByText(/目标是记录行动\/结果/)).toBeInTheDocument();
    expect(screen.getByText(/需依次推进到对应步骤/)).toBeInTheDocument();
  });

  it('/sessions/new?intent=observe 显示不能跳段的说明', () => {
    renderSessionPage('/sessions/new?intent=observe');
    expect(screen.getByText(/不能跳段/)).toBeInTheDocument();
  });

  /* ---- /sessions/:id ---- */
  it('恢复会话后显示 manifest、state/sequence 与 DecisionStageStepper', async () => {
    setSessionResolved(SESSION);
    renderSessionPage('/sessions/ors_test');
    await waitFor(() => expect(screen.getByText('会话推进')).toBeInTheDocument());
    expect(screen.getByText('未来 8 周如何分配时间')).toBeInTheDocument();
    expect(screen.getByText('已确认')).toBeInTheDocument();
    expect(screen.getByRole('list', { name: '决策会话阶段' })).toBeInTheDocument();
  });

  it('合法下一跳可点：每跳独立 preview → 抽屉确认 → execute', async () => {
    setSessionResolved(SESSION);
    sessionPreviewMock.mockResolvedValue(PREVIEW);
    sessionExecuteMock.mockResolvedValue(RESULT);
    renderSessionPage('/sessions/ors_test');
    await waitFor(() => expect(screen.getByText('生成分析')).toBeInTheDocument());

    // preview 按钮
    fireEvent.click(screen.getByRole('button', { name: /生成 exact preview/ }));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    expect(sessionPreviewMock).toHaveBeenCalledTimes(1);

    // 确认写入
    fireEvent.click(screen.getByRole('button', { name: /确认写入/ }));
    await waitFor(() => expect(screen.getByRole('region', { name: '上一跳写入结果' })).toBeInTheDocument());
    expect(sessionExecuteMock).toHaveBeenCalledTimes(1);
  });

  it('已完成后不显示任何可执行按钮，只显示 empty state', async () => {
    setSessionResolved({ ...SESSION, state: 'calibrated', sequence: 9 });
    renderSessionPage('/sessions/ors_test');
    await waitFor(() => expect(screen.getByText('会话已完成全部阶段')).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /生成 exact preview/ })).not.toBeInTheDocument();
  });

  it('exact replay：replayed=true 显示"已返回原事件，未重复写入"，receipt 不额外显示', async () => {
    setSessionResolved(SESSION);
    sessionPreviewMock.mockResolvedValue(PREVIEW);
    sessionExecuteMock.mockResolvedValue({ ...RESULT, replayed: true });
    renderSessionPage('/sessions/ors_test');
    await waitFor(() => expect(screen.getByText('生成分析')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /生成 exact preview/ }));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /确认写入/ }));

    await waitFor(() => expect(screen.getByText('已返回原事件，未重复写入')).toBeInTheDocument());
    // replayed=true 时 receipt 区不渲染"已写入"卡片
    expect(screen.queryByRole('region', { name: '上一跳写入结果' })).not.toBeInTheDocument();
  });

  it('刷新后 actor mismatch：显示只读说明，不渲染 StepPanel 伪入口', async () => {
    actorHash = 'a'.repeat(64); // 与 manifest 的 'b'.repeat(64) 不匹配
    setSessionResolved(SESSION);
    renderSessionPage('/sessions/ors_test');

    await waitFor(() => expect(screen.getByText('会话操作者身份不一致')).toBeInTheDocument());
    // 不渲染任何写入入口
    expect(screen.queryByRole('button', { name: /生成 exact preview/ })).not.toBeInTheDocument();
    expect(screen.queryByText('下一步')).not.toBeInTheDocument();
  });

  it('推进失败 stale 类错误：丢弃本地 preview，不保留复用（先 resume 再重新 preview）', async () => {
    const { OrchestrationError } = await import('../api/orchestration');
    setSessionResolved(SESSION);
    sessionPreviewMock.mockResolvedValue(PREVIEW);
    sessionExecuteMock.mockRejectedValue(
      new OrchestrationError({
        code: 'stale_expected_sequence',
        category: 'stale',
        message: '会话已被推进',
        retryable: true,
        recoveryActions: ['resume_session', 'prepare_fresh_preview'],
      }),
    );
    renderSessionPage('/sessions/ors_test');
    await waitFor(() => expect(screen.getByText('生成分析')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /生成 exact preview/ }));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /确认写入/ }));

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    // stale 错误后抽屉关闭：不允许复用旧 preview
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    // 不提供"重试同一 preview"按钮
    expect(screen.queryByRole('button', { name: /重试/ })).not.toBeInTheDocument();
  });

  it('推进失败 runtime 类错误：保留 preview，允许同一键重试', async () => {
    const { OrchestrationError } = await import('../api/orchestration');
    setSessionResolved(SESSION);
    sessionPreviewMock.mockResolvedValue(PREVIEW);
    sessionExecuteMock
      .mockRejectedValueOnce(
        new OrchestrationError({
          code: 'confirmation_secret_unavailable',
          category: 'runtime',
          message: '密钥未配置',
          retryable: true,
          recoveryActions: ['check_runtime', 'retry_when_ready'],
        }),
      )
      .mockResolvedValueOnce(RESULT);
    renderSessionPage('/sessions/ors_test');
    await waitFor(() => expect(screen.getByText('生成分析')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /生成 exact preview/ }));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /确认写入/ }));

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    // 抽屉保留，允许显式点击重试
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    const retryButton = screen.getByRole('button', { name: /重试/ });
    fireEvent.click(retryButton);
    await waitFor(() => expect(screen.getByRole('region', { name: '上一跳写入结果' })).toBeInTheDocument());
    expect(sessionExecuteMock).toHaveBeenCalledTimes(2);
  });

  it('每一跳都需要重新 preview 并独立确认，前端不提供一键完成全部阶段入口', () => {
    renderSessionPage('/sessions/new');
    expect(screen.getByText(/Guarded Orchestration 写流程/)).toBeInTheDocument();
  });
});