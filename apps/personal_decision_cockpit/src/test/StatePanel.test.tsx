import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatePanel } from '../components/feedback/StatePanel';

// 状态模型测试（spec §12 / §17.1）：error 态可告警，partial 态列出不可用 Authority
describe('StatePanel', () => {
  it('error 态渲染 role="alert" 与重试按钮', () => {
    render(
      <StatePanel
        variant="error"
        title="今日总览加载失败"
        errorMessage="无法连接后端服务"
        onRetry={() => {}}
      />,
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('今日总览加载失败')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /重试/ })).toBeInTheDocument();
  });

  it('partial 态列出不可用 Authority 名称', () => {
    render(
      <StatePanel
        variant="partial"
        title="部分数据暂不可用"
        unavailableAuthorities={['决策分析', '主动提醒']}
      />,
    );
    expect(screen.getByText('部分数据暂不可用')).toBeInTheDocument();
    expect(screen.getByText('决策分析')).toBeInTheDocument();
    expect(screen.getByText('主动提醒')).toBeInTheDocument();
  });
});
