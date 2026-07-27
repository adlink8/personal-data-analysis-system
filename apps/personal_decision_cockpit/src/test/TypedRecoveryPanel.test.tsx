import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { TypedRecoveryPanel, type RecoveryError } from '../components/feedback/TypedRecoveryPanel';

/**
 * 分类恢复面板测试（spec §8 / §12，Phase 38-03 负向验收矩阵）：
 * - 重试 CTA fail-closed：仅 runtime 类（recovery_actions 含 retry_when_ready）渲染"重试"；
 *   stale/confirmation/sequence/conflict/integrity/risk/unknown_outcome/actor mismatch
 *   即便调用方误传 onRetry 也不渲染重试按钮（T-38-09 自动重试防线）。
 * - replayed 显示 Replay 态"已返回原事件，未重复写入"（T-38-11 重放误解防线）。
 * - 错误视图不泄露 confirmation/HMAC/secret/payload（T-38-10：输入类型即不含这些字段，
 *   本测试断言渲染输出只包含脱敏 code/category/message/recovery_actions）。
 */

function makeError(overrides: Partial<RecoveryError> & Pick<RecoveryError, 'code' | 'category'>): RecoveryError {
  return {
    message: 'test message',
    retryable: false,
    recoveryActions: [],
    ...overrides,
  };
}

describe('TypedRecoveryPanel', () => {
  it('runtime 类（retry_when_ready）：显示"重试"按钮并触发 onRetry', () => {
    const onRetry = vi.fn();
    render(
      <TypedRecoveryPanel
        error={makeError({
          code: 'generation_provider_unavailable',
          category: 'runtime',
          message: 'A required local runtime component is unavailable.',
          retryable: true,
          recoveryActions: ['check_runtime', 'retry_when_ready'],
        })}
        operationLabel="生成分析"
        onRetry={onRetry}
      />,
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('可重试')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /重试/ }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('stale：服务端 retryable=true 也不渲染重试 CTA，只给 resume/重新 preview 路径', () => {
    const onRetry = vi.fn();
    render(
      <TypedRecoveryPanel
        error={makeError({
          code: 'stale_expected_sequence',
          category: 'stale',
          message: 'The request is stale; inspect current state before preparing a new preview.',
          retryable: true,
          recoveryActions: ['resume_session', 'prepare_fresh_preview'],
        })}
        operationLabel="记录决策"
        onRetry={onRetry}
        onResume={vi.fn()}
      />,
    );
    // fail-closed：即便传了 onRetry 也不渲染重试按钮
    expect(screen.queryByRole('button', { name: /重试/ })).not.toBeInTheDocument();
    expect(screen.getByText('不可自动重试')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /恢复会话状态/ })).toBeInTheDocument();
    expect(screen.getByText(/恢复会话，核对当前 state 与 sequence/)).toBeInTheDocument();
  });

  it.each([
    ['confirmation_expired', 'confirmation', ['resume_session', 'prepare_fresh_preview', 'confirm_again'], true],
    ['illegal_transition', 'sequence', ['resume_session', 'prepare_fresh_preview'], true],
    ['idempotency_conflict', 'conflict', ['resume_session', 'use_original_idempotency_key', 'manual_review'], false],
    ['event_chain_checksum_drift', 'integrity', ['inspect_authority', 'manual_review'], false],
    ['high_risk_or_external_action_forbidden', 'risk', ['reduce_scope', 'manual_review'], false],
  ] as const)('%s（%s）：无论 retryable 如何，不渲染重试 CTA', (code, category, actions, retryable) => {
    render(
      <TypedRecoveryPanel
        error={makeError({ code, category, retryable, recoveryActions: [...actions] })}
        onRetry={vi.fn()}
      />,
    );
    expect(screen.queryByRole('button', { name: /重试/ })).not.toBeInTheDocument();
    expect(screen.getByText('不可自动重试')).toBeInTheDocument();
    // 每类都有稳定的类别级说明（categorySpecificNote 兜底，不空白）
    expect(screen.getByText(code)).toBeInTheDocument();
  });

  it('provider_outcome_unknown：无重试 CTA，只允许 resume/检查预留/人工复核', () => {
    render(
      <TypedRecoveryPanel
        error={makeError({
          code: 'provider_outcome_unknown',
          category: 'unknown_outcome',
          message: 'Provider outcome is unknown; automatic retry is unsafe.',
          retryable: false,
          recoveryActions: ['resume_session', 'inspect_provider_reservation', 'manual_review'],
        })}
        onRetry={vi.fn()}
        onResume={vi.fn()}
      />,
    );
    expect(screen.queryByRole('button', { name: /重试/ })).not.toBeInTheDocument();
    expect(screen.getByText(/自动重试不安全/)).toBeInTheDocument();
    expect(screen.getAllByText(/检查 provider 预留的执行结果/).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: /恢复会话状态/ })).toBeInTheDocument();
  });

  it('actor_identity_mismatch：即便服务端归入 runtime 并带 retry_when_ready 也不渲染重试', () => {
    render(
      <TypedRecoveryPanel
        error={makeError({
          code: 'actor_identity_mismatch',
          category: 'runtime',
          retryable: true,
          recoveryActions: ['check_runtime', 'retry_when_ready'],
        })}
        onRetry={vi.fn()}
      />,
    );
    expect(screen.queryByRole('button', { name: /重试/ })).not.toBeInTheDocument();
    expect(screen.getByText(/只能只读查看/)).toBeInTheDocument();
  });

  it('replayed=true 显示 Replay 态"已返回原事件，未重复写入"', () => {
    render(<TypedRecoveryPanel replayed />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText('已返回原事件，未重复写入')).toBeInTheDocument();
    expect(screen.getByText(/exact replay/)).toBeInTheDocument();
  });

  it('idempotency_conflict：不可重试警示与"不要换幂等键"恢复路径', () => {
    render(
      <TypedRecoveryPanel
        error={makeError({
          code: 'idempotency_conflict',
          category: 'conflict',
          message: 'The request conflicts with an existing immutable record.',
          recoveryActions: ['resume_session', 'use_original_idempotency_key', 'manual_review'],
        })}
      />,
    );
    expect(screen.getByText('不可自动重试')).toBeInTheDocument();
    expect(screen.getByText(/不可重试：同一幂等键对应了不同的请求内容/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /重试/ })).not.toBeInTheDocument();
  });

  it('confirmation_secret_unavailable：给出 PERSONAL_DATA_ORCHESTRATION_SECRET 恢复说明', () => {
    render(
      <TypedRecoveryPanel
        error={makeError({
          code: 'confirmation_secret_unavailable',
          category: 'runtime',
          retryable: true,
          recoveryActions: ['check_runtime', 'retry_when_ready'],
        })}
      />,
    );
    expect(screen.getByText(/PERSONAL_DATA_ORCHESTRATION_SECRET/)).toBeInTheDocument();
  });

  it('generation_provider_unavailable：说明 generation runner 恢复路径', () => {
    render(
      <TypedRecoveryPanel
        error={makeError({
          code: 'generation_provider_unavailable',
          category: 'runtime',
          retryable: true,
          recoveryActions: ['check_runtime', 'retry_when_ready'],
        })}
      />,
    );
    expect(screen.getByText(/generation runner/)).toBeInTheDocument();
    expect(screen.getByText(/不会中断/)).toBeInTheDocument();
  });

  it('错误视图不泄露敏感材料：渲染输出不含 token/HMAC/secret/payload 字样的原始值', () => {
    const { container } = render(
      <TypedRecoveryPanel
        error={makeError({
          code: 'confirmation_checksum_mismatch',
          category: 'confirmation',
          message: 'The explicit confirmation is missing, expired, consumed, or does not match this preview.',
          retryable: true,
          recoveryActions: ['resume_session', 'prepare_fresh_preview', 'confirm_again'],
        })}
      />,
    );
    const text = container.textContent ?? '';
    // 输入类型上就不存在这些字段；这里回归断言渲染输出不会出现敏感材料痕迹
    expect(text).not.toMatch(/hmac|Bearer |eyJ[A-Za-z0-9]/i);
    expect(screen.queryByRole('button', { name: /重试/ })).not.toBeInTheDocument();
  });
});
