import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { EvidencePage } from '../pages/evidence/EvidencePage';

vi.mock('../api/hooks', () => ({
  useSystemStatus: () => ({
    isPending: false,
    isError: false,
    data: { data: { ports: { mcp: { up: false } } } },
  }),
}));

describe('EvidencePage degraded widget boundary', () => {
  it('shows a non-empty diagnostic recovery card when MCP is unavailable', () => {
    render(<MemoryRouter><EvidencePage /></MemoryRouter>);
    expect(screen.getAllByText('诊断集成当前不可达').length).toBeGreaterThan(0);
    expect(screen.getByText(/不是当前 Personal State 的权威读取路径/)).toBeInTheDocument();
    expect(screen.getByText(/Memory Graph 是旧关系层探索工具/)).toBeInTheDocument();
    expect(screen.queryByTitle(/数据浏览器（诊断/)).not.toBeInTheDocument();
  });
});
