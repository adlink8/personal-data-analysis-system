import { useEffect, useRef } from 'react';
import type { ApiError } from '../../api/client';
import type { EvidenceReferenceInput } from '../../api/hooks';
import { useEvidenceResolve } from '../../api/hooks';
import type {
  EvidenceResolveEnvelope,
  EvidenceResolveStatus,
  EvidenceResult,
  EvidenceSubjectType,
  SupportEntry,
} from '../../api/schemas';
import { fmtConfidence, fmtTime } from '../../utils/format';
import { ClaimKindBadge, ConfirmationStateBadge, LifecycleBadge } from '../authority/ClaimLifecycleBadges';
import { shortId } from '../authority/SnapshotChip';
import { FreshnessBadge } from '../feedback/FreshnessBadge';
import { StatePanel } from '../feedback/StatePanel';
import { ActionStateBadge } from '../decision/stateBadges';
import { IconAlertTriangle, IconArrowLeftRight, IconCheckCircle, IconClock, IconInfo, IconX } from '../icons';

/**
 * 通用只读证据抽屉（Phase 37 Plan 03 Task 1，EVID-01）：唯一的证据下钻入口。
 * 调用方只能传入某次 Projection 响应已经给出的 stable_id/snapshot_id/checksum
 * （personal_state 额外要求完整 state key）——本组件自身不重建、不猜测、不回退到
 * "最新记录"；`useEvidenceResolve`（Plan 37-01）只发起同源只读 GET，没有任何写入
 * payload 或 mutation 控件。six-status 词表（ok/mismatch/expired/abstain/not_found/
 * authority_unavailable）逐一区分渲染，authority_unavailable 不是死胡同——展示为
 * 有界的、可恢复的降级说明，而不是页面级异常。
 */

type IconComponent = typeof IconInfo;

/* ---------------- 引用回显（无论解析结果如何都恒定展示） ---------------- */

const SUBJECT_LABELS: Record<EvidenceSubjectType, string> = {
  personal_state: '个人状态',
  external_fact: '外部环境',
  decision: '决策分析',
};

function FieldRow({
  label,
  value,
  mono,
  title,
}: {
  label: string;
  value: string | null | undefined;
  mono?: boolean;
  title?: string;
}) {
  return (
    <div className="break-words">
      <dt className="inline text-muted">{label}：</dt>
      <dd className={`inline ${mono ? 'font-mono text-xs' : ''}`} title={title}>
        {value ?? '未提供'}
      </dd>
    </div>
  );
}

function ReferenceBlock({ reference }: { reference: EvidenceReferenceInput }) {
  return (
    <section className="rounded-lg border border-line bg-surface p-3" aria-label="已提交的稳定引用">
      <h3 className="text-sm font-medium">已提交的稳定引用</h3>
      <p className="mt-1 text-xs text-muted">
        以下引用来自卡片渲染时已持有的字段；本次请求不会从浏览器重建或替换为最新记录。
      </p>
      <dl className="mt-2 space-y-1 text-sm">
        <FieldRow label="Authority" value={SUBJECT_LABELS[reference.subjectType]} />
        <FieldRow label="stable_id" value={shortId(reference.stableId, 24)} mono title={reference.stableId} />
        <FieldRow label="snapshot_id" value={shortId(reference.snapshotId, 24)} mono title={reference.snapshotId} />
        <FieldRow label="checksum" value={shortId(reference.checksum, 24)} mono title={reference.checksum} />
      </dl>
    </section>
  );
}

/* ---------------- 六态状态横幅（typed status，互斥且可区分） ---------------- */

interface StatusMeta {
  label: string;
  description: string;
  frameClass: string;
  textClass: string;
  Icon: IconComponent;
  role: 'status' | 'alert';
}

const STATUS_META: Record<EvidenceResolveStatus, StatusMeta> = {
  ok: {
    label: '已核验',
    description: '当前引用与服务端记录一致：以下信息来自本次快照绑定的权威记录。',
    frameClass: 'border-verified bg-verified-soft',
    textClass: 'text-verified',
    Icon: IconCheckCircle,
    role: 'status',
  },
  abstain: {
    label: '证据暂不满足可用性判定',
    description: '引用仍与当前记录匹配，但证据尚不足以直接采信；请结合下方限制说明谨慎使用，不建议据此确认决策。',
    frameClass: 'border-uncertainty bg-uncertainty-soft',
    textClass: 'text-uncertainty',
    Icon: IconAlertTriangle,
    role: 'status',
  },
  mismatch: {
    label: '引用已变化（binding mismatch）',
    description: '该卡片绑定的 stable_id / snapshot_id / checksum 与当前记录不再一致；系统不会静默替换为最新记录。',
    frameClass: 'border-risk bg-risk-soft',
    textClass: 'text-risk',
    Icon: IconArrowLeftRight,
    role: 'alert',
  },
  expired: {
    label: '引用已过期',
    description: '该引用绑定的 snapshot / run 语境已失效，无法再被解释为当前证据。',
    frameClass: 'border-uncertainty bg-uncertainty-soft',
    textClass: 'text-uncertainty',
    Icon: IconClock,
    role: 'status',
  },
  not_found: {
    label: '未找到该记录',
    description: '未找到与该稳定引用对应的记录：可能已被移除，或引用本身不完整。',
    frameClass: 'border-line bg-panel',
    textClass: 'text-muted',
    Icon: IconInfo,
    role: 'status',
  },
  authority_unavailable: {
    label: '权威暂时不可用',
    description: '本次证据读取因单个 Authority 故障被隔离：不代表数据已丢失，也不是页面级异常，可稍后重试。',
    frameClass: 'border-risk bg-risk-soft',
    textClass: 'text-risk',
    Icon: IconAlertTriangle,
    role: 'alert',
  },
};

function StatusBanner({ status }: { status: EvidenceResolveStatus }) {
  const meta = STATUS_META[status];
  const Icon = meta.Icon;
  return (
    <div className={`card ${meta.frameClass}`} role={meta.role}>
      <div className="flex items-start gap-3">
        <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${meta.textClass}`} />
        <div className="min-w-0 flex-1">
          <p className={`font-medium ${meta.textClass}`}>{meta.label}</p>
          <p className="mt-1 text-sm text-muted">{meta.description}</p>
        </div>
      </div>
    </div>
  );
}

/* ---------------- 解析成功（ok/abstain）时的证据元数据 ---------------- */

function SupportEntryRow({ entry }: { entry: SupportEntry }) {
  return (
    <li className="rounded-md border border-line bg-panel p-2 text-xs">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="badge border-line bg-surface text-muted">{entry.cognitive_type ?? '未提供'}</span>
        {entry.evidence_status ? (
          <span className="badge border-line bg-surface text-muted">{entry.evidence_status}</span>
        ) : null}
      </div>
      <p className="mt-1 break-all font-mono text-muted" title={entry.record_id ?? undefined}>
        record_id：{entry.record_id ? shortId(entry.record_id, 24) : '未提供'}
      </p>
    </li>
  );
}

function PersonalResultFields({ result }: { result: EvidenceResult }) {
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        {result.provenance_class ? <ClaimKindBadge kind={result.provenance_class} /> : null}
        <LifecycleBadge status={result.record_lifecycle} />
        <FreshnessBadge asOf={result.as_of} />
      </div>
      <FieldRow label="主体" value={result.key?.subject} />
      <FieldRow label="谓词" value={result.key?.predicate} />
      <FieldRow label="置信度" value={fmtConfidence(result.confidence)} />
      {(result.evidence ?? []).length > 0 ? (
        <div>
          <dt className="text-muted">关联证据</dt>
          <dd className="mt-1">
            <ul className="flex flex-wrap gap-1.5">
              {(result.evidence ?? []).map((item, i) => (
                <li key={item.ref ?? `evidence-${i}`} className="badge border-line bg-panel text-muted">
                  {item.artifact_type ?? '未提供'} · {item.status ?? '未提供'}
                  {item.eligible === false ? '（不合格）' : ''}
                </li>
              ))}
            </ul>
          </dd>
        </div>
      ) : null}
    </>
  );
}

function ExternalResultFields({ result }: { result: EvidenceResult }) {
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <LifecycleBadge status={result.lifecycle} />
        <FreshnessBadge asOf={result.valid_from} />
      </div>
      <FieldRow label="主体" value={result.subject} />
      <FieldRow label="谓词" value={result.predicate} />
      <FieldRow label="地区" value={result.region} />
      <FieldRow
        label="有效期"
        value={
          result.valid_from || result.valid_to
            ? `${result.valid_from ? fmtTime(result.valid_from) : '—'} ~ ${result.valid_to ? fmtTime(result.valid_to) : '—'}`
            : null
        }
      />
      <FieldRow label="来源质量" value={result.source_quality != null ? String(result.source_quality) : null} />
      <FieldRow label="事实置信度" value={fmtConfidence(result.fact_confidence)} />
    </>
  );
}

function DecisionResultFields({ result }: { result: EvidenceResult }) {
  return (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <ConfirmationStateBadge state={result.confirmation_state} />
        <ActionStateBadge state={result.action_state} />
      </div>
      <FieldRow label="建议类型" value={result.recommendation_kind} />
      <FieldRow label="领域" value={result.domain} />
      {(result.rationale_codes ?? []).length > 0 ? (
        <div>
          <dt className="text-muted">rationale_codes</dt>
          <dd className="mt-1">
            <ul className="flex flex-wrap gap-1.5">
              {(result.rationale_codes ?? []).map((code) => (
                <li key={code} className="badge border-line bg-panel font-mono text-xs text-muted">
                  {code}
                </li>
              ))}
            </ul>
          </dd>
        </div>
      ) : null}
      {(result.support ?? []).length > 0 ? (
        <div>
          <dt className="text-muted">支撑证据</dt>
          <dd className="mt-1">
            <ul className="section-stack">
              {(result.support ?? []).map((entry, i) => (
                <SupportEntryRow key={entry.record_id ?? `support-${i}`} entry={entry} />
              ))}
            </ul>
          </dd>
        </div>
      ) : null}
    </>
  );
}

function ResultDetail({ subjectType, result }: { subjectType: EvidenceSubjectType; result: EvidenceResult }) {
  return (
    <section className="rounded-lg border border-line bg-surface p-3" aria-label="证据元数据">
      <h3 className="text-sm font-medium">证据元数据</h3>
      <dl className="mt-2 space-y-2 text-sm">
        <FieldRow label="Snapshot" value={result.snapshot_id ? shortId(result.snapshot_id, 24) : null} mono title={result.snapshot_id ?? undefined} />
        <FieldRow label="Checksum" value={result.checksum ? shortId(result.checksum, 24) : null} mono title={result.checksum ?? undefined} />
        {subjectType === 'personal_state' ? <PersonalResultFields result={result} /> : null}
        {subjectType === 'external_fact' ? <ExternalResultFields result={result} /> : null}
        {subjectType === 'decision' ? <DecisionResultFields result={result} /> : null}
        {(result.uncertainty ?? []).length > 0 ? (
          <div>
            <dt className="text-muted">不确定性</dt>
            <dd className="mt-1">
              <ul className="list-disc pl-5 text-muted">
                {(result.uncertainty ?? []).map((reason, i) => (
                  <li key={i}>{reason}</li>
                ))}
              </ul>
            </dd>
          </div>
        ) : null}
      </dl>
    </section>
  );
}

/* ---------------- 限制与安全的下一步（对全部状态恒定可见） ---------------- */

function LimitationsAndNextActions({ envelope }: { envelope: EvidenceResolveEnvelope }) {
  const { limitations } = envelope;
  const { next_actions: nextActions } = envelope.data;
  if (limitations.length === 0 && nextActions.length === 0) return null;
  return (
    <>
      {limitations.length > 0 ? (
        <section aria-label="限制">
          <h3 className="text-sm font-medium">限制</h3>
          <ul className="mt-1 list-disc pl-5 text-sm text-muted">
            {limitations.map((limitation, i) => (
              <li key={i}>{limitation}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {nextActions.length > 0 ? (
        <section aria-label="安全的下一步">
          <h3 className="text-sm font-medium">下一步</h3>
          <ul className="mt-1 list-disc pl-5 text-sm text-muted">
            {nextActions.map((action, i) => (
              <li key={i}>{action}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}

function ResolvedBody({ envelope, subjectType }: { envelope: EvidenceResolveEnvelope; subjectType: EvidenceSubjectType }) {
  const { data } = envelope;
  return (
    <>
      <StatusBanner status={data.status} />
      {data.result ? <ResultDetail subjectType={subjectType} result={data.result} /> : null}
      <LimitationsAndNextActions envelope={envelope} />
    </>
  );
}

/* ---------------- 抽屉外壳：键盘、焦点圈、焦点还原（同 ConfirmDrawer 模式） ---------------- */

export interface EvidenceDrawerProps {
  /** 唯一的证据引用来源：调用方渲染时已持有的 stable_id/snapshot_id/checksum（+ personal_state 的完整 state key） */
  reference: EvidenceReferenceInput;
  /** 抽屉标题旁的对象说明（如 "career · target_role" / "nodejs · release.lts" / recommendation 短 ID） */
  subjectLabel: string;
  onClose: () => void;
}

export function EvidenceDrawer({ reference, subjectLabel, onClose }: EvidenceDrawerProps) {
  const query = useEvidenceResolve(reference);
  const panelRef = useRef<HTMLElement>(null);
  const restoreFocusRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // 挂载即视为打开（父组件用条件挂载控制显隐，不复用 ConfirmDrawer 的 open 翻转模式）：
  // Esc 关闭、Tab 焦点圈、卸载时焦点还原；只在挂载/卸载各跑一次，避免父组件重渲染打断焦点。
  useEffect(() => {
    restoreFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    panelRef.current?.querySelector<HTMLElement>('button, [href], input, select, textarea')?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onCloseRef.current();
        return;
      }
      if (event.key === 'Tab') {
        const panel = panelRef.current;
        if (!panel) return;
        const focusable = panel.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        const active = document.activeElement;
        if (event.shiftKey && (active === first || !panel.contains(active))) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && (active === last || !panel.contains(active))) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      const target = restoreFocusRef.current;
      if (target?.isConnected) target.focus();
    };
  }, []);

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={`证据详情：${subjectLabel}`}>
      <button
        type="button"
        aria-label="关闭证据详情"
        className="absolute inset-0 h-full w-full cursor-default overlay-backdrop"
        onClick={onClose}
      />
      <aside
        ref={panelRef}
        className="absolute inset-y-0 right-0 flex w-full max-w-lg flex-col border-l border-line bg-panel shadow-xl"
      >
        <header className="flex items-start justify-between gap-3 border-b border-line p-4">
          <div>
            <p className="text-xs text-muted">只读证据下钻</p>
            <h2 className="mt-0.5 text-lg font-semibold">{subjectLabel}</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="rounded-md border border-line p-1.5 text-muted transition-colors hover:bg-surface focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <IconX />
          </button>
        </header>

        <div className="section-stack flex-1 overflow-y-auto p-4">
          <ReferenceBlock reference={reference} />

          {query.isPending ? <StatePanel variant="loading" /> : null}

          {query.isError
            ? (() => {
                const err = query.error as ApiError;
                return (
                  <StatePanel
                    variant={err.code === 'network_error' ? 'offline' : 'error'}
                    title="证据解析请求失败"
                    errorMessage={err.message}
                    onRetry={() => void query.refetch()}
                  />
                );
              })()
            : null}

          {query.data ? <ResolvedBody envelope={query.data} subjectType={reference.subjectType} /> : null}
        </div>
      </aside>
    </div>
  );
}
