import type { Mock } from 'vitest';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ExternalContextPage } from '../pages/external/ExternalContextPage';
import { ApiError } from '../api/client';
import { useEvidenceResolve } from '../api/hooks';
import { EXTERNAL_DELTA_ENVELOPE } from './mockData';

// 直接 mock hooks（无 MSW）：默认返回手工构造的 external_delta.get 信封样例，
// 个别测试可覆盖 currentQuery 来验证 offline/error 等非默认路径。
// useEvidenceResolve 是 Phase 37 Plan 03"查看证据"入口依赖的唯一数据 hook，
// 默认 pending（抽屉自身的六态渲染由 EvidenceDrawer.test.tsx 覆盖，此处只验证入口接线）。
let currentQuery: {
  isPending: boolean;
  isError: boolean;
  error?: unknown;
  data?: unknown;
  refetch: () => void;
};

vi.mock('../api/hooks', () => ({
  useExternalDelta: () => currentQuery,
  useEvidenceResolve: vi.fn(() => ({ isPending: true, isError: false, data: undefined, refetch: vi.fn() })),
}));

const mockedUseEvidenceResolve = useEvidenceResolve as unknown as Mock;

/** 徽标内含 SVG 图标，文字被拆成多个节点，用 textContent 匹配 */
const badgeWithText = (text: string) => (_: string, el: Element | null) =>
  el?.tagName === 'SPAN' && el.textContent === text;

function renderPage() {
  return render(
    <MemoryRouter>
      <ExternalContextPage />
    </MemoryRouter>,
  );
}

describe('ExternalContextPage（/external）', () => {
  beforeEach(() => {
    currentQuery = { isPending: false, isError: false, data: EXTERNAL_DELTA_ENVELOPE, refetch: vi.fn() };
  });

  it('渲染隔离免责声明与 Delta 四组（含冲突分组与冲突事实卡）', () => {
    renderPage();

    // spec §7.5 硬性要求：显著提示条
    expect(
      screen.getByText((_, el) => el?.tagName === 'P' && el.textContent === '外部事实不会自动成为个人事实。'),
    ).toBeInTheDocument();

    // Delta 四组标题；空组显示"无"
    expect(screen.getByRole('region', { name: '新增' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: '即将过期' })).toBeInTheDocument();
    // updated=[] 是已知权威限制（未提供逐事实更新事件），必须显式陈述为 limitation，
    // 不能被渲染成"本次没有更新"（Phase 37 Plan 02 Task 3 / D-37-02）
    const updatedRegion = screen.getByRole('region', { name: '更新' });
    expect(within(updatedRegion).getByText(/External 权威未提供逐事实更新事件/)).toBeInTheDocument();
    expect(within(updatedRegion).queryByText('无')).not.toBeInTheDocument();

    // 冲突分组：渲染冲突事实卡（短 ID + 红色冲突标识 + 类型徽标）
    const conflictRegion = within(screen.getByRole('region', { name: '冲突' }));
    expect(conflictRegion.getByText('ef_20260717_…')).toBeInTheDocument();
    expect(conflictRegion.getByText(badgeWithText('冲突'))).toBeInTheDocument();
    expect(conflictRegion.getAllByText('job_market').length).toBeGreaterThan(0);

    // 宽松字段：f2 缺 region/source_quality 等 → 显式"未提供"
    expect(screen.getAllByText('未提供').length).toBeGreaterThan(0);

    // 顶部计数与来源表格（allowlist 状态）
    expect(screen.getByText((_, el) => el?.tagName === 'LI' && el.textContent === '冲突 1')).toBeInTheDocument();
    const sourcesRegion = within(screen.getByRole('region', { name: '来源列表' }));
    expect(sourcesRegion.getByText('src_mohrss_policy')).toBeInTheDocument();
    expect(sourcesRegion.getByText('已允许')).toBeInTheDocument();
    expect(sourcesRegion.getByText('人社部政策发布')).toBeInTheDocument();
    // 第二个来源缺名称与 allowlist 字段 → "未提供"
    expect(sourcesRegion.getByText('src_job_board_iot')).toBeInTheDocument();
  });

  it('地区筛选为纯客户端过滤：筛掉不匹配的事实组', () => {
    renderPage();

    fireEvent.change(screen.getByLabelText('地区'), { target: { value: 'CN' } });

    // f2 无 region、f3 地区为 CN-Shanghai，均被筛掉 → 对应组显示"被筛选排除"回退行；
    // f1 地区 CN，仍在新增组
    const excludedNote = (_: string, el: Element | null) =>
      el?.tagName === 'LI' && (el.textContent ?? '').includes('已被当前筛选条件排除');
    expect(within(screen.getByRole('region', { name: '即将过期' })).getByText(excludedNote)).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: '冲突' })).getByText(excludedNote)).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: '新增' })).getByText('ef_20260719_…')).toBeInTheDocument();

    // 清除筛选后恢复
    fireEvent.click(screen.getByRole('button', { name: '清除筛选' }));
    expect(within(screen.getByRole('region', { name: '冲突' })).getByText('ef_20260717_…')).toBeInTheDocument();
  });

  it('事实卡直接渲染服务端 lifecycle 与 freshness.level/reason（图标+文字，不用浏览器时钟推断，D-37-02）', () => {
    renderPage();

    // f1 lifecycle='current' → LifecycleBadge「当前」；freshness.level='valid' → FreshnessBadge「新鲜」
    const newRegion = within(screen.getByRole('region', { name: '新增' }));
    expect(newRegion.getByText(badgeWithText('当前'))).toBeInTheDocument();
    expect(newRegion.getByText(badgeWithText('新鲜'))).toBeInTheDocument();

    // f3（冲突分组）freshness.level='expiring_soon' → FreshnessBadge「即将过期」，reason 进入 title
    const conflictRegion = within(screen.getByRole('region', { name: '冲突' }));
    const expiringBadge = conflictRegion.getByText(badgeWithText('即将过期'));
    expect(expiringBadge.closest('.badge')?.getAttribute('title')).toContain('valid_to 距 snapshot 参考时间不足');
  });

  it('必需字段缺失（f2 缺 lifecycle/freshness）显式标为 partial，而非普通"未提供"（D-37-02 pitfall #7）', () => {
    renderPage();
    const expiringRegion = within(screen.getByRole('region', { name: '即将过期' }));
    expect(
      expiringRegion.getByText(/该事实资料不完整（缺少lifecycle（记录状态）、新鲜度分级）/),
    ).toBeInTheDocument();
  });

  it('offline 与 error 是不同的用户可见状态（D-37-03）', () => {
    currentQuery = {
      isPending: false,
      isError: true,
      error: new ApiError('network_error', '无法连接后端服务'),
      data: undefined,
      refetch: vi.fn(),
    };
    renderPage();
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('外部环境加载失败');
    expect(alert).toHaveTextContent('不代表数据已被清空');
  });

  it('事实卡"查看证据"打开 Evidence Drawer，携带该事实的稳定引用三元组（Phase 37 Plan 03，EVID-01）', () => {
    renderPage();
    const newRegion = within(screen.getByRole('region', { name: '新增' }));

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    fireEvent.click(newRegion.getByRole('button', { name: '查看证据' }));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(mockedUseEvidenceResolve).toHaveBeenCalledWith({
      subjectType: 'external_fact',
      stableId: 'ef_20260719_aaaa1111bbbb',
      snapshotId: 'es_20260718_f6e5d4c3b2a1',
      checksum: 'efc_20260719_aaaa1111bbbb',
    });
  });
});
