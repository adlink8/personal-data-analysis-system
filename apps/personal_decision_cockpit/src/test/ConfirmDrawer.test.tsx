import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { ConfirmDrawer } from '../components/decision/ConfirmDrawer';
import type { OrchestrationPreview } from '../api/orchestration';

/**
 * 确认抽屉测试（spec §7.3 八要素 / §17.1 Exact Preview）：
 * 展示 preview_checksum 与 idempotency_key、确认按钮具体文案、"不会执行的动作"固定提示。
 */

const PREVIEW: OrchestrationPreview = {
  session_id: 'ors_20260719_test_session_0001',
  operation: 'decide',
  actor_identity_hash: 'a'.repeat(64),
  expected_sequence: 3,
  payload: { input: { case_id: 'case_x', decision: 'accept' }, binding_hash: 'b'.repeat(64) },
  issued_at: '2026-07-19T08:00:00Z',
  preview_checksum: 'abcd1234'.repeat(8),
};

function renderDrawer(overrides: Partial<Parameters<typeof ConfirmDrawer>[0]> = {}) {
  const props = {
    open: true,
    title: '记录决策',
    preview: PREVIEW,
    eventDescription: '写入 decide 事件：决策确认写入 Pilot 权威案例（sequence 4）。',
    confirmLabel: '确认写入"接受方案"',
    idempotencyKey: 'ui-decide-11111111-2222-4333-8444-555555555555',
    onConfirm: vi.fn(),
    onClose: vi.fn(),
    ...overrides,
  };
  render(<ConfirmDrawer {...props} />);
  return props;
}

describe('ConfirmDrawer', () => {
  it('展示 preview_checksum、idempotency_key 与具体确认文案', () => {
    renderDrawer();

    // 操作名称
    expect(screen.getByRole('dialog', { name: '确认写入：记录决策' })).toBeInTheDocument();
    // 确认按钮文案具体（禁止"继续/确定"）
    expect(screen.getByRole('button', { name: '确认写入"接受方案"' })).toBeInTheDocument();
    // preview_checksum（短码展示，完整值在 title）
    expect(screen.getByText('preview_checksum')).toBeInTheDocument();
    expect(screen.getByText(`${'abcd1234'.repeat(3)}…`)).toBeInTheDocument();
    // idempotency_key 全文展示 + 重试同键说明
    expect(screen.getByText('ui-decide-11111111-2222-4333-8444-555555555555')).toBeInTheDocument();
    expect(screen.getByText(/网络重试使用同一键/)).toBeInTheDocument();
  });

  it('包含"不会执行的动作"固定提示', () => {
    renderDrawer();
    expect(screen.getByText('不会执行的动作')).toBeInTheDocument();
    expect(screen.getByText('不会自动执行任何外部动作')).toBeInTheDocument();
    expect(screen.getByText('不会 promote 任何建议或知识单元')).toBeInTheDocument();
    expect(screen.getByText('不会修改任何 SSOT（知识库 / 个人状态 / 外部快照）')).toBeInTheDocument();
  });

  it('exact preview 默认折叠，点击展开 JSON 只读视图', () => {
    renderDrawer();
    expect(screen.queryByText(/"decide"/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /exact preview/ }));
    expect(screen.getByText(/"operation": "decide"/)).toBeInTheDocument();
  });

  it('busy=true 时 Esc、背景遮罩与关闭按钮均不触发 onClose（与底部"取消"按钮 disabled 一致）', () => {
    const onClose = vi.fn();
    renderDrawer({ busy: true, onClose });

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '关闭确认抽屉' }));
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '关闭' }));
    expect(onClose).not.toHaveBeenCalled();

    // 确认按钮同样禁用，防止 busy 期间重复提交
    expect(screen.getByRole('button', { name: /正在写入/ })).toBeDisabled();
  });

  it('Esc 不会冒泡到外层对话框（嵌套模态场景，如"新建决策会话"）：只关闭当前抽屉', () => {
    const outerListener = vi.fn();
    // 模拟外层对话框（NewSessionDialog）自己的 window 级 bubble-phase Escape 监听
    window.addEventListener('keydown', outerListener);
    try {
      const onClose = vi.fn();
      renderDrawer({ onClose });
      fireEvent.keyDown(window, { key: 'Escape' });
      expect(onClose).toHaveBeenCalledTimes(1);
      expect(outerListener).not.toHaveBeenCalled();
    } finally {
      window.removeEventListener('keydown', outerListener);
    }
  });

  it('busy=false 时 Esc/背景/关闭按钮均可正常触发 onClose，且不调用 onConfirm（取消零副作用）', () => {
    const onClose = vi.fn();
    const onConfirm = vi.fn();
    renderDrawer({ onClose, onConfirm });

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('open=false 不渲染；确认按钮触发 onConfirm', () => {
    const { rerender } = render(
      <ConfirmDrawer
        open={false}
        title="记录决策"
        preview={PREVIEW}
        eventDescription="x"
        confirmLabel='确认写入"接受方案"'
        idempotencyKey="k"
        onConfirm={() => {}}
        onClose={() => {}}
      />,
    );
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    rerender(
      <ConfirmDrawer
        open
        title="记录决策"
        preview={PREVIEW}
        eventDescription="x"
        confirmLabel='确认写入"接受方案"'
        idempotencyKey="k"
        onConfirm={() => {}}
        onClose={() => {}}
      />,
    );
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});
