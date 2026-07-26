import type { Mock } from 'vitest';
import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { DecisionWorkspacePage } from '../pages/decisions/DecisionWorkspacePage';
import { ApiError } from '../api/client';
import { useEvidenceResolve } from '../api/hooks';
import {
  DECISION_WORKSPACE_CLOSED_ENVELOPE,
  DECISION_WORKSPACE_ENVELOPE,
  DECISION_WORKSPACE_EXPIRED_ENVELOPE,
  DECISION_WORKSPACE_FIELDS_MISSING_ENVELOPE,
  DECISION_WORKSPACE_NON_PROJECT_ENVELOPE,
  DECISION_WORKSPACE_NO_EVIDENCE_ENVELOPE,
  DECISION_WORKSPACE_PARTIAL_ENVELOPE,
  DECISION_WORKSPACE_UNBOUND_ENVELOPE,
} from './mockData';

/**
 * DecisionWorkspacePage 补充测试（Phase 37 Plan 03 Task 2，EVID-01）：
 * 决策工作区头部新增只读"查看证据"入口，携带 recommendation 的
 * recommendation_id/snapshot_id/recommendation_checksum 稳定引用三元组；
 * 本计划不新增、替换或绕过既有 guarded 记录行动/结果按钮与 session 流程，
 * 这里额外验证该按钮与其 case_id 预填逻辑不受"查看证据"入口影响。
 */

let currentQuery: {
  isPending: boolean;
  isError: boolean;
  error?: unknown;
  data?: unknown;
  refetch: () => void;
};

vi.mock('../api/hooks', () => ({
  useDecisionWorkspace: () => currentQuery,
  useEvidenceResolve: vi.fn(() => ({ isPending: true, isError: false, data: undefined, refetch: vi.fn() })),
}));

const mockedUseEvidenceResolve = useEvidenceResolve as unknown as Mock;

function renderPage(id = 'rec_attn_001') {
  return render(
    <MemoryRouter initialEntries={[`/decisions/${id}`]}>
      <Routes>
        <Route path="/decisions/:id" element={<DecisionWorkspacePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('DecisionWorkspacePage（/decisions/:id）：只读证据下钻入口', () => {
  it('recommendation 具备完整稳定引用时渲染"查看证据"，点击打开 Drawer 并携带 recommendation 引用', () => {
    currentQuery = { isPending: false, isError: false, data: DECISION_WORKSPACE_ENVELOPE, refetch: vi.fn() };
    renderPage();

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '查看证据' }));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(mockedUseEvidenceResolve).toHaveBeenCalledWith({
      subjectType: 'decision',
      stableId: 'rec_attn_001',
      snapshotId: DECISION_WORKSPACE_ENVELOPE.data.recommendation.snapshot_id,
      checksum: DECISION_WORKSPACE_ENVELOPE.data.recommendation.recommendation_checksum,
    });

    // 既有的"记录行动/结果"guarded 入口不受影响，仍然存在
    expect(screen.getByRole('button', { name: /记录行动\/结果/ })).toBeInTheDocument();
  });

  it('recommendation 缺少 recommendation_checksum 时不渲染"查看证据"（不构造伪 evidence）', () => {
    currentQuery = {
      isPending: false,
      isError: false,
      data: {
        ...DECISION_WORKSPACE_ENVELOPE,
        data: {
          ...DECISION_WORKSPACE_ENVELOPE.data,
          recommendation: { ...DECISION_WORKSPACE_ENVELOPE.data.recommendation, recommendation_checksum: null },
        },
      },
      refetch: vi.fn(),
    };
    renderPage();
    expect(screen.queryByRole('button', { name: '查看证据' })).not.toBeInTheDocument();
  });

  it('recommendation 为 null 时仍显示 partial 面板，不因证据入口改动而回归', () => {
    currentQuery = {
      isPending: false,
      isError: false,
      data: { ...DECISION_WORKSPACE_ENVELOPE, data: { ...DECISION_WORKSPACE_ENVELOPE.data, recommendation: null } },
      refetch: vi.fn(),
    };
    renderPage();
    expect(screen.getByText('建议详情暂不可用')).toBeInTheDocument();
  });

  it('error 态显示重试并不渲染证据入口', () => {
    currentQuery = {
      isPending: false,
      isError: true,
      error: new ApiError('http_500', '后端返回 HTTP 500'),
      data: undefined,
      refetch: vi.fn(),
    };
    renderPage();
    expect(screen.getByRole('alert')).toHaveTextContent('决策工作区加载失败');
    expect(screen.queryByRole('button', { name: '查看证据' })).not.toBeInTheDocument();
  });
});

/**
 * DEC-01 决策比较（Phase 38 Task 1/2）：问题/目标/硬约束/风险预算/候选方案/
 * 不行动基线/成本/机会成本/假设/反面证据/停止条件必须逐一可见，缺失字段
 * 显式"未提供"而非静默省略或用单一分数替代。
 */
describe('DecisionWorkspacePage：DEC-01 决策比较', () => {
  function comparisonSection() {
    return screen.getByRole('heading', { name: '决策比较（DEC-01）' }).closest('section') as HTMLElement;
  }

  it('完整样例：硬约束/假设/反面证据以列表渲染，风险预算按 project 域显式为 low', () => {
    currentQuery = { isPending: false, isError: false, data: DECISION_WORKSPACE_ENVELOPE, refetch: vi.fn() };
    renderPage();
    const section = within(comparisonSection());
    expect(section.getByText('每周总投入不超过 30 小时')).toBeInTheDocument();
    expect(section.getByText('未来 8 周项目范围不再扩大')).toBeInTheDocument();
    expect(section.getByText('若项目风险评级上升为 high，本建议应重新评估后再确认')).toBeInTheDocument();
    expect(section.getByText('low')).toBeInTheDocument();
    expect(section.getByText(/目标对象：/)).toBeInTheDocument();
    expect(section.getByText(/预期收益：/)).toBeInTheDocument();
  });

  it('字段缺失样例（真实 recommendations.get 现状）：target/costs_constraints/assumptions/contraindications 皆显式"未提供"', () => {
    currentQuery = {
      isPending: false,
      isError: false,
      data: DECISION_WORKSPACE_FIELDS_MISSING_ENVELOPE,
      refetch: vi.fn(),
    };
    renderPage();
    const section = within(comparisonSection());
    // 目标对象/预期收益不再拼接展示；候选方案行退化为仅剩 recommendation_kind
    expect(section.queryByText(/目标对象：/)).not.toBeInTheDocument();
    expect(section.queryByText(/预期收益：/)).not.toBeInTheDocument();
    // 决策问题/目标/不行动基线/机会成本/停止条件（各 1）+ 硬约束/假设/反面证据（各 1，空数组）= 8
    expect(section.getAllByText('未提供')).toHaveLength(8);
  });

  it('非 project 域样例：风险预算显式"未提供"并说明原因', () => {
    currentQuery = {
      isPending: false,
      isError: false,
      data: DECISION_WORKSPACE_NON_PROJECT_ENVELOPE,
      refetch: vi.fn(),
    };
    renderPage();
    const section = within(comparisonSection());
    expect(section.getByText(/仅 project 域的受控会话固定风险预算为 low/)).toBeInTheDocument();
  });
});

/**
 * fail-closed 资格门（Phase 38 Task 3）：partial、stale、conflict、binding
 * mismatch 或 evidence insufficient 时，"记录行动/结果"guarded 入口必须消失，
 * 只保留只读阻断说明与刷新恢复路径；合格样例保持既有入口可用。
 */
describe('DecisionWorkspacePage：fail-closed 资格门', () => {
  function expectBlocked(reasonText: string) {
    expect(screen.queryByRole('button', { name: /记录行动\/结果/ })).not.toBeInTheDocument();
    expect(screen.getByText('暂不能发起受控会话')).toBeInTheDocument();
    expect(screen.getByText(reasonText)).toBeInTheDocument();
  }

  it('过期样例：expires_at 已过 → 阻断，不渲染写入入口', () => {
    currentQuery = { isPending: false, isError: false, data: DECISION_WORKSPACE_EXPIRED_ENVELOPE, refetch: vi.fn() };
    renderPage();
    expectBlocked('建议已过有效期');
  });

  it('已关闭样例：confirmation_state=rejected → 阻断', () => {
    currentQuery = { isPending: false, isError: false, data: DECISION_WORKSPACE_CLOSED_ENVELOPE, refetch: vi.fn() };
    renderPage();
    expectBlocked('确认状态已关闭（已拒绝 / 已延迟 / 已撤销），不应继续写入');
  });

  it('非 project 域样例：domain=career → 阻断（Phase 38 只开放 project 域）', () => {
    currentQuery = {
      isPending: false,
      isError: false,
      data: DECISION_WORKSPACE_NON_PROJECT_ENVELOPE,
      refetch: vi.fn(),
    };
    renderPage();
    expectBlocked('仅 project 域开放受控会话（当前建议不属于 project 域）');
  });

  it('证据不足样例：support 为空 → 阻断', () => {
    currentQuery = {
      isPending: false,
      isError: false,
      data: DECISION_WORKSPACE_NO_EVIDENCE_ENVELOPE,
      refetch: vi.fn(),
    };
    renderPage();
    expectBlocked('缺少支撑证据，信息不足');
  });

  it('缺少 Personal snapshot 绑定样例：snapshot_id 为空 → 阻断', () => {
    currentQuery = { isPending: false, isError: false, data: DECISION_WORKSPACE_UNBOUND_ENVELOPE, refetch: vi.fn() };
    renderPage();
    expectBlocked('缺少 Personal snapshot 绑定');
  });

  it('投影部分可用样例：envelope.partial=true → 阻断', () => {
    currentQuery = { isPending: false, isError: false, data: DECISION_WORKSPACE_PARTIAL_ENVELOPE, refetch: vi.fn() };
    renderPage();
    expectBlocked('本次投影为部分可用，真值状态不完整');
  });

  it('刷新后重试按钮调用 query.refetch，不发起任何写入请求', () => {
    const refetch = vi.fn();
    currentQuery = { isPending: false, isError: false, data: DECISION_WORKSPACE_EXPIRED_ENVELOPE, refetch };
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: '刷新后重试' }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it('合格样例：既有"记录行动/结果"入口保留，不出现阻断提示', () => {
    currentQuery = { isPending: false, isError: false, data: DECISION_WORKSPACE_ENVELOPE, refetch: vi.fn() };
    renderPage();
    expect(screen.getByRole('button', { name: /记录行动\/结果/ })).toBeInTheDocument();
    expect(screen.queryByText('暂不能发起受控会话')).not.toBeInTheDocument();
  });
});
