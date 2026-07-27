import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { EvidencePage } from '../pages/evidence/EvidencePage';
import { ApiError } from '../api/client';
import { SYSTEM_STATUS_ENVELOPE } from './mockData';

/**
 * 证据中心页面测试（Phase 37 Plan 03 Task 3，D-37-05/D-37-06）：
 * - 先说明 current-object Evidence Drawer 是权威只读路径，再把 Widget 收口到
 *   显式"诊断 / 历史集成"区域；
 * - MCP 服务上线 / 不可用 / system status 本身查询失败三种场景都不留空白成功卡；
 * - iframe 使用最小 sandbox（仅 allow-scripts）、no-referrer、描述性 title；
 * - Memory Graph 显式标注为历史/诊断，不是当前 Personal State SSOT。
 */

let currentQuery: {
  isPending: boolean;
  isError: boolean;
  error?: unknown;
  data?: unknown;
  refetch: () => void;
};

vi.mock('../api/hooks', () => ({
  useSystemStatus: () => currentQuery,
}));

function withMcpUp(up: boolean) {
  return {
    ...SYSTEM_STATUS_ENVELOPE,
    data: { ...SYSTEM_STATUS_ENVELOPE.data, ports: { ...SYSTEM_STATUS_ENVELOPE.data.ports, mcp: { up, port: 8789 } } },
  };
}

describe('EvidencePage（/evidence）', () => {
  it('先说明 current-object Evidence Drawer 是权威只读路径', () => {
    currentQuery = { isPending: false, isError: false, data: withMcpUp(true), refetch: vi.fn() };
    render(<EvidencePage />);
    expect(screen.getByText(/权威的只读证据下钻路径是/)).toBeInTheDocument();
    expect(screen.getByText(/当前对象的"查看证据"/)).toBeInTheDocument();
  });

  it('MCP 服务可达（ports.mcp.up=true）：渲染最小 sandbox 的 iframe，不含 same-origin/top-navigation/popup/download/form', () => {
    currentQuery = { isPending: false, isError: false, data: withMcpUp(true), refetch: vi.fn() };
    render(<EvidencePage />);

    const iframe = screen.getByTitle(/数据浏览器/) as HTMLIFrameElement;
    expect(iframe.getAttribute('sandbox')).toBe('allow-scripts');
    expect(iframe.getAttribute('referrerpolicy')).toBe('no-referrer');
    expect(iframe.getAttribute('src')).toBe('http://127.0.0.1:8789/widgets/data-browser-widget.html');
    expect(screen.queryByText('诊断集成当前不可达')).not.toBeInTheDocument();
  });

  it('MCP 服务不可达（ports.mcp.up=false）：三个 Widget 均显示非空 recovery card，而非空白 iframe', () => {
    currentQuery = { isPending: false, isError: false, data: withMcpUp(false), refetch: vi.fn() };
    render(<EvidencePage />);

    expect(screen.getAllByText('诊断集成当前不可达')).toHaveLength(3);
    expect(screen.getAllByRole('button', { name: '重试' })).toHaveLength(3);
    expect(screen.getAllByRole('link', { name: '在新窗口打开确认' })).toHaveLength(3);
    expect(screen.queryByTitle(/数据浏览器/)).not.toBeInTheDocument();
  });

  it('system status 查询失败时仍非空：显示"无法确认"提示，且不阻止 Widget 尝试加载', () => {
    currentQuery = {
      isPending: false,
      isError: true,
      error: new ApiError('network_error', '无法连接后端服务'),
      data: undefined,
      refetch: vi.fn(),
    };
    render(<EvidencePage />);
    expect(screen.getByText('无法确认 MCP 服务运行状态')).toBeInTheDocument();
    expect(screen.getByTitle(/数据浏览器/)).toBeInTheDocument();
  });

  it('Memory Graph 显式标注为历史/诊断而非当前 Personal State SSOT', () => {
    currentQuery = { isPending: false, isError: false, data: withMcpUp(true), refetch: vi.fn() };
    render(<EvidencePage />);
    const memoryGraphSection = screen.getByText('Memory Graph').closest('section') as HTMLElement;
    expect(within(memoryGraphSection).getByText(/不是当前 Personal State SSOT/)).toBeInTheDocument();
  });

  it('iframe 加载超时（受控超时判断）显示非空提示；随后 onLoad 触发后清除提示', async () => {
    vi.useFakeTimers();
    currentQuery = { isPending: false, isError: false, data: withMcpUp(true), refetch: vi.fn() };
    render(<EvidencePage />);

    const dataBrowserSection = screen.getByText('数据浏览器').closest('section') as HTMLElement;
    const iframe = within(dataBrowserSection).getByTitle(/数据浏览器/);
    act(() => { vi.advanceTimersByTime(4001); });
    expect(within(dataBrowserSection).getByText(/尚未确认加载/)).toBeInTheDocument();
    act(() => { fireEvent.load(iframe); });
    expect(within(dataBrowserSection).queryByText(/尚未确认加载/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Widget 已验证|Widget 加载成功/)).not.toBeInTheDocument();
    vi.useRealTimers();
  });
});
