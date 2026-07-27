import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatePanel } from '../components/feedback/StatePanel';

describe('StatePanel truth states', () => {
  it('keeps offline, partial and stale distinct with recovery copy', () => {
    const { rerender } = render(<StatePanel variant="offline" onRetry={vi.fn()} />);
    expect(screen.getByRole('alert')).toHaveTextContent('服务当前不可达');
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument();

    rerender(<StatePanel variant="partial" unavailableAuthorities={['decision']} description="其它区域仍可读" />);
    expect(screen.getByText('以下 Authority 暂不可用：')).toBeInTheDocument();
    expect(screen.getByText('其它区域仍可读')).toBeInTheDocument();

    rerender(<StatePanel variant="stale" asOfText="2026-07-20" />);
    expect(screen.getByText('数据已偏旧')).toBeInTheDocument();
    expect(screen.getByText(/数据时间：2026-07-20/)).toBeInTheDocument();
  });
});
