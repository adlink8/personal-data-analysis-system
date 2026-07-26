/**
 * 共享的 claim kind（事实/观察/推断/建议候选/用户确认）、record lifecycle（记录生命周期）
 * 与 decision confirmation（用户确认状态）语义映射（spec §7.2/§9.2，Phase 37 Plan 02 Task 1）。
 *
 * 三条轴线互相独立，不合并成一个颜色字段（D-37-01 / RESEARCH.md 架构模式 2）：
 * - Claim / object kind：产出该记录的权威类别（事实 / 观察 / 推断 / 决策侧的建议候选 / 用户确认）。
 * - Record lifecycle：权威自身发布的记录状态（当前 / 偏旧 / 冲突 / 已解决 / 已过期……）。
 * - Historical 是展示分组（历史态降透明度），不是伪造出来的第三种 lifecycle 值。
 *
 * 服务端权威闭集（复用而非重新发明）：
 * - personal_state.get 的 provenance_class ∈ {fact, observation, inference}
 *   （intelligence/schema.py PROVENANCE_CLASSES）。
 * - personal_state.get 的 lifecycle_counts ∈ {current, stale, conflict, resolved, expired}
 *   （intelligence/schema.py ASSERTION_LIFECYCLES）。
 * - external_delta.get 的 fact.lifecycle ∈ {current, stale, superseded, conflict, invalid}
 *   （ui_projection.py 注释：External 权威自身发布的记录状态，与 personal 闭集不完全相同）。
 * - decision confirmation_state ∈ {proposed, accepted, rejected, deferred, revoked}
 *   （ui_projection.py `_KNOWN_CONFIRMATION_STATES`，36-03 已锁定该词表）。
 *
 * 闭集之外的字符串一律走 fallback（原样展示 + 中性图标），不静默丢弃——
 * state_projection.py 的单条断言 status 偶发出现 unknown/uncertain/future，
 * 而 lifecycle_counts 只统计 5 个已知桶，若前端也用同样的白名单过滤会让这些记录
 * 在 UI 上无声消失，与 spec §12"禁止空白页面和静默失败"相悖。
 */
import {
  IconAlertTriangle,
  IconArchive,
  IconArrowLeftRight,
  IconCheckCircle,
  IconClock,
  IconEye,
  IconInfo,
  IconSparkles,
  IconXCircle,
} from '../icons';

type IconComponent = typeof IconInfo;

/* ---------------- Claim / object kind ---------------- */

export type ClaimKind = 'fact' | 'observation' | 'inference' | 'recommendation' | 'confirmation';

interface ClaimKindMeta {
  label: string;
  badgeClass: string;
  Icon: IconComponent;
}

const CLAIM_KIND_META: Record<ClaimKind, ClaimKindMeta> = {
  fact: { label: '事实', badgeClass: 'border-line bg-panel text-ink', Icon: IconCheckCircle },
  observation: { label: '观察', badgeClass: 'border-line bg-surface text-muted', Icon: IconEye },
  inference: { label: '推断', badgeClass: 'border-candidate bg-candidate-soft text-candidate', Icon: IconSparkles },
  // Decision 侧的两个 claim kind（personal_state 从不产出，仅供 Overview/Decision 复用同一套视觉语义）
  recommendation: { label: '建议候选', badgeClass: 'border-primary bg-primary-soft text-primary', Icon: IconSparkles },
  confirmation: { label: '用户确认', badgeClass: 'border-verified bg-verified-soft text-verified', Icon: IconCheckCircle },
};

/** personal_state.get 真实 provenance_class 顺序（PROVENANCE_CLASSES 排序一致） */
export const PERSONAL_CLAIM_ORDER: readonly ClaimKind[] = ['fact', 'observation', 'inference'];

export function claimKindMeta(kind: string): ClaimKindMeta {
  return (
    (CLAIM_KIND_META as Record<string, ClaimKindMeta>)[kind] ?? {
      label: kind,
      badgeClass: 'border-line bg-panel text-muted',
      Icon: IconInfo,
    }
  );
}

export function ClaimKindBadge({ kind }: { kind: string }) {
  const meta = claimKindMeta(kind);
  const Icon = meta.Icon;
  return (
    <span className={`badge ${meta.badgeClass}`}>
      <Icon className="h-3.5 w-3.5" />
      {meta.label}
    </span>
  );
}

/* ---------------- Record lifecycle（Personal + External 记录状态并集） ---------------- */

export type RecordLifecycle =
  | 'current'
  | 'stale'
  | 'conflict'
  | 'resolved'
  | 'expired'
  | 'superseded'
  | 'invalid'
  | 'unknown'
  | 'uncertain'
  | 'future';

interface LifecycleMeta {
  label: string;
  textClass: string;
  Icon: IconComponent;
}

const LIFECYCLE_META: Record<RecordLifecycle, LifecycleMeta> = {
  current: { label: '当前', textClass: 'text-verified', Icon: IconCheckCircle },
  stale: { label: '偏旧', textClass: 'text-uncertainty', Icon: IconClock },
  conflict: { label: '冲突', textClass: 'text-risk', Icon: IconArrowLeftRight },
  resolved: { label: '已解决', textClass: 'text-muted', Icon: IconCheckCircle },
  expired: { label: '已过期', textClass: 'text-muted', Icon: IconArchive },
  // External 权威专有记录状态（personal_state 不产出，但共享同一套图标/颜色语义）
  superseded: { label: '已被替代', textClass: 'text-muted', Icon: IconArchive },
  invalid: { label: '已失效', textClass: 'text-risk', Icon: IconXCircle },
  // state_projection.py 偶发出现、不计入 lifecycle_counts 五桶的单条记录状态：显式呈现而非丢弃
  unknown: { label: '未知', textClass: 'text-muted', Icon: IconInfo },
  uncertain: { label: '不确定', textClass: 'text-uncertainty', Icon: IconAlertTriangle },
  future: { label: '未来生效', textClass: 'text-muted', Icon: IconClock },
};

/** lifecycle_counts 五桶顺序（与 ASSERTION_LIFECYCLES 闭集一致，personal_state 专用） */
export const LIFECYCLE_ORDER: readonly RecordLifecycle[] = ['current', 'stale', 'conflict', 'resolved', 'expired'];

/**
 * Historical 是展示分组（spec §7.2），不是伪造的第三条 lifecycle 值（D-37-01）：
 * 这些记录状态在断言卡上降透明度展示，且不默认参与"当前"判断。
 */
export const HISTORICAL_LIFECYCLE_STATUSES: ReadonlySet<string> = new Set([
  'stale',
  'resolved',
  'expired',
  'superseded',
]);

export function isHistoricalLifecycle(status: string | null | undefined): boolean {
  return Boolean(status && HISTORICAL_LIFECYCLE_STATUSES.has(status));
}

export function lifecycleMeta(status: string): LifecycleMeta {
  return (
    (LIFECYCLE_META as Record<string, LifecycleMeta>)[status] ?? {
      label: status,
      textClass: 'text-muted',
      Icon: IconInfo,
    }
  );
}

/** hideCurrent：current 是默认态，断言卡等场景可选择不重复展示"当前"徽标 */
export function LifecycleBadge({
  status,
  hideCurrent = false,
}: {
  status: string | null | undefined;
  hideCurrent?: boolean;
}) {
  if (!status) return null;
  if (hideCurrent && status === 'current') return null;
  const meta = lifecycleMeta(status);
  const Icon = meta.Icon;
  return (
    <span className={`badge border-line bg-panel ${meta.textClass}`}>
      <Icon className="h-3.5 w-3.5" />
      {meta.label}
    </span>
  );
}

/* ---------------- Decision confirmation_state（_KNOWN_CONFIRMATION_STATES 闭集） ---------------- */

export type ConfirmationState = 'proposed' | 'accepted' | 'rejected' | 'deferred' | 'revoked';

interface ConfirmationMeta {
  label: string;
  textClass: string;
  Icon: IconComponent;
}

const CONFIRMATION_STATE_META: Record<ConfirmationState, ConfirmationMeta> = {
  proposed: { label: '待确认', textClass: 'text-uncertainty', Icon: IconClock },
  accepted: { label: '已接受', textClass: 'text-verified', Icon: IconCheckCircle },
  rejected: { label: '已拒绝', textClass: 'text-risk', Icon: IconXCircle },
  deferred: { label: '已推迟', textClass: 'text-muted', Icon: IconArchive },
  revoked: { label: '已撤回', textClass: 'text-muted', Icon: IconArchive },
};

/**
 * 已结案状态集合（与 ui_projection.py `_classify_stage` 规则 1 / 36-03 的
 * `CLOSED_CONFIRMATION_STATES` 完全一致）：这些决策不再需要"现在关注"。
 * 提取到共享模块，OverviewPage 直接复用，避免同一份权威词表在多处重复定义。
 */
export const CLOSED_CONFIRMATION_STATES: ReadonlySet<string> = new Set(['rejected', 'deferred', 'revoked']);

export function ConfirmationStateBadge({ state }: { state: string | null | undefined }) {
  if (!state) {
    return (
      <span className="badge border-line bg-panel text-muted">
        <IconInfo className="h-3.5 w-3.5" />
        未提供
      </span>
    );
  }
  const meta =
    (CONFIRMATION_STATE_META as Record<string, ConfirmationMeta>)[state] ??
    { label: state, textClass: 'text-muted', Icon: IconInfo };
  const Icon = meta.Icon;
  return (
    <span className={`badge border-line bg-panel ${meta.textClass}`}>
      <Icon className="h-3.5 w-3.5" />
      {meta.label}
    </span>
  );
}
