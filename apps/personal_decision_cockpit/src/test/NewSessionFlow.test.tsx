import { afterEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { NewSessionFlow } from '../components/decision/NewSessionFlow';
import type { OperationResult, OrchestrationPreview } from '../api/orchestration';

/**
 * NewSessionFlow 测试（Phase 38-02，spec §5.2/§5.3 + RESEARCH.md「Exact Preview and
 * Confirmation Rules」/「Typed Recovery Matrix」）：
 * - 表单只接受固定 project/low（无可编辑域字段）；prepare 明确标注"不会写入"；
 * - prepare 成功后弹出 ConfirmDrawer，取消/关闭零 POST；
 * - confirm 成功显示 sequence/event_id/event_checksum，replayed=true 不显示"已创建"卡片；
 * - confirm 遇到 stale/confirmation 类错误时丢弃本地 preview（不允许静默复用已过期 Preview
 *   重新提交），遇到 runtime 类错误保留 preview 允许同一键重试；
 * - 全程不存在"一键跑完全部阶段"的入口。
 */

const PREVIEW: OrchestrationPreview = {
  session_id: 'ors_20260726_test_0001',
  operation: 'confirm',
  actor_identity_hash: 'a'.repeat(64),
  expected_sequence: 0,
  payload: { schema_version: 'guarded_orchestration_v1', goal: '未来 8 周如何分配时间' },
  issued_at: '2026-07-26T00:00:00Z',
  preview_checksum: 'abcd1234'.repeat(8),
};

const RESULT: OperationResult = {
  session_id: PREVIEW.session_id,
  operation: 'confirm',
  state: 'confirmed',
  sequence: 1,
  event_id: 'ore_20260726_event0001',
  event_checksum: 'efgh5678'.repeat(8),
  replayed: false,
  references: {},
};

const sessionPrepareMock = vi.fn();
const sessionConfirmMock = vi.fn();

vi.mock('../api/orchestration', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/orchestration')>();
  return {
    ...actual,
    sessionPrepare: (...args: Parameters<typeof actual.sessionPrepare>) => sessionPrepareMock(...args),
    sessionConfirm: (...args: Parameters<typeof actual.sessionConfirm>) => sessionConfirmMock(...args),
    deriveActorIdentityHash: async () => 'a'.repeat(64),
  };
});

afterEach(() => {
  vi.clearAllMocks();
});

function fillValidForm() {
  fireEvent.change(screen.getByLabelText('决策问题（goal）'), { target: { value: '未来 8 周如何分配时间' } });
  fireEvent.change(screen.getByLabelText('约束 1'), { target: { value: '每周不超过 30 小时' } });
  fireEvent.change(screen.getByLabelText('权重 1 名称'), { target: { value: 'career' } });
}

describe('NewSessionFlow', () => {
  it('固定 domain=project / risk_budget=low（只读徽标，无可编辑域选择控件）', () => {
    render(<NewSessionFlow onCreated={vi.fn()} />);
    expect(screen.getByText('project')).toBeInTheDocument();
    expect(screen.getByText('low')).toBeInTheDocument();
    // 不存在任何用于选择 domain/risk_budget 的表单控件
    expect(screen.queryByRole('combobox', { name: /domain/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: /risk_budget/i })).not.toBeInTheDocument();
  });

  it('prepare 按钮旁明确标注"不会写入"', () => {
    render(<NewSessionFlow onCreated={vi.fn()} />);
    expect(screen.getByText(/prepare 不会写入/)).toBeInTheDocument();
  });

  it('prepare 成功后弹出 ConfirmDrawer 展示 exact preview；关闭抽屉零 POST（不调用 sessionConfirm）', async () => {
    sessionPrepareMock.mockResolvedValue(PREVIEW);
    render(<NewSessionFlow onCreated={vi.fn()} />);
    fillValidForm();
    fireEvent.click(screen.getByRole('button', { name: /生成 exact preview/ }));

    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    expect(sessionPrepareMock).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole('button', { name: '关闭' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(sessionConfirmMock).not.toHaveBeenCalled();
  });

  it('confirm 成功：非 replay 展示 sequence/event_id/event_checksum 与"已创建"卡片', async () => {
    sessionPrepareMock.mockResolvedValue(PREVIEW);
    sessionConfirmMock.mockResolvedValue(RESULT);
    const onCreated = vi.fn();
    render(<NewSessionFlow onCreated={onCreated} />);
    fillValidForm();
    fireEvent.click(screen.getByRole('button', { name: /生成 exact preview/ }));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /确认写入/ }));
    await waitFor(() => expect(screen.getByText('决策会话已创建并确认')).toBeInTheDocument());
    expect(screen.getByText('1')).toBeInTheDocument();
    expect(sessionConfirmMock).toHaveBeenCalledTimes(1);
    const [previewArg] = sessionConfirmMock.mock.calls[0] as [OrchestrationPreview, string];
    expect(previewArg).toEqual(PREVIEW);

    fireEvent.click(screen.getByRole('button', { name: '进入会话推进视图' }));
    expect(onCreated).toHaveBeenCalledWith(RESULT.session_id);
  });

  it('confirm 命中幂等重放（replayed=true）：显示"已返回原事件，未重复写入"，不显示"已创建"卡片', async () => {
    sessionPrepareMock.mockResolvedValue(PREVIEW);
    sessionConfirmMock.mockResolvedValue({ ...RESULT, replayed: true });
    render(<NewSessionFlow onCreated={vi.fn()} />);
    fillValidForm();
    fireEvent.click(screen.getByRole('button', { name: /生成 exact preview/ }));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /确认写入/ }));

    await waitFor(() => expect(screen.getByText('已返回原事件，未重复写入')).toBeInTheDocument());
    expect(screen.queryByText('决策会话已创建并确认')).not.toBeInTheDocument();
  });

  it('confirm 遇到 stale_expected_sequence：丢弃本地 preview（抽屉关闭），不提供"重试同一 preview"入口', async () => {
    const { OrchestrationError } = await import('../api/orchestration');
    sessionPrepareMock.mockResolvedValue(PREVIEW);
    sessionConfirmMock.mockRejectedValue(
      new OrchestrationError({
        code: 'stale_expected_sequence',
        category: 'stale',
        message: '会话已被推进',
        retryable: true,
        recoveryActions: ['resume_session', 'prepare_fresh_preview'],
      }),
    );
    render(<NewSessionFlow onCreated={vi.fn()} />);
    fillValidForm();
    fireEvent.click(screen.getByRole('button', { name: /生成 exact preview/ }));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /确认写入/ }));

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    // 抽屉必须已关闭：不能继续复用一个可能已过期的 preview
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(sessionConfirmMock).toHaveBeenCalledTimes(1);
  });

  it('confirm 遇到 generation_provider_unavailable 一类 runtime 错误：保留 preview，"重试"复用同一幂等键', async () => {
    const { OrchestrationError } = await import('../api/orchestration');
    sessionPrepareMock.mockResolvedValue(PREVIEW);
    sessionConfirmMock
      .mockRejectedValueOnce(
        new OrchestrationError({
          code: 'confirmation_secret_unavailable',
          category: 'runtime',
          message: '服务端未配置确认密钥',
          retryable: true,
          recoveryActions: ['check_runtime', 'retry_when_ready'],
        }),
      )
      .mockResolvedValueOnce(RESULT);
    render(<NewSessionFlow onCreated={vi.fn()} />);
    fillValidForm();
    fireEvent.click(screen.getByRole('button', { name: /生成 exact preview/ }));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /确认写入/ }));

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
    // 抽屉保留：仍是同一个 preview，允许显式点击"重试"复用同一幂等键
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    const retryButton = screen.getByRole('button', { name: /重试/ });
    fireEvent.click(retryButton);
    await waitFor(() => expect(screen.getByText('决策会话已创建并确认')).toBeInTheDocument());

    expect(sessionConfirmMock).toHaveBeenCalledTimes(2);
    const firstKey = (sessionConfirmMock.mock.calls[0] as [OrchestrationPreview, string])[1];
    const secondKey = (sessionConfirmMock.mock.calls[1] as [OrchestrationPreview, string])[1];
    expect(secondKey).toBe(firstKey);
    // prepare 只调用过一次：重试没有重新走 prepare（同一 preview 复用）
    expect(sessionPrepareMock).toHaveBeenCalledTimes(1);
  });

  it('不存在"一键完成全部阶段"入口：confirm 成功后只提供"进入会话推进视图"，无跳跃到后续 transition 的按钮', async () => {
    sessionPrepareMock.mockResolvedValue(PREVIEW);
    sessionConfirmMock.mockResolvedValue(RESULT);
    render(<NewSessionFlow onCreated={vi.fn()} />);
    fillValidForm();
    fireEvent.click(screen.getByRole('button', { name: /生成 exact preview/ }));
    await waitFor(() => expect(screen.getByRole('dialog')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /确认写入/ }));
    await waitFor(() => expect(screen.getByText('决策会话已创建并确认')).toBeInTheDocument());

    expect(screen.getByText(/前端不提供一键完成入口/)).toBeInTheDocument();
    expect(screen.getAllByRole('button')).toHaveLength(1);
  });
});
