import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ExternalContextPage } from '../pages/external/ExternalContextPage';

// 直接 mock hooks（无 MSW）：返回手工构造的 external_delta.get 信封样例
vi.mock('../api/hooks', async () => {
  const { EXTERNAL_DELTA_ENVELOPE } = await import('./mockData');
  return {
    useExternalDelta: () => ({ isPending: false, isError: false, data: EXTERNAL_DELTA_ENVELOPE }),
  };
});

/** 徽标内含 SVG 图标，文字被拆成多个节点，用 textContent 匹配 */
const badgeWithText = (text: string) => (_: string, el: Element | null) =>
  el?.tagName === 'SPAN' && el.textContent === text;

describe('ExternalContextPage（/external）', () => {
  it('渲染隔离免责声明与 Delta 四组（含冲突分组与冲突事实卡）', () => {
    render(
      <MemoryRouter>
        <ExternalContextPage />
      </MemoryRouter>,
    );

    // spec §7.5 硬性要求：显著提示条
    expect(
      screen.getByText((_, el) => el?.tagName === 'P' && el.textContent === '外部事实不会自动成为个人事实。'),
    ).toBeInTheDocument();

    // Delta 四组标题；空组显示"无"
    expect(screen.getByRole('region', { name: '新增' })).toBeInTheDocument();
    expect(screen.getByRole('region', { name: '即将过期' })).toBeInTheDocument();
    const updatedRegion = screen.getByRole('region', { name: '更新' });
    expect(within(updatedRegion).getByText('无')).toBeInTheDocument();

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
    render(
      <MemoryRouter>
        <ExternalContextPage />
      </MemoryRouter>,
    );

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
});
