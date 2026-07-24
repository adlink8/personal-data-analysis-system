import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { TypedRecoveryPanel } from '../components/feedback/TypedRecoveryPanel';

/**
 * 分类恢复面板测试（spec §8 / §12）：
 * retryable 显示"重试"；replayed 显示 Replay 态"已返回原事件，未重复写入"；
 * 已知服务端限制给出明确恢复说明；idempotency_conflict 不可重试警示。
 */

describe('TypedRecoveryPanel', () => {
  it('retryable 错误显示"重试"按钮并触发 onRetry', () => {
    const onRetry = vi.fn();
    render(
      <TypedRecoveryPanel
        error={{
          code: 'stale_expected_sequence',
          category: 'stale',
          message: 'The request is stale; inspect current state before preparing a new preview.',
          retryable: true,
          recoveryActions: ['resume_session', 'prepare_fresh_preview'],
        }}
        operationLabel="记录决策"
        onRetry={onRetry}
      />,
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('stale_expected_sequence')).toBeInTheDocument();
    expect(screen.getByText('可重试')).toBeInTheDocument();
    // recovery_actions 中文说明 + 原始代码
    expect(screen.getByText(/恢复会话，核对当前 state 与 sequence/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /重试/ }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('replayed=true 显示 Replay 态"已返回原事件，未重复写入"', () => {
    render(<TypedRecoveryPanel replayed />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText('已返回原事件，未重复写入')).toBeInTheDocument();
    expect(screen.getByText(/exact replay/)).toBeInTheDocument();
  });

  it('idempotency_conflict：不可重试警示与恢复路径', () => {
    render(
      <TypedRecoveryPanel
        error={{
          code: 'idempotency_conflict',
          category: 'conflict',
          message: 'The request conflicts with an existing immutable record.',
          retryable: false,
          recoveryActions: ['resume_session', 'use_original_idempotency_key', 'manual_review'],
        }}
      />,
    );
    expect(screen.getByText('不可自动重试')).toBeInTheDocument();
    expect(screen.getByText(/不可重试：同一幂等键对应了不同的请求内容/)).toBeInTheDocument();
    // 不可重试时不渲染重试按钮
    expect(screen.queryByRole('button', { name: /重试/ })).not.toBeInTheDocument();
  });

  it('confirmation_secret_unavailable：给出 PERSONAL_DATA_ORCHESTRATION_SECRET 恢复说明', () => {
    render(
      <TypedRecoveryPanel
        error={{
          code: 'confirmation_secret_unavailable',
          category: 'runtime',
          message: 'A required local runtime component is unavailable.',
          retryable: true,
          recoveryActions: ['check_runtime', 'retry_when_ready'],
        }}
      />,
    );
    expect(screen.getByText(/PERSONAL_DATA_ORCHESTRATION_SECRET/)).toBeInTheDocument();
  });

  it('generation_provider_unavailable：说明 generation runner 恢复路径', () => {
    render(
      <TypedRecoveryPanel
        error={{
          code: 'generation_provider_unavailable',
          category: 'runtime',
          message: 'A required local runtime component is unavailable.',
          retryable: true,
          recoveryActions: ['check_runtime', 'retry_when_ready'],
        }}
      />,
    );
    expect(screen.getByText(/generation runner/)).toBeInTheDocument();
    expect(screen.getByText(/不会中断/)).toBeInTheDocument();
  });
});
