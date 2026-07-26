import type { Mock } from 'vitest';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { EvidenceDrawer } from '../components/evidence/EvidenceDrawer';
import { useEvidenceResolve } from '../api/hooks';
import { ApiError } from '../api/client';
import type { EvidenceReferenceInput } from '../api/hooks';

/**
 * Evidence Drawer 测试（Phase 37 Plan 03 Task 1，EVID-01）：
 * - 只依赖 Plan 37-01 的只读 GET hook `useEvidenceResolve`（GET-only，无 mutation 路径）；
 * - 六种 status（ok/abstain/mismatch/expired/not_found/authority_unavailable）逐一区分渲染；
 * - 引用回显恒定展示（无论解析结果如何）；不出现 sealed value、原始对话、路径、provider body、
 *   HMAC 或 confirmation material，也不提供任何写入控件；
 * - Esc 关闭、Tab 焦点圈、卸载后焦点还原。
 */

vi.mock('../api/hooks', () => ({ useEvidenceResolve: vi.fn() }));

const mockedUseEvidenceResolve = useEvidenceResolve as unknown as Mock;

const PERSONAL_REFERENCE: EvidenceReferenceInput = {
  subjectType: 'personal_state',
  stableId: 'pa_20260719_goal_career_01',
  snapshotId: 'ps_20260719_a1b2c3d4e5f6',
  checksum: 'c'.repeat(64),
  stateKey: { assertion_kind: 'goal', subject: 'me', domain: 'career', scope: 'current', predicate: 'target_role' },
};

const EXTERNAL_REFERENCE: EvidenceReferenceInput = {
  subjectType: 'external_fact',
  stableId: 'ef_520f2c2e1ae56134e0dcdbc8',
  snapshotId: 'exs_a7770b7d4e9e2727e359befc',
  checksum: 'cad7760270bebc8d9e5ef11913646c2ed7c1b5a559cb927273161f70a615206c',
};

const DECISION_REFERENCE: EvidenceReferenceInput = {
  subjectType: 'decision',
  stableId: 'rec_attn_001',
  snapshotId: 'ps_20260719_a1b2c3d4e5f6',
  checksum: 'd'.repeat(64),
};

function envelope(overrides: {
  status: string;
  result?: Record<string, unknown> | null;
  nextActions?: string[];
  limitations?: string[];
  reference?: Record<string, unknown>;
}) {
  return {
    schema_version: 'decision_cockpit_projection_v1',
    operation: 'evidence_resolve.get',
    ok: true,
    generated_at: '2026-07-26T08:00:00Z',
    snapshot_bindings: { personal: null, external: null, serving: null },
    freshness: { personal_as_of: null, knowledge_unit_count: null },
    authorities: { evidence: overrides.status === 'authority_unavailable' ? 'error' : 'ok' },
    partial: false,
    limitations: overrides.limitations ?? [],
    data: {
      status: overrides.status,
      reference: overrides.reference ?? {
        subject_type: 'personal_state',
        stable_id: PERSONAL_REFERENCE.stableId,
        snapshot_id: PERSONAL_REFERENCE.snapshotId,
        checksum: PERSONAL_REFERENCE.checksum,
      },
      result: overrides.result ?? null,
      next_actions: overrides.nextActions ?? [],
    },
  };
}

function queryOk(data: unknown) {
  return { isPending: false, isError: false, data, refetch: vi.fn() };
}

function renderDrawer(reference: EvidenceReferenceInput, subjectLabel = 'career · target_role') {
  const onClose = vi.fn();
  render(<EvidenceDrawer reference={reference} subjectLabel={subjectLabel} onClose={onClose} />);
  return { onClose };
}

describe('EvidenceDrawer：只读证据下钻抽屉', () => {
  it('挂载即调用 useEvidenceResolve（唯一数据来源），并恒定展示已提交的稳定引用', () => {
    mockedUseEvidenceResolve.mockReturnValue({ isPending: true, isError: false, data: undefined, refetch: vi.fn() });
    renderDrawer(PERSONAL_REFERENCE);

    expect(mockedUseEvidenceResolve).toHaveBeenCalledWith(PERSONAL_REFERENCE);
    expect(screen.getByRole('dialog', { name: '证据详情：career · target_role' })).toBeInTheDocument();
    expect(screen.getByText('已提交的稳定引用')).toBeInTheDocument();
    expect(screen.getByText('stable_id：')).toBeInTheDocument();
  });

  it('加载中显示 loading 面板', () => {
    mockedUseEvidenceResolve.mockReturnValue({ isPending: true, isError: false, data: undefined, refetch: vi.fn() });
    renderDrawer(PERSONAL_REFERENCE);
    expect(screen.getByLabelText('加载中')).toBeInTheDocument();
  });

  it('status=ok（personal_state）：展示 claim/lifecycle/freshness/置信度/关联证据/下一步', () => {
    mockedUseEvidenceResolve.mockReturnValue(
      queryOk(
        envelope({
          status: 'ok',
          result: {
            subject_type: 'personal_state',
            snapshot_id: PERSONAL_REFERENCE.snapshotId,
            checksum: PERSONAL_REFERENCE.checksum,
            key: { assertion_kind: 'goal', subject: 'me', domain: 'career', scope: 'current', predicate: 'target_role' },
            record_lifecycle: 'current',
            provenance_class: 'fact',
            confidence: 0.9,
            as_of: '2026-07-19T07:30:00Z',
            evidence: [{ ref: 'ku_001', artifact_type: 'knowledge_unit', status: 'active', eligible: true, privacy_class: 'normal' }],
            uncertainty: [],
          },
          nextActions: [],
        }),
      ),
    );
    renderDrawer(PERSONAL_REFERENCE);

    expect(screen.getByRole('status', { name: undefined })).toHaveTextContent('已核验');
    expect(screen.getByText('事实')).toBeInTheDocument();
    expect(screen.getByText((_, el) => el?.tagName === 'SPAN' && el.textContent === '当前')).toBeInTheDocument();
    expect(screen.getByText('target_role')).toBeInTheDocument();
    expect(screen.getByText(/knowledge_unit/)).toBeInTheDocument();
  });

  it('status=abstain：展示"证据暂不满足可用性判定"且仍保留元数据', () => {
    mockedUseEvidenceResolve.mockReturnValue(
      queryOk(
        envelope({
          status: 'abstain',
          result: {
            subject_type: 'personal_state',
            snapshot_id: PERSONAL_REFERENCE.snapshotId,
            checksum: PERSONAL_REFERENCE.checksum,
            key: { assertion_kind: 'goal', subject: 'me', domain: 'career', scope: 'current', predicate: 'target_role' },
            record_lifecycle: 'current',
            provenance_class: 'observation',
            confidence: null,
            as_of: null,
            evidence: [],
            uncertainty: ['insufficient_corroboration'],
          },
          nextActions: ['evidence 暂不满足可用性判定，可稍后重试或改看其它断言'],
        }),
      ),
    );
    renderDrawer(PERSONAL_REFERENCE);

    expect(screen.getByText('证据暂不满足可用性判定')).toBeInTheDocument();
    expect(screen.getByText('insufficient_corroboration')).toBeInTheDocument();
    expect(screen.getByText(/可稍后重试或改看其它断言/)).toBeInTheDocument();
  });

  it.each([
    ['mismatch', '引用已变化（binding mismatch）', 'alert'],
    ['expired', '引用已过期', 'status'],
    ['not_found', '未找到该记录', 'status'],
    ['authority_unavailable', '权威暂时不可用', 'alert'],
  ] as const)('status=%s：展示区分文案且不渲染证据元数据（result 为 null）', (status, label, role) => {
    mockedUseEvidenceResolve.mockReturnValue(
      queryOk(envelope({ status, result: null, nextActions: ['刷新页面后重新下钻'] })),
    );
    renderDrawer(EXTERNAL_REFERENCE);

    expect(screen.getByRole(role)).toHaveTextContent(label);
    expect(screen.queryByLabelText('证据元数据')).not.toBeInTheDocument();
    expect(screen.getByText('刷新页面后重新下钻')).toBeInTheDocument();
  });

  it('status=ok（decision）：展示 confirmation/action 状态与支撑证据', () => {
    mockedUseEvidenceResolve.mockReturnValue(
      queryOk(
        envelope({
          status: 'ok',
          result: {
            subject_type: 'decision',
            snapshot_id: DECISION_REFERENCE.snapshotId,
            checksum: DECISION_REFERENCE.checksum,
            confirmation_state: 'proposed',
            action_state: null,
            recommendation_kind: 'time_allocation',
            domain: 'career',
            rationale_codes: ['goal_misaligned'],
            support: [{ cognitive_type: 'fact', evidence_status: 'verified', record_id: 'pa_20260719_goal_career_01' }],
          },
        }),
      ),
    );
    renderDrawer(DECISION_REFERENCE, 'rec_attn_001');

    expect(screen.getByText('待确认')).toBeInTheDocument();
    expect(screen.getByText('time_allocation')).toBeInTheDocument();
    expect(screen.getByText('goal_misaligned')).toBeInTheDocument();
    expect(screen.getByText(/verified/)).toBeInTheDocument();
  });

  it('传输层 network_error 渲染 offline 面板（与 authority_unavailable 业务态不同）并可重试', () => {
    const refetch = vi.fn();
    mockedUseEvidenceResolve.mockReturnValue({
      isPending: false,
      isError: true,
      error: new ApiError('network_error', '无法连接后端服务'),
      data: undefined,
      refetch,
    });
    renderDrawer(PERSONAL_REFERENCE);

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('证据解析请求失败');
    expect(alert).toHaveTextContent('不代表数据已被清空');
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it('不出现隐私敏感片段（HMAC/路径/原始正文），也不提供任何写入控件', () => {
    mockedUseEvidenceResolve.mockReturnValue(
      queryOk(
        envelope({
          status: 'ok',
          result: {
            subject_type: 'external_fact',
            snapshot_id: EXTERNAL_REFERENCE.snapshotId,
            checksum: EXTERNAL_REFERENCE.checksum,
            subject: 'nodejs',
            predicate: 'release.lts',
            region: 'global',
            valid_from: '2026-01-13T00:00:00Z',
            valid_to: null,
            source_quality: 0.99,
            fact_confidence: 0.99,
            lifecycle: 'current',
          },
        }),
      ),
    );
    const { container } = render(
      <EvidenceDrawer reference={EXTERNAL_REFERENCE} subjectLabel="nodejs · release.lts" onClose={vi.fn()} />,
    );

    expect(container.querySelector('form')).not.toBeInTheDocument();
    expect(container.querySelector('input')).not.toBeInTheDocument();
    expect(container.textContent).not.toMatch(/HMAC|confirmation_token|C:\\\\|payload_checksum/i);
    // 仅有遮罩 + header 两个关闭按钮，没有任何写入类按钮（确认/提交/保存/写入）
    const buttonNames = screen.getAllByRole('button').map((btn) => btn.getAttribute('aria-label') ?? btn.textContent);
    expect(buttonNames).toEqual(['关闭证据详情', '关闭']);
  });

  it('Esc 关闭抽屉；卸载后焦点还原到触发元素', async () => {
    mockedUseEvidenceResolve.mockReturnValue({ isPending: true, isError: false, data: undefined, refetch: vi.fn() });
    const trigger = document.createElement('button');
    trigger.textContent = '查看证据';
    document.body.appendChild(trigger);
    trigger.focus();
    expect(document.activeElement).toBe(trigger);

    const onClose = vi.fn();
    const { unmount } = render(
      <EvidenceDrawer reference={PERSONAL_REFERENCE} subjectLabel="career · target_role" onClose={onClose} />,
    );

    // 打开后焦点进入抽屉内部（关闭按钮或首个可聚焦元素）
    await waitFor(() => expect(document.activeElement).not.toBe(trigger));

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);

    unmount();
    expect(document.activeElement).toBe(trigger);
    trigger.remove();
  });
});
