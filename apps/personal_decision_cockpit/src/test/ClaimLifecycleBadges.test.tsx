import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import {
  CLOSED_CONFIRMATION_STATES,
  ClaimKindBadge,
  ConfirmationStateBadge,
  HISTORICAL_LIFECYCLE_STATUSES,
  LifecycleBadge,
  isHistoricalLifecycle,
} from '../components/authority/ClaimLifecycleBadges';

/**
 * 共享 claim/lifecycle/confirmation 语义组件测试（Phase 37 Plan 02 Task 1）：
 * claim、lifecycle 两轴各自独立可识别；未知值不静默丢弃；Historical 只是展示分组。
 */

describe('ClaimKindBadge：claim / object kind 轴', () => {
  it.each([
    ['fact', '事实'],
    ['observation', '观察'],
    ['inference', '推断'],
    ['recommendation', '建议候选'],
    ['confirmation', '用户确认'],
  ])('%s 渲染为「%s」，且带有非纯色的图标', (kind, label) => {
    const { container } = render(<ClaimKindBadge kind={kind} />);
    expect(screen.getByText(label)).toBeInTheDocument();
    expect(container.querySelector('svg')).toBeInTheDocument();
  });

  it('未知 kind 原样展示而非丢弃', () => {
    render(<ClaimKindBadge kind="forecast" />);
    expect(screen.getByText('forecast')).toBeInTheDocument();
  });
});

describe('LifecycleBadge：record lifecycle 轴（Personal + External 并集）', () => {
  it.each([
    ['current', '当前'],
    ['stale', '偏旧'],
    ['conflict', '冲突'],
    ['resolved', '已解决'],
    ['expired', '已过期'],
    ['superseded', '已被替代'],
    ['invalid', '已失效'],
  ])('%s 渲染为「%s」', (status, label) => {
    render(<LifecycleBadge status={status} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it('hideCurrent=true 时 current 不渲染任何内容（避免默认态噪音）', () => {
    const { container } = render(<LifecycleBadge status="current" hideCurrent />);
    expect(container).toBeEmptyDOMElement();
  });

  it('state_projection 偶发的 unknown/uncertain/future 状态显式呈现，不静默丢弃', () => {
    render(<LifecycleBadge status="unknown" />);
    expect(screen.getByText('未知')).toBeInTheDocument();
    render(<LifecycleBadge status="uncertain" />);
    expect(screen.getByText('不确定')).toBeInTheDocument();
    render(<LifecycleBadge status="future" />);
    expect(screen.getByText('未来生效')).toBeInTheDocument();
  });

  it('完全未在闭集中的字符串原样展示，而不是返回 null', () => {
    render(<LifecycleBadge status="totally_new_status" />);
    expect(screen.getByText('totally_new_status')).toBeInTheDocument();
  });

  it('null/undefined 状态不渲染（无记录状态可展示）', () => {
    const { container } = render(<LifecycleBadge status={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('Historical 是展示分组，不是伪造的 lifecycle 值（D-37-01）', () => {
  it('stale/resolved/expired/superseded 属于 Historical 分组', () => {
    for (const status of ['stale', 'resolved', 'expired', 'superseded']) {
      expect(HISTORICAL_LIFECYCLE_STATUSES.has(status)).toBe(true);
      expect(isHistoricalLifecycle(status)).toBe(true);
    }
  });

  it('current/conflict 不属于 Historical 分组', () => {
    expect(isHistoricalLifecycle('current')).toBe(false);
    expect(isHistoricalLifecycle('conflict')).toBe(false);
    expect(isHistoricalLifecycle(null)).toBe(false);
  });
});

describe('ConfirmationStateBadge：_KNOWN_CONFIRMATION_STATES 闭集', () => {
  it.each([
    ['proposed', '待确认'],
    ['accepted', '已接受'],
    ['rejected', '已拒绝'],
    ['deferred', '已推迟'],
    ['revoked', '已撤回'],
  ])('%s 渲染为「%s」', (state, label) => {
    render(<ConfirmationStateBadge state={state} />);
    expect(screen.getByText(label)).toBeInTheDocument();
  });

  it('缺失 state 显式标注"未提供"，而非空白', () => {
    render(<ConfirmationStateBadge state={null} />);
    expect(screen.getByText('未提供')).toBeInTheDocument();
  });

  it('闭集之外的未知值原样展示', () => {
    render(<ConfirmationStateBadge state="mystery_state" />);
    expect(screen.getByText('mystery_state')).toBeInTheDocument();
  });

  it('CLOSED_CONFIRMATION_STATES 与 ui_projection.py `_classify_stage` 规则 1 一致', () => {
    expect(CLOSED_CONFIRMATION_STATES.has('rejected')).toBe(true);
    expect(CLOSED_CONFIRMATION_STATES.has('deferred')).toBe(true);
    expect(CLOSED_CONFIRMATION_STATES.has('revoked')).toBe(true);
    expect(CLOSED_CONFIRMATION_STATES.has('proposed')).toBe(false);
    expect(CLOSED_CONFIRMATION_STATES.has('accepted')).toBe(false);
  });
});
