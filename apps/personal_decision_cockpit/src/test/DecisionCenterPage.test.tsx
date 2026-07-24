import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { DecisionCenterPage } from '../pages/decisions/DecisionCenterPage';
import { DECISION_QUEUE_EMPTY_ENVELOPE, DECISION_QUEUE_ENVELOPE } from './mockData';

// 直接 mock hooks（无 MSW）：返回手工构造的 decision_queue.get 信封样例
const queueState = { envelope: DECISION_QUEUE_ENVELOPE as unknown };
vi.mock('../api/hooks', () => ({
  useDecisionQueue: () => ({ isPending: false, isError: false, data: queueState.envelope }),
}));

/** 徽标内含 SVG 图标，文字被拆成多个节点，用 textContent 匹配 */
const badgeWithText = (text: string) => (_: string, el: Element | null) =>
  el?.tagName === 'SPAN' && el.textContent === text;

describe('DecisionCenterPage（/decisions）', () => {
  it('渲染六组看板（含计数）与卡片双状态徽标、到期强调', () => {
    queueState.envelope = DECISION_QUEUE_ENVELOPE;
    render(
      <MemoryRouter>
        <DecisionCenterPage />
      </MemoryRouter>,
    );

    // 六组标题与计数
    for (const label of ['需要关注', '等待确认', '执行中', '等待结果', '已完成', '已关闭']) {
      const region = screen.getByRole('region', { name: label });
      expect(within(region).getByText(badgeWithText('1 条'))).toBeInTheDocument();
    }

    // 卡片：短 ID + domain + kind
    const attention = within(screen.getByRole('region', { name: '需要关注' }));
    expect(attention.getByText('rec_attn_001')).toBeInTheDocument();
    expect(attention.getByText('career')).toBeInTheDocument();
    expect(attention.getByText('time_allocation')).toBeInTheDocument();

    // 双状态徽标（文字 + 图标，非纯色）
    expect(attention.getByText(badgeWithText('待确认'))).toBeInTheDocument();
    expect(attention.getByText(badgeWithText('未开始行动'))).toBeInTheDocument();
    const progress = within(screen.getByRole('region', { name: '执行中' }));
    expect(progress.getByText(badgeWithText('已接受'))).toBeInTheDocument();
    expect(progress.getByText(badgeWithText('执行中'))).toBeInTheDocument();

    // expires_at 已过 → amber 强调"已过期"
    expect(attention.getByText('已过期')).toBeInTheDocument();

    // 卡片链接指向工作区
    expect(screen.getByRole('link', { name: /rec_attn_001/ })).toHaveAttribute(
      'href',
      '/decisions/rec_attn_001',
    );
  });

  it('空队列显示"当前没有待决策事项"与下一步引导', () => {
    queueState.envelope = DECISION_QUEUE_EMPTY_ENVELOPE;
    render(
      <MemoryRouter>
        <DecisionCenterPage />
      </MemoryRouter>,
    );
    expect(screen.getByText('当前没有待决策事项')).toBeInTheDocument();
    expect(screen.getByText(/新建决策/)).toBeInTheDocument();
  });
});
