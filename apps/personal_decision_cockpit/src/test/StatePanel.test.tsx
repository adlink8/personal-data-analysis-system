import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatePanel } from '../components/feedback/StatePanel';

// 状态模型测试（spec §12 / §17.1）：error 态可告警，partial 态列出不可用 Authority
describe('StatePanel', () => {
  it('error 态渲染 role="alert" 与重试按钮', () => {
    render(<StatePanel variant="error" title="今日总览加载失败" errorMessage="无法连接后端服务" onRetry={() => {}} />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('今日总览加载失败')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /重试/ })).toBeInTheDocument();
  });

  it('partial 态列出不可用 Authority 名称', () => {
    render(<StatePanel variant="partial" title="部分数据暂不可用" unavailableAuthorities={['决策分析', '主动提醒']} />);
    expect(screen.getByText('部分数据暂不可用')).toBeInTheDocument();
    expect(screen.getByText('决策分析')).toBeInTheDocument();
    expect(screen.getByText('主动提醒')).toBeInTheDocument();
  });

  it('offline 态：role="alert"，说明整个 API 不可达且不代表数据被清空', () => {
    render(<StatePanel variant="offline" title="今日总览加载失败" errorMessage="无法连接后端服务" onRetry={() => {}} />);
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('今日总览加载失败');
    expect(alert).toHaveTextContent('无法连接后端服务');
    expect(alert).toHaveTextContent('不代表数据已被清空');
    expect(screen.getByRole('button', { name: /重试/ })).toBeInTheDocument();
  });

  it('stale 态：展示数据时间与重新同步入口，不伪装成当前成功', () => {
    render(<StatePanel variant="stale" asOfText="2026-07-20 08:00:00" onRetry={() => {}} />);
    expect(screen.getByRole('status')).toBeInTheDocument();
    expect(screen.getByText('数据已偏旧')).toBeInTheDocument();
    expect(screen.getByText(/2026-07-20 08:00:00/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /重新同步/ })).toBeInTheDocument();
  });

  it('conflict 态：陈述冲突条目，不自动选择一边', () => {
    render(<StatePanel variant="conflict" conflictItems={['职业领域断言 A vs B']} />);
    expect(screen.getByText('存在冲突记录')).toBeInTheDocument();
    expect(screen.getByText('职业领域断言 A vs B')).toBeInTheDocument();
    expect(screen.getByText('系统不会自动选择一边，请人工核对后再决定。')).toBeInTheDocument();
  });
});
