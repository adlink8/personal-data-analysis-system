import type { Mock } from 'vitest';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { PersonalStatePage } from '../pages/state/PersonalStatePage';
import { useEvidenceResolve } from '../api/hooks';

// 直接 mock hooks（无 MSW）：返回手工构造的 personal_state.get 信封样例；
// useEvidenceResolve 是 Phase 37 Plan 03 新增的"查看证据"入口所依赖的唯一数据 hook，
// 默认返回 pending 态（本文件只验证入口能否正确打开抽屉并携带稳定引用，
// 抽屉自身的六态渲染已由 EvidenceDrawer.test.tsx 覆盖，此处不重复）。
vi.mock('../api/hooks', async () => {
  const { PERSONAL_STATE_ENVELOPE } = await import('./mockData');
  return {
    usePersonalState: () => ({ isPending: false, isError: false, data: PERSONAL_STATE_ENVELOPE }),
    useEvidenceResolve: vi.fn(() => ({ isPending: true, isError: false, data: undefined, refetch: vi.fn() })),
  };
});

const mockedUseEvidenceResolve = useEvidenceResolve as unknown as Mock;

/** 徽标内含 SVG 图标，文字被拆成多个节点，用 textContent 匹配 */
const badgeWithText = (text: string) => (_: string, el: Element | null) =>
  el?.tagName === 'SPAN' && el.textContent === text;

describe('PersonalStatePage（/state）', () => {
  it('渲染八领域网格，含冲突标记与高风险域提示', () => {
    render(
      <MemoryRouter>
        <PersonalStatePage />
      </MemoryRouter>,
    );

    const grid = within(screen.getByRole('region', { name: '八领域状态' }));
    for (const label of ['学习', '职业', '项目', '健康', '财务', '关系', '时间', '精力']) {
      expect(grid.getByText(label)).toBeInTheDocument();
    }

    // 职业领域 conflicts=2 → 红色"冲突 2"标记（图标 + 文字，非纯色）
    expect(grid.getByText(badgeWithText('冲突 2'))).toBeInTheDocument();

    // 健康/财务/关系为高风险域（spec §13.3）：域级风险提示小字
    const hints = grid.getAllByText(
      (_, el) => el?.tagName === 'P' && el.textContent === '高风险领域：任何行动需显式确认',
    );
    expect(hints).toHaveLength(3);

    // 生命周期摘要条（current/stale/conflict/resolved/expired）
    const strip = screen.getByLabelText('生命周期分布');
    for (const label of ['当前', '偏旧', '冲突', '已解决', '已过期']) {
      expect(within(strip).getByText((_, el) => el?.tagName === 'LI' && (el.textContent ?? '').startsWith(label))).toBeInTheDocument();
    }

    // 近期变化时间线
    expect(screen.getByRole('region', { name: '近期变化' })).toBeInTheDocument();
    expect(screen.getByText('supersede')).toBeInTheDocument();
  });

  it('/state/:domain 详情按 claim 类型分组，并注明隐私封存', () => {
    render(
      <MemoryRouter initialEntries={['/state/career']}>
        <Routes>
          <Route path="/state/:domain" element={<PersonalStatePage />} />
        </Routes>
      </MemoryRouter>,
    );

    // 值只有 checksum：页面注明"内容经隐私封存，仅展示元数据"
    expect(
      screen.getByText(
        (_, el) => el?.tagName === 'P' && el.textContent === '断言值仅保留 checksum：内容经隐私封存，仅展示元数据。',
      ),
    ).toBeInTheDocument();

    // claim 分组徽标：事实 / 观察 / 推断
    expect(screen.getAllByText(badgeWithText('事实')).length).toBeGreaterThan(0);
    expect(screen.getAllByText(badgeWithText('观察')).length).toBeGreaterThan(0);
    expect(screen.getAllByText(badgeWithText('推断')).length).toBeGreaterThan(0);

    // 断言元数据：predicate、置信度、证据数；stale 状态有文字标注
    expect(screen.getByText('target_role')).toBeInTheDocument();
    expect(screen.getByText('job_search_window')).toBeInTheDocument();
    expect(screen.getByText(/证据 5 条/)).toBeInTheDocument();
    expect(screen.getAllByText(badgeWithText('偏旧')).length).toBeGreaterThan(0);
    expect(screen.getAllByText(badgeWithText('冲突')).length).toBeGreaterThan(0);

    // 领域级冲突标记（career conflicts=2）
    expect(screen.getAllByText(badgeWithText('冲突 2')).length).toBeGreaterThan(0);
  });

  it('断言卡"查看证据"入口只在具备完整稳定引用三元组时出现（Phase 37 Plan 03，EVID-01）', () => {
    render(
      <MemoryRouter initialEntries={['/state/career']}>
        <Routes>
          <Route path="/state/:domain" element={<PersonalStatePage />} />
        </Routes>
      </MemoryRouter>,
    );

    // target_role（有 current_value_checksum）与 job_search_window（有 checksum）均有入口；
    // weekly_hours 的 mock 数据故意省略 checksum → 不构造伪 evidence，不渲染入口
    const evidenceButtons = screen.getAllByRole('button', { name: '查看证据' });
    expect(evidenceButtons).toHaveLength(2);
  });

  it('点击"查看证据"打开 Evidence Drawer 并携带该断言的稳定引用三元组，不重建或替换为其它记录', () => {
    render(
      <MemoryRouter initialEntries={['/state/career']}>
        <Routes>
          <Route path="/state/:domain" element={<PersonalStatePage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByRole('button', { name: '查看证据' })[0]);

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(mockedUseEvidenceResolve).toHaveBeenCalledWith({
      subjectType: 'personal_state',
      stableId: 'pa_20260719_goal_career_01',
      snapshotId: 'ps_20260719_a1b2c3d4e5f6',
      checksum: 'c'.repeat(64),
      stateKey: { assertion_kind: 'goal', subject: 'me', domain: 'career', scope: 'current', predicate: 'target_role' },
    });

    // Esc 关闭抽屉，不影响页面其余内容
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
