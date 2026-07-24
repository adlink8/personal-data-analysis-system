import { Link, useParams } from 'react-router-dom';
import type { ApiError } from '../../api/client';
import { usePersonalState } from '../../api/hooks';
import type {
  PersonalAssertion,
  PersonalStateData,
  PersonalStateDomain,
  PersonalStateEnvelope,
  RecentChange,
} from '../../api/schemas';
import { SnapshotChip } from '../../components/authority/SnapshotChip';
import { FreshnessBadge } from '../../components/feedback/FreshnessBadge';
import { StatePanel } from '../../components/feedback/StatePanel';
import {
  IconAlertTriangle,
  IconArchive,
  IconArrowLeft,
  IconArrowLeftRight,
  IconCheckCircle,
  IconChevronRight,
  IconClock,
  IconEye,
  IconInfo,
  IconLock,
  IconShield,
  IconSparkles,
} from '../../components/icons';
import { fmtConfidence, fmtNumber, fmtTime } from '../../utils/format';

/**
 * 个人状态（spec §7.2）：八领域当前模型，区分 事实 / 观察 / 推断 / 冲突 / 历史。
 * 视觉规则：Fact=实线边框+"事实"标签，Observation=蓝灰标签，Inference=紫色虚线边框+"推断"，
 * Conflict=红色双向冲突标识，stale/resolved/expired=降透明度+文字标注；
 * 颜色一律配文字 + 图标（spec §9.2）。断言值只有 checksum，页面只展示元数据。
 */

type IconComponent = typeof IconInfo;

/* ---------------- 领域与状态元数据 ---------------- */

interface DomainMeta {
  key: string;
  label: string;
  /** 健康/财务/关系为高风险域（spec §13.3），只读页面加域级风险提示 */
  highRisk?: boolean;
}

const DOMAINS: ReadonlyArray<DomainMeta> = [
  { key: 'learning', label: '学习' },
  { key: 'career', label: '职业' },
  { key: 'project', label: '项目' },
  { key: 'health', label: '健康', highRisk: true },
  { key: 'finance', label: '财务', highRisk: true },
  { key: 'relationship', label: '关系', highRisk: true },
  { key: 'time', label: '时间' },
  { key: 'energy', label: '精力' },
];

const KIND_LABELS = [
  { key: 'goal', label: '目标' },
  { key: 'constraint', label: '约束' },
  { key: 'observation', label: '观察' },
  { key: 'state', label: '状态' },
] as const;

const CLAIM_META: Record<string, { label: string; badgeClass: string; Icon: IconComponent }> = {
  fact: { label: '事实', badgeClass: 'border-line bg-panel text-ink', Icon: IconCheckCircle },
  observation: { label: '观察', badgeClass: 'border-line bg-surface text-muted', Icon: IconEye },
  inference: { label: '推断', badgeClass: 'border-candidate bg-candidate-soft text-candidate', Icon: IconSparkles },
};

const CLAIM_ORDER: readonly string[] = ['fact', 'observation', 'inference'];

const STATUS_META: Record<string, { label: string; textClass: string; Icon: IconComponent }> = {
  current: { label: '当前', textClass: 'text-verified', Icon: IconCheckCircle },
  stale: { label: '偏旧', textClass: 'text-uncertainty', Icon: IconClock },
  conflict: { label: '冲突', textClass: 'text-risk', Icon: IconArrowLeftRight },
  resolved: { label: '已解决', textClass: 'text-muted', Icon: IconCheckCircle },
  expired: { label: '已过期', textClass: 'text-muted', Icon: IconArchive },
};

const LIFECYCLE_ORDER: readonly string[] = ['current', 'stale', 'conflict', 'resolved', 'expired'];

/** 历史态（spec §7.2 Historical）：降低透明度，不默认参与当前判断 */
const HISTORICAL_STATUSES: ReadonlySet<string> = new Set(['stale', 'resolved', 'expired']);

function domainLabel(key: string | null | undefined): string {
  if (!key) return '未提供';
  return DOMAINS.find((d) => d.key === key)?.label ?? key;
}

function errorAuthorities(envelope: PersonalStateEnvelope): string[] {
  return Object.entries(envelope.authorities)
    .filter(([, value]) => value === 'error')
    .map(([name]) => name);
}

function evidenceText(count: number | null | undefined): string {
  return count === null || count === undefined ? '未提供' : `${fmtNumber(count)} 条`;
}

/* ---------------- 徽标与通用小块 ---------------- */

function ClaimBadge({ claim }: { claim: string }) {
  const meta = CLAIM_META[claim] ?? { label: claim, badgeClass: 'border-line bg-panel text-muted', Icon: IconInfo };
  const Icon = meta.Icon;
  return (
    <span className={`badge ${meta.badgeClass}`}>
      <Icon className="h-3.5 w-3.5" />
      {meta.label}
    </span>
  );
}

function StatusBadge({ status }: { status: string }) {
  const meta = STATUS_META[status];
  if (!meta || status === 'current') return null;
  const Icon = meta.Icon;
  return (
    <span className={`badge border-line bg-panel ${meta.textClass}`}>
      <Icon className="h-3.5 w-3.5" />
      {meta.label}
    </span>
  );
}

function HighRiskHint() {
  return (
    <p className="mt-2 flex items-center gap-1 text-xs text-uncertainty">
      <IconShield className="h-3.5 w-3.5 shrink-0" />
      高风险领域：任何行动需显式确认
    </p>
  );
}

function BackLink() {
  return (
    <p>
      <Link
        to="/state"
        className="inline-flex items-center gap-1 text-sm text-primary transition-colors hover:underline focus:outline-none focus:ring-2 focus:ring-primary"
      >
        <IconArrowLeft className="h-4 w-4" />
        返回八领域总览
      </Link>
    </p>
  );
}

/* ---------------- 顶部：快照 + 生命周期摘要条 ---------------- */

function LifecycleStrip({ counts }: { counts: PersonalStateData['lifecycle_counts'] }) {
  const countOf = (status: string): number | null => {
    if (!counts) return null;
    const value = (counts as Record<string, unknown>)[status];
    return typeof value === 'number' ? value : null;
  };
  return (
    <ul className="mt-3 flex flex-wrap gap-2" aria-label="生命周期分布">
      {LIFECYCLE_ORDER.map((status) => {
        const meta = STATUS_META[status];
        const Icon = meta.Icon;
        return (
          <li key={status} className={`badge border-line bg-panel ${meta.textClass}`}>
            <Icon className="h-3.5 w-3.5" />
            {meta.label} <span className="font-medium">{fmtNumber(countOf(status))}</span>
          </li>
        );
      })}
    </ul>
  );
}

/* ---------------- 八领域网格 ---------------- */

function DomainCard({ meta, domain }: { meta: DomainMeta; domain: PersonalStateDomain | null }) {
  if (domain === null) {
    return (
      <div className="card flex h-full flex-col" aria-label={`${meta.label}领域暂不可用`}>
        <div className="flex items-baseline justify-between gap-2">
          <h3 className="font-medium">{meta.label}</h3>
          <span className="text-xs text-muted">{meta.key}</span>
        </div>
        <p className="mt-3 flex items-center gap-1.5 text-sm text-uncertainty">
          <IconAlertTriangle className="h-4 w-4 shrink-0" />
          该领域数据暂不可用
        </p>
        {meta.highRisk ? <HighRiskHint /> : null}
      </div>
    );
  }

  const conflicts = domain.conflicts ?? 0;
  return (
    <Link
      to={`/state/${meta.key}`}
      className="card flex h-full flex-col transition-colors hover:border-primary focus:outline-none focus:ring-2 focus:ring-primary"
      aria-label={`查看${meta.label}领域详情`}
    >
      <div className="flex items-baseline justify-between gap-2">
        <h3 className="font-medium">{meta.label}</h3>
        <span className="text-xs text-muted">{meta.key}</span>
      </div>
      <p className="mt-2">
        <span className="text-2xl font-semibold">{fmtNumber(domain.total)}</span>
        <span className="ml-1 text-xs text-muted">条当前断言</span>
      </p>
      <dl className="mt-3 grid grid-cols-4 gap-1 text-center">
        {KIND_LABELS.map((kind) => (
          <div key={kind.key} className="rounded-md bg-surface px-1 py-1.5">
            <dt className="text-xs text-muted">{kind.label}</dt>
            <dd className="mt-0.5 text-sm font-medium">{fmtNumber(domain.by_kind?.[kind.key])}</dd>
          </div>
        ))}
      </dl>
      {conflicts > 0 ? (
        <p className="mt-3">
          <span className="badge border-risk bg-risk-soft text-risk">
            <IconArrowLeftRight className="h-3.5 w-3.5" />
            冲突 {fmtNumber(conflicts)}
          </span>
        </p>
      ) : null}
      {meta.highRisk ? <HighRiskHint /> : null}
      <span className="mt-auto inline-flex items-center gap-1 pt-3 text-xs text-primary">
        查看详情
        <IconChevronRight className="h-3.5 w-3.5" />
      </span>
    </Link>
  );
}

/* ---------------- 领域详情：断言按 claim 类型分组 ---------------- */

function AssertionCard({ assertion }: { assertion: PersonalAssertion }) {
  const claim = assertion.provenance_class ?? 'unknown';
  const status = assertion.status ?? 'current';
  const isConflict = status === 'conflict';
  const isHistorical = HISTORICAL_STATUSES.has(status);

  // Fact=实线边框；Inference=紫色虚线边框；Conflict=红色冲突标识优先于类型边框色
  const frameClass = isConflict
    ? 'border-risk bg-risk-soft'
    : claim === 'inference'
      ? 'border-candidate border-dashed bg-surface'
      : 'border-line bg-surface';

  return (
    <li className={`rounded-lg border p-3 ${frameClass} ${isHistorical ? 'opacity-60' : ''}`}>
      <div className="flex flex-wrap items-center gap-2">
        <ClaimBadge claim={claim} />
        <StatusBadge status={status} />
        <span className="break-words font-medium">{assertion.key.predicate ?? '（无谓词）'}</span>
      </div>
      <p className="mt-1.5 break-words text-sm text-muted">
        主体 {assertion.key.subject ?? '未提供'} · 范围 {assertion.key.scope ?? '未提供'} · 置信度{' '}
        {fmtConfidence(assertion.confidence)} · 证据 {evidenceText(assertion.evidence_count)}
      </p>
    </li>
  );
}

function groupByClaim(assertions: PersonalAssertion[]): Array<{ claim: string; items: PersonalAssertion[] }> {
  const map = new Map<string, PersonalAssertion[]>();
  for (const assertion of assertions) {
    const claim = assertion.provenance_class ?? 'unknown';
    const list = map.get(claim) ?? [];
    list.push(assertion);
    map.set(claim, list);
  }
  const orderedKeys = [
    ...CLAIM_ORDER.filter((key) => map.has(key)),
    ...[...map.keys()].filter((key) => !CLAIM_ORDER.includes(key)),
  ];
  return orderedKeys.map((claim) => ({ claim, items: map.get(claim) ?? [] }));
}

function DomainDetail({ domainKey, data }: { domainKey: string; data: PersonalStateData }) {
  const meta = DOMAINS.find((d) => d.key === domainKey);
  if (!meta) {
    return (
      <div className="section-stack">
        <BackLink />
        <StatePanel
          variant="empty"
          title={`未知领域：${domainKey}`}
          description="个人状态仅覆盖学习 / 职业 / 项目 / 健康 / 财务 / 关系 / 时间 / 精力八个领域。"
          nextStep="返回八领域总览选择有效领域。"
        />
      </div>
    );
  }

  const domain = data.domains[domainKey] ?? null;
  if (domain === null) {
    return (
      <div className="section-stack">
        <BackLink />
        <StatePanel
          variant="partial"
          title={`${meta.label}领域数据暂不可用`}
          unavailableAuthorities={[`个人状态 · ${meta.label}`]}
        />
      </div>
    );
  }

  const conflicts = domain.conflicts ?? 0;
  const groups = groupByClaim(domain.assertions);

  return (
    <div className="section-stack">
      <BackLink />

      <header className="card">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-lg font-semibold">{meta.label}领域</h1>
          <span className="text-sm text-muted">{meta.key}</span>
          {conflicts > 0 ? (
            <span className="badge border-risk bg-risk-soft text-risk">
              <IconArrowLeftRight className="h-3.5 w-3.5" />
              冲突 {fmtNumber(conflicts)}
            </span>
          ) : null}
        </div>
        <p className="mt-2 text-sm text-muted">
          当前断言 {fmtNumber(domain.total)} 条 · 数据截止 {fmtTime(data.as_of)}
        </p>
        {meta.highRisk ? <HighRiskHint /> : null}
      </header>

      <section className="card" aria-labelledby="domain-assertions-title">
        <h2 id="domain-assertions-title" className="font-semibold">
          当前断言
        </h2>
        <p className="mt-1 flex items-center gap-1.5 text-xs text-muted">
          <IconLock className="h-3.5 w-3.5 shrink-0" />
          断言值仅保留 checksum：内容经隐私封存，仅展示元数据。
        </p>
        {groups.length === 0 ? (
          <div className="mt-3">
            <StatePanel
              variant="empty"
              title="该领域当前没有断言"
              description="快照已覆盖此领域，但暂无有效断言记录。"
              nextStep="可通过日常对话同步（pk-sync）与 KU 流程累积个人事实。"
            />
          </div>
        ) : (
          <div className="section-stack mt-4">
            {groups.map((group) => (
              <section key={group.claim} aria-label={`${CLAIM_META[group.claim]?.label ?? group.claim}分组`}>
                <h3 className="flex items-center gap-2 text-sm font-medium">
                  <ClaimBadge claim={group.claim} />
                  <span className="text-muted">{group.items.length} 条</span>
                </h3>
                <ul className="section-stack mt-2">
                  {group.items.map((assertion, index) => (
                    <AssertionCard
                      key={assertion.current_assertion_id ?? `assertion-${index}`}
                      assertion={assertion}
                    />
                  ))}
                </ul>
              </section>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

/* ---------------- 近期变化 ---------------- */

function ChangeStatusText({ status }: { status: string | null | undefined }) {
  if (!status) return <span className="text-muted">未提供</span>;
  const meta = STATUS_META[status];
  if (!meta) return <span className="text-muted">{status}</span>;
  const Icon = meta.Icon;
  return (
    <span className={`inline-flex items-center gap-1 ${meta.textClass}`}>
      <Icon className="h-3.5 w-3.5" />
      {meta.label}
    </span>
  );
}

function RecentChangesCard({ changes }: { changes: RecentChange[] }) {
  return (
    <section className="card" aria-labelledby="recent-changes-title">
      <h2 id="recent-changes-title" className="font-semibold">
        近期变化
      </h2>
      <p className="mt-0.5 text-sm text-muted">最近的断言新增、更新与状态变化（排序由投影给出）</p>
      {changes.length === 0 ? (
        <div className="mt-3">
          <StatePanel
            variant="empty"
            title="暂无近期变化"
            description="当前快照窗口内没有记录到断言新增、更新或状态变化。"
          />
        </div>
      ) : (
        <ol className="section-stack mt-3">
          {changes.map((change, index) => (
            <li
              key={`${change.effective_at ?? change.observed_at ?? 'na'}-${index}`}
              className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-line bg-surface p-3 text-sm"
            >
              <span className="font-mono text-xs text-muted">{fmtTime(change.effective_at ?? change.observed_at)}</span>
              <span className="badge border-line bg-panel text-ink">{change.change_type ?? change.record_type ?? '未提供'}</span>
              <span>{domainLabel(change.domain)}</span>
              <span className="break-words text-muted">{change.subject ?? '未提供'}</span>
              <ChangeStatusText status={change.status} />
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

/* ---------------- 页面 ---------------- */

function StateOverview({ data }: { data: PersonalStateData }) {
  const hasAnyDomain = DOMAINS.some((meta) => data.domains[meta.key] != null);
  return (
    <>
      <header className="card">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-lg font-semibold">个人状态</h1>
          <SnapshotChip label="Personal" snapshotId={data.snapshot_id} />
          <FreshnessBadge asOf={data.as_of} />
        </div>
        <p className="mt-2 text-sm text-muted">
          数据截止 {fmtTime(data.as_of)} · 当前有效断言共 {fmtNumber(data.total_available)} 条
        </p>
        <LifecycleStrip counts={data.lifecycle_counts} />
      </header>

      <section aria-labelledby="domain-grid-title">
        <div className="flex items-baseline justify-between gap-2 px-1">
          <h2 id="domain-grid-title" className="font-semibold">
            八领域状态
          </h2>
          <p className="text-xs text-muted">点击卡片进入领域详情</p>
        </div>
        {hasAnyDomain ? (
          <ul className="mt-3 grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {DOMAINS.map((meta) => (
              <li key={meta.key}>
                <DomainCard meta={meta} domain={data.domains[meta.key] ?? null} />
              </li>
            ))}
          </ul>
        ) : (
          <div className="mt-3">
            <StatePanel
              variant="empty"
              title="当前快照没有领域数据"
              description="Personal Snapshot 已绑定，但八个领域均未返回断言统计。"
              nextStep="可先通过对话同步（pk-sync）与 KU 流程累积个人事实，再查看本页。"
            />
          </div>
        )}
      </section>

      <RecentChangesCard changes={data.recent_changes} />
    </>
  );
}

export function PersonalStatePage() {
  const { domain } = useParams<{ domain?: string }>();
  const query = usePersonalState();

  if (query.isPending) {
    return (
      <div className="section-stack" aria-label="个人状态加载中">
        <StatePanel variant="loading" />
        <StatePanel variant="loading" />
        <StatePanel variant="loading" />
      </div>
    );
  }

  if (query.isError) {
    const err = query.error as ApiError;
    return (
      <StatePanel
        variant="error"
        title="个人状态加载失败"
        errorMessage={err.message}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const envelope = query.data;
  const { data } = envelope;

  return (
    <div className="section-stack">
      {/* 部分失败提示条：不伪装完整成功（spec §11.3） */}
      {envelope.partial || envelope.limitations.length > 0 ? (
        <div className="card border-uncertainty bg-uncertainty-soft" role="status">
          <p className="flex items-center gap-2 text-sm font-medium text-uncertainty">
            <IconAlertTriangle />
            本次投影为部分可用
          </p>
          {envelope.limitations.length > 0 ? (
            <ul className="mt-1 list-disc pl-8 text-sm text-muted">
              {envelope.limitations.map((limitation, i) => (
                <li key={i}>{limitation}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}

      {data === null ? (
        <StatePanel
          variant="partial"
          title="个人状态暂不可用"
          unavailableAuthorities={errorAuthorities(envelope)}
          description="个人状态 Authority 本次未返回数据，其余页面不受影响。"
        />
      ) : domain !== undefined ? (
        <DomainDetail domainKey={domain} data={data} />
      ) : (
        <StateOverview data={data} />
      )}
    </div>
  );
}
