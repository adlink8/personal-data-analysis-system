import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SystemPage } from '../pages/system/SystemPage';
import { SYSTEM_STATUS_ENVELOPE } from './mockData';

const state = { envelope: SYSTEM_STATUS_ENVELOPE as any };
vi.mock('../api/hooks', () => ({
  useSystemStatus: () => ({ isPending: false, isError: false, data: state.envelope }),
  usePiOperations: () => ({ isPending: false, isError: false, data: { schema_version: 'pi_operation_projection_v1', ok: true, state: 'ready', operations: [], observed_at: '2026-08-05T00:00:00Z', recovery_action: 'none' } }),
}));

describe('SystemPage（/system）', () => {
  it('按来源、时间、范围展示独立运行观测，不合并成全局健康', () => {
    render(<MemoryRouter><SystemPage /></MemoryRouter>);
    expect(screen.getByRole('region', { name: '独立运行观测' })).toBeInTheDocument();
    expect(screen.getByRole('article', { name: 'REST 当前响应' })).toBeInTheDocument();
    expect(screen.getByRole('article', { name: 'MCP listener' })).toBeInTheDocument();
    expect(screen.getByText(/REST 请求成功不等于整栈健康/)).toBeInTheDocument();
    expect(screen.getByRole('article', { name: 'supervisor last observation' })).toBeInTheDocument();
  });

  it('明确 Cockpit 没有进程或 Tunnel 控制面', () => {
    render(<MemoryRouter><SystemPage /></MemoryRouter>);
    expect(screen.getByText(/不能启动、停止、重启、杀掉进程或配置 Tunnel/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /启动|停止|重启|杀掉|配置/ })).not.toBeInTheDocument();
  });
});
