import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AppShell, NAV_ITEMS } from '../components/layout/AppShell';
import { AppProviders } from '../app/providers';

vi.mock('../api/hooks', () => ({
  useOverview: () => ({ isPending: false, isError: false, data: { snapshot_bindings: { personal: null, external: null }, freshness: {} } }),
  useSystemStatus: () => ({ isPending: false, isError: false, data: { ok: true, partial: false, authorities: {}, data: { ports: { rest: { up: true } } } } }),
}));

describe('Cockpit navigation accessibility baseline', () => {
  it('keeps all primary destinations text-labelled and keyboard-focusable', () => {
    const { container } = render(<AppProviders><MemoryRouter><AppShell /></MemoryRouter></AppProviders>);
    expect(NAV_ITEMS).toHaveLength(8);
    expect(screen.getAllByRole('navigation').length).toBeGreaterThanOrEqual(2);
    for (const item of NAV_ITEMS) {
      expect(screen.getAllByText(item.zh).length).toBeGreaterThan(0);
    }
    expect(container.querySelectorAll('a[class*="focus:ring"], button[class*="focus:ring"]').length).toBeGreaterThan(0);
  });

  it('keeps mobile More navigation labelled and keyboard-toggleable', () => {
    render(<AppProviders><MemoryRouter><AppShell /></MemoryRouter></AppProviders>);
    const more = screen.getByRole('button', { name: '更多' });
    expect(more).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(more);
    expect(more).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getAllByRole('link', { name: '系统状态' }).length).toBeGreaterThanOrEqual(2);
  });
});
