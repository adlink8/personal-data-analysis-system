import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProactivePage } from '../pages/proactive/ProactivePage';
import { PROACTIVE_SUMMARY_ENVELOPE } from './mockData';

// 直接 mock hooks（无 MSW）：返回手工构造的 proactive_summary.get 信封样例；
// explain/controls 两个按需查询默认不触发，给空态返回。
const summaryState = { envelope: PROACTIVE_SUMMARY_ENVELOPE as unknown };
vi.mock('../api/hooks', () => ({
  useProactiveSummary: () => ({ isPending: false, isError: false, data: summaryState.envelope }),
  useProactiveCandidateExplain: () => ({ isPending: false, isError: false, data: undefined }),
  useProactiveControlStatus: () => ({ isPending: false, isError: false, data: undefined }),
}));

describe('ProactivePage（/proactive）', () => {
  it('渲染需要现在处理 / 可延后分组与 ProactiveCard 关键字段', () => {
    summaryState.envelope = PROACTIVE_SUMMARY_ENVELOPE;
    render(
      <MemoryRouter>
        <ProactivePage />
      </MemoryRouter>,
    );

    const nowRegion = screen.getByRole('region', { name: '需要现在处理' });
    expect(within(nowRegion).getByText('1 条')).toBeInTheDocument();
    // candidate_id 短码（前 20 字符 + …）
    expect(within(nowRegion).getByText(/cand_20260719_now000/)).toBeInTheDocument();
    // 领域 chips 与 class/kind
    expect(within(nowRegion).getByText('career')).toBeInTheDocument();
    expect(within(nowRegion).getByText('learning')).toBeInTheDocument();
    expect(within(nowRegion).getByText('opportunity')).toBeInTheDocument();
    expect(within(nowRegion).getByText('card')).toBeInTheDocument();
    // importance 尽力解析：level（score）
    expect(within(nowRegion).getByText(/high（0\.83）/)).toBeInTheDocument();
    // 触发依据
    expect(within(nowRegion).getByText('deadline_approaching')).toBeInTheDocument();
    // 控制状态
    expect(within(nowRegion).getByText('可控制')).toBeInTheDocument();

    const deferrableRegion = screen.getByRole('region', { name: '可延后' });
    expect(within(deferrableRegion).getByText(/cand_20260718_def000/)).toBeInTheDocument();
    expect(within(deferrableRegion).getByText('当前不可控制')).toBeInTheDocument();
    expect(within(deferrableRegion).getByText('snoozed_recently')).toBeInTheDocument();
  });

  it('已抑制与冷却中 / 历史为诚实空态，并提供 candidate_id 控制状态查询入口', () => {
    summaryState.envelope = PROACTIVE_SUMMARY_ENVELOPE;
    render(
      <MemoryRouter>
        <ProactivePage />
      </MemoryRouter>,
    );
    expect(screen.getByText(/该状态不列入 eligible inbox/)).toBeInTheDocument();
    expect(screen.getByRole('textbox', { name: 'candidate_id' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /查询控制状态/ })).toBeInTheDocument();
    expect(screen.getByText(/本投影仅面向当前 eligible 候选，不提供历史视图/)).toBeInTheDocument();
  });

  it('写按钮一律 disabled 且有 REST 未暴露说明，不做假按钮', () => {
    summaryState.envelope = PROACTIVE_SUMMARY_ENVELOPE;
    render(
      <MemoryRouter>
        <ProactivePage />
      </MemoryRouter>,
    );
    // 两张卡各一组四个写按钮
    for (const label of ['Snooze', 'Suppress', '限定 Scope', 'Restore']) {
      const buttons = screen.getAllByRole('button', { name: label });
      expect(buttons).toHaveLength(2);
      for (const button of buttons) {
        expect(button).toBeDisabled();
        expect(button).toHaveAttribute('title', '该写入由 MCP 工具或 pk CLI 提供，REST 未暴露');
      }
    }
    // 可见说明文案（非静默不可点）
    expect(screen.getAllByText(/该写入由 MCP 工具或 pk CLI 提供，REST 未暴露/).length).toBeGreaterThanOrEqual(2);
    // 查看证据可点；创建 Decision Case 链到会话流
    expect(screen.getAllByRole('button', { name: '查看证据' })[0]).toBeEnabled();
    expect(screen.getAllByRole('link', { name: /创建 Decision Case/ })[0]).toHaveAttribute('href', '/sessions/new');
  });

  it('metrics 键值区与 notes 说明条渲染', () => {
    summaryState.envelope = PROACTIVE_SUMMARY_ENVELOPE;
    render(
      <MemoryRouter>
        <ProactivePage />
      </MemoryRouter>,
    );
    const metricsRegion = screen.getByRole('region', { name: '指标' });
    expect(within(metricsRegion).getByText('noise_budget_remaining：')).toBeInTheDocument();
    expect(within(metricsRegion).getByText('3')).toBeInTheDocument();
    expect(within(metricsRegion).getByText('candidates_suppressed：')).toBeInTheDocument();
    expect(screen.getByText(/仅展示当前 eligible 候选；已抑制与冷却中的候选不列入本页。/)).toBeInTheDocument();
  });
});
