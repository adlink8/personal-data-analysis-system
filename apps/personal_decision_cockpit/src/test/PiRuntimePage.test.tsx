import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PiRuntimePage } from '../pages/system/PiRuntimePage';

vi.mock('../api/hooks', () => ({
  usePiRuntimeStatus: () => ({ isPending: false, isError: false, data: { state: 'ready', observed_at: '2026-08-04T00:00:00Z', provider_calls: 0 } }),
  usePiRuntimeTasks: () => ({ isPending: false, isError: false, data: { tasks: [{ task_id: 'task-1', event_id: 'event-1', state: 'outcome_unknown', version: 2, session_id: 'session-1', progress: 0, tool_label: '', evidence_refs: [], recovery_action: 'inspect_status', observed_at: '2026-08-04T00:00:00Z' }] } }),
}));

describe('PiRuntimePage', () => {
  it('shows truthful outcome_unknown state and metadata-only privacy notice', () => {
    render(<PiRuntimePage />);
    expect(screen.getByRole('heading', { name: 'AI Runtime' })).toBeInTheDocument();
    expect(screen.getAllByText('结果状态未知').length).toBeGreaterThan(0);
    expect(screen.getByText(/不展示提示词/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain('prompt');
  });
});
