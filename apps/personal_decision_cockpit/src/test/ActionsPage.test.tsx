import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ActionsPage } from '../pages/actions/ActionsPage';
import {
  ACTIONS_RECENT_ENVELOPE,
  ACTIONS_RECENT_ITEM_ERROR_ENVELOPE,
  CALIBRATION_OVERVIEW_ENVELOPE,
} from './mockData';

// 直接 mock hooks（无 MSW）：返回手工构造的 actions_recent.get / calibration_overview.get 信封样例
const actionsState = { envelope: ACTIONS_RECENT_ENVELOPE as unknown };
const calibrationState = { envelope: CALIBRATION_OVERVIEW_ENVELOPE as unknown };
// 游标分页：cursor 非空且设置了 cursorPage 时返回第二页信封（见 39-01 分页测试）
let cursorPage: unknown = null;
vi.mock('../api/hooks', () => ({
  useActionsRecent: (cursor?: string | null) => {
    if (cursor && cursorPage) return { isPending: false, isError: false, data: cursorPage };
    return { isPending: false, isError: false, data: actionsState.envelope };
  },
  useCalibrationOverview: () => ({ isPending: false, isError: false, data: calibrationState.envelope }),
}));

describe('ActionsPage（/actions）', () => {
  it('渲染摘要条与每条推荐的六节点时间线（含 present 状态与等宽校验字段）', () => {
    actionsState.envelope = ACTIONS_RECENT_ENVELOPE;
    calibrationState.envelope = CALIBRATION_OVERVIEW_ENVELOPE;
    render(
      <MemoryRouter>
        <ActionsPage />
      </MemoryRouter>,
    );

    // 摘要条四个计数
    expect(screen.getByText('共 2 条')).toBeInTheDocument();
    expect(screen.getByText('本次展示 2 条')).toBeInTheDocument();
    expect(screen.getByText('已有结果 1 条')).toBeInTheDocument();
    expect(screen.getByText('等待结果 1 条')).toBeInTheDocument();

    // 六节点中文名（两条推荐各一组）
    for (const label of ['建议', '决策', '行动开始', '行动完成', '结果', '效果评估']) {
      expect(screen.getAllByText(label).length).toBeGreaterThanOrEqual(2);
    }

    // present 状态：第一条六节点全达成，第二条 outcome/effectiveness 未达成
    expect(screen.getAllByText('已达成')).toHaveLength(10);
    expect(screen.getAllByText('未达成')).toHaveLength(2);

    // 节点等宽校验字段（event_id 短码 / sequence / checksum 短码）
    const firstCard = screen.getByRole('article', { name: /rec_done_005/ });
    expect(within(firstCard).getAllByText(/^evt_20260601/).length).toBeGreaterThanOrEqual(1);
    expect(within(firstCard).getAllByText('event_id：').length).toBe(6);
    expect(within(firstCard).getAllByText('checksum：').length).toBe(6);

    // 第二条未达成节点字段显"未提供"
    const secondCard = screen.getByRole('article', { name: /rec_outc_004/ });
    expect(within(secondCard).getAllByText('未提供').length).toBeGreaterThanOrEqual(4);
  });

  it('outcome 展开区渲染真实字段 + 固定提示，effectiveness 显著标注非因果', () => {
    actionsState.envelope = ACTIONS_RECENT_ENVELOPE;
    calibrationState.envelope = CALIBRATION_OVERVIEW_ENVELOPE;
    render(
      <MemoryRouter>
        <ActionsPage />
      </MemoryRouter>,
    );

    // spec §7.4 硬性提示（页头 + outcome 展开区各出现）
    expect(screen.getAllByText(/结果记录不自动证明建议导致了结果。/).length).toBeGreaterThanOrEqual(2);

    // outcome 真实字段标签与值
    expect(screen.getByText('实际耗时（分钟）：')).toBeInTheDocument();
    expect(screen.getByText('45')).toBeInTheDocument();
    expect(screen.getByText('满意度：')).toBeInTheDocument();
    expect(screen.getByText('轻微加班')).toBeInTheDocument();

    // causal_claim==false 显著标注"非因果评估"
    expect(screen.getAllByText(/非因果评估/).length).toBeGreaterThanOrEqual(1);

    // "记录结果"入口链到会话流（intent=observe&from=/actions）
    const recordLinks = screen.getAllByRole('link', { name: /记录结果/ });
    expect(recordLinks[0]).toHaveAttribute('href', '/sessions/new?intent=observe&from=/actions');
    // 会话链严格线性说明
    expect(screen.getByText(/不能跳段/)).toBeInTheDocument();
  });

  it('单条 error 只降级该条（其余区域正常）', () => {
    actionsState.envelope = ACTIONS_RECENT_ITEM_ERROR_ENVELOPE;
    calibrationState.envelope = CALIBRATION_OVERVIEW_ENVELOPE;
    render(
      <MemoryRouter>
        <ActionsPage />
      </MemoryRouter>,
    );
    expect(screen.getByText('该条组装失败')).toBeInTheDocument();
    expect(screen.getByText(/recommendation history unavailable/)).toBeInTheDocument();
    // 校准区不受影响
    expect(screen.getByText('校准总览')).toBeInTheDocument();
  });

  it('CalibrationPanel：协议卡 + INCONCLUSIVE 原因与样本不足说明 + 非因果标注', () => {
    actionsState.envelope = ACTIONS_RECENT_ENVELOPE;
    calibrationState.envelope = CALIBRATION_OVERVIEW_ENVELOPE;
    render(
      <MemoryRouter>
        <ActionsPage />
      </MemoryRouter>,
    );
    const panel = screen.getByRole('region', { name: '校准总览' });
    expect(within(panel).getByText('cal_weekly_hours_v1')).toBeInTheDocument();
    expect(within(panel).getByText('concluded')).toBeInTheDocument();
    expect(within(panel).getByText('样本不足或协议偏离：该协议结论不可用（INCONCLUSIVE），不能作为建议有效性的依据。')).toBeInTheDocument();
    expect(within(panel).getByText('sample_below_minimum')).toBeInTheDocument();
    expect(within(panel).getAllByText(/非因果评估/).length).toBeGreaterThanOrEqual(2);
    expect(within(panel).getByText('单用户观察性数据，不能作因果解释。')).toBeInTheDocument();
  });
});

// --- 39-01 稳定游标分页：newest-first + "加载更早记录" 累积 + 返回最新 ----------

describe('ActionsPage 游标分页（39-01）', () => {
  it('next_cursor 存在时显示"加载更早记录";点击后累积更早条目并隐藏按钮', async () => {
    actionsState.envelope = {
      ...ACTIONS_RECENT_ENVELOPE,
      data: { ...ACTIONS_RECENT_ENVELOPE.data, next_cursor: 'CUR2' },
    } as unknown;
    calibrationState.envelope = CALIBRATION_OVERVIEW_ENVELOPE;
    const page2Item = JSON.parse(JSON.stringify(ACTIONS_RECENT_ENVELOPE.data.items[0]));
    page2Item.recommendation_id = 'rec_older_099';
    cursorPage = {
      ...ACTIONS_RECENT_ENVELOPE,
      data: {
        ...ACTIONS_RECENT_ENVELOPE.data,
        items: [page2Item],
        next_cursor: null,
        total_available: 3,
        shown: 1,
        with_outcome: 0,
        awaiting_outcome: 1,
      },
    } as unknown;

    render(
      <MemoryRouter>
        <ActionsPage />
      </MemoryRouter>,
    );

    // 初始只渲染第一页两条（newest-first 窗口）
    expect(screen.getByRole('article', { name: /rec_done_005/ })).toBeInTheDocument();
    expect(screen.getByRole('article', { name: /rec_outc_004/ })).toBeInTheDocument();
    const loadBtn = screen.getByRole('button', { name: /加载更早记录/ });
    expect(loadBtn).toBeInTheDocument();

    fireEvent.click(loadBtn);
    await waitFor(() => {
      expect(screen.getByRole('article', { name: /rec_older_099/ })).toBeInTheDocument();
    });
    // 累积三页条目，计数随之增长
    expect(screen.getByText('本次展示 3 条')).toBeInTheDocument();
    expect(screen.getByText('共 3 条')).toBeInTheDocument();
    // 第二页无 next_cursor → "加载更早记录" 按钮消失
    expect(screen.queryByRole('button', { name: /加载更早记录/ })).not.toBeInTheDocument();
    // 分页视图徽标出现（后端 limitations 反馈"当前为分页视图"）
    expect(screen.getByText('分页视图（更早记录）')).toBeInTheDocument();
  });
});
