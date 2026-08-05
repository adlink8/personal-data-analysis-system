import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SystemPage } from '../pages/system/SystemPage';
import { SYSTEM_STATUS_ENVELOPE } from './mockData';

const mutate = vi.fn();
vi.mock('../api/hooks', () => ({
  useSystemStatus: () => ({ isPending: false, isError: false, data: SYSTEM_STATUS_ENVELOPE }),
  usePiOperations: () => ({ isPending: false, isError: false, data: { schema_version: 'pi_operation_projection_v1', ok: true, state: 'ready', operations: [{ schema_version: 'pi_operation_projection_v1', operation_id: 'op:provider:1', operation_kind: 'provider', task_id: 'task:1', session_id: 'session:1', correlation_id: 'corr:1', authority_class: 'authority:kernel', side_effect_class: 'mutation', snapshot_id: 'snapshot:1', state: 'outcome_unknown', version: 2, attempt: 1, budget: { token_limit: 100, cost_limit: 0, timeout_ms: 1000, token_used: 10, cost_used: 0 }, receipt_refs: [], fingerprint_refs: [], allowed_actions: ['reconcile'], reason: 'provider_timeout', created_at: '2026-08-05T00:00:00Z', updated_at: '2026-08-05T00:00:00Z' }], observed_at: '2026-08-05T00:00:00Z', recovery_action: 'none' } }),
  usePiOperationMutation: () => ({ isPending: false, mutate }),
}));

describe('Pi operation status', () => {
  it('shows plane/state and keeps the control metadata-only', () => {
    render(<MemoryRouter><SystemPage /></MemoryRouter>);
    expect(screen.getByRole('heading', { name: 'Kernel 操作控制面' })).toBeInTheDocument();
    expect(screen.getByText('provider')).toBeInTheDocument();
    expect(screen.getByText('outcome_unknown')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'reconcile' })).toBeInTheDocument();
    expect(document.body.textContent).not.toContain('prompt');
    expect(document.body.textContent).not.toContain('credential');
  });
});
