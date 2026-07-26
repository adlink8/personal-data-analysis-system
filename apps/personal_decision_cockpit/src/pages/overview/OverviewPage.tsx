import type { ApiError } from '../../api/client';
import { useOverview } from '../../api/hooks';
import type { OverviewData, OverviewEnvelope } from '../../api/schemas';
import { AuthorityBadge } from '../../components/authority/AuthorityBadge';
import {
  CLOSED_CONFIRMATION_STATES,
  ConfirmationStateBadge,
  LifecycleBadge,
} from '../../components/authority/ClaimLifecycleBadges';
import { shortId } from '../../components/authority/SnapshotChip';
import { FreshnessBadge } from '../../components/feedback/FreshnessBadge';
import { StatePanel } from '../../components/feedback/StatePanel';
import { IconAlertTriangle, IconClock } from '../../components/icons';
import { fmtConfidence, fmtNumber, fmtTime } from '../../utils/format';

/**
 * 今日总览（spec §7.1）：30 秒回答“我现在最需要关注什么”。
 * 任何一节为 null（对应 Authority error）时只降级该卡片，绝不整页白。
 */

/* ---------------- Now Stack 派生 ---------------- */

interface NowItem {
  /** analysis=决策建议候选；pilot=主动提醒候选 */
  authority: 'analysis' | 'pilot';
  id: string;
  title: string;
  detail: string;
  confidence: number | string | null;
  /** 仅决策项有：claim kind 为 Recommendation + Confirmation 状态两条独立轴（spec §7.2） */
  confirmationState?: string | null;
  /** 仅决策项有：到期/时间窗信息，单独渲染为琥珀色时间徽标（spec §7.2 Forecast 视觉规则） */
  expiresAt?: string | null;
}

/**
 * 决策 confirmation_state 真实词表（D-36-05，见 ui_projection.py `_KNOWN_CONFIRMATION_STATES`
 * 与 `_classify_stage` 规则 1）：rejected/deferred/revoked 已结案，不再需要"现在关注"；
 * proposed/accepted 仍是当前有效状态，继续展示（accepted 显示为"已接受"语义，不是待确认）。
 * 词表外的未知值保守按"需要关注"处理，与后端 needs_attention 兜底一致，不臆造新状态。
 * `CLOSED_CONFIRMATION_STATES` 现由 components/authority/ClaimLifecycleBadges 统一维护
 * （Phase 37 Plan 02），避免同一份权威闭集在多处重复定义。
 */

/**
 * 主动提醒重要性判定：只读服务端权威字段 `importance.final_score`
 * （ui_projection.py `_proactive_inbox_section`），与后端 now/deferrable 分组
 * 使用的同一 ranking policy 阈值（DEFAULT_RANKING_POLICY.threshold = 0.55）对齐。
 * 缺失或非数值时保守判定为非高重要（与后端"unscored → deferrable"一致），
 * 不臆造新的重要性判定字段或权威。
 */
const PROACTIVE_IMPORTANCE_THRESHOLD = 0.55;

function isHighImportance(importance: Record<string, unknown>): boolean {
  const finalScore = importance['final_score'];
  return typeof finalScore === 'number' && finalScore >= PROACTIVE_IMPORTANCE_THRESHOLD;
}

/** 从未结案的决策项 + 主动提醒高重要项派生 Now Stack，最多 3 项 */
function buildNowStack(data: OverviewData): NowItem[] {
  const items: NowItem[] = [];
  for (const it of data.decision?.items ?? []) {
    if (CLOSED_CONFIRMATION_STATES.has(it.confirmation_state ?? '')) continue;
    items.push({
      authority: 'analysis',
      id: it.recommendation_id ?? '（无 ID）',
      title: [it.domain, it.recommendation_kind].filter(Boolean).join(' · ') || '决策建议',
      detail: [it.horizon, it.confirmation_state ? `确认状态：${it.confirmation_state}` : null]
        .filter(Boolean)
        .join(' · '),
      confidence: it.confidence ?? null,
      confirmationState: it.confirmation_state,
      expiresAt: it.expires_at,
    });
  }
  for (const c of data.proactive?.items ?? []) {
    if (!isHighImportance(c.importance)) continue;
    items.push({
      authority: 'pilot',
      id: c.candidate_id ?? '（无 ID）',
      title: c.domains.length > 0 ? c.domains.join(' / ') : '主动提醒候选',
      detail: c.reason_codes.join('、'),
      confidence: null,
    });
  }
  return items.slice(0, 3);
}

/* ---------------- 各模块卡片 ---------------- */

function NowStackCard({ data }: { data: OverviewData }) {
  const unavailable: string[] = [];
  if (data.decision === null) unavailable.push('决策分析');
  if (data.proactive === null) unavailable.push('主动提醒');

  return (
    <section className="card" aria-labelledby="now-stack-title">
      <h2 id="now-stack-title" className="font-semibold">
        现在最重要
      </h2>
      <p className="mt-0.5 text-sm text-muted">最多三项：未结案决策与高重要主动提醒</p>
      <div className="mt-3">
        {unavailable.length === 2 ? (
          <StatePanel
            variant="partial"
            title="Now Stack 暂不可用"
            unavailableAuthorities={unavailable}
          />
        ) : (
          <NowStackBody data={data} unavailable={unavailable} />
        )}
      </div>
    </section>
  );
}

function NowStackBody({ data, unavailable }: { data: OverviewData; unavailable: string[] }) {
  const items = buildNowStack(data);
  return (
    <div className="section-stack">
      {unavailable.length > 0 ? (
        <StatePanel
          variant="partial"
          title="部分来源暂不可用"
          unavailableAuthorities={unavailable}
        />
      ) : null}
      {items.length === 0 && unavailable.length === 0 ? (
        <StatePanel
          variant="empty"
          title="暂无需要立即关注的事项"
          description="当前没有未确认的决策建议，也没有达到高重要阈值的主动提醒。"
          nextStep="可前往决策中心查看全部待决策事项。"
        />
      ) : (
        <ol className="section-stack">
          {items.map((item, index) => (
            <li
              key={`${item.authority}-${item.id}`}
              className="flex items-start gap-3 rounded-lg border border-line bg-surface p-3"
            >
              <span
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary-soft text-sm font-semibold text-primary"
                aria-hidden="true"
              >
                {index + 1}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium">{item.title}</span>
                  <AuthorityBadge authority={item.authority} />
                  {item.confirmationState !== undefined ? (
                    <ConfirmationStateBadge state={item.confirmationState} />
                  ) : null}
                  {item.expiresAt ? (
                    <span className="badge border-line bg-panel text-uncertainty">
                      <IconClock className="h-3.5 w-3.5" />
                      到期 {fmtTime(item.expiresAt)}
                    </span>
                  ) : null}
                </div>
                <p className="mt-1 break-words text-sm text-muted">
                  <span className="font-mono">{shortId(item.id)}</span>
                  {item.detail ? ` · ${item.detail}` : ''}
                  {item.confidence !== null ? ` · 置信度 ${fmtConfidence(item.confidence)}` : ''}
                </p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function GoalsCard({ personal }: { personal: OverviewData['personal'] }) {
  if (personal === null) {
    return (
      <StatePanel
        variant="partial"
        title="目标与约束暂不可用"
        unavailableAuthorities={['个人状态']}
      />
    );
  }
  const entries = Object.entries(personal.domains).sort((a, b) => b[1] - a[1]).slice(0, 5);
  return (
    <section className="card" aria-labelledby="goals-title">
      <h2 id="goals-title" className="font-semibold">
        当前目标与约束
      </h2>
      <p className="mt-0.5 text-sm text-muted">领域事实分布（前 5）</p>
      {entries.length === 0 ? (
        <p className="mt-3 text-sm text-muted">当前快照没有可用的领域事实。</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {entries.map(([domain, count]) => (
            <li key={domain} className="flex items-center justify-between gap-2 text-sm">
              <span className="truncate">{domain}</span>
              <span className="badge border-line bg-surface text-muted">{fmtNumber(count)} 条</span>
            </li>
          ))}
        </ul>
      )}
      <p className="mt-3 text-xs text-muted">
        快照 {personal.snapshot_id ? shortId(personal.snapshot_id) : '未绑定'} · 共{' '}
        {fmtNumber(personal.total_available)} 条有效事实
      </p>
    </section>
  );
}

function ChangesCard({ personal }: { personal: OverviewData['personal'] }) {
  if (personal === null) {
    return (
      <StatePanel
        variant="partial"
        title="变化与风险暂不可用"
        unavailableAuthorities={['个人状态']}
      />
    );
  }
  const entries = Object.entries(personal.status_counts).sort((a, b) => b[1] - a[1]);
  return (
    <section className="card" aria-labelledby="changes-title">
      <h2 id="changes-title" className="font-semibold">
        主要变化与风险
      </h2>
      <p className="mt-0.5 text-sm text-muted">事实状态分布</p>
      {entries.length === 0 ? (
        <p className="mt-3 text-sm text-muted">当前快照没有状态统计。</p>
      ) : (
        <ul className="mt-3 flex flex-wrap gap-2">
          {entries.map(([status, count]) => (
            <li key={status} className="flex items-center gap-1.5">
              <LifecycleBadge status={status} />
              <span className="text-sm text-muted">{fmtNumber(count)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function DecisionQueueCard({ decision }: { decision: OverviewData['decision'] }) {
  if (decision === null) {
    return (
      <StatePanel
        variant="partial"
        title="决策队列暂不可用"
        unavailableAuthorities={['决策分析']}
      />
    );
  }
  const queueEntries = Object.entries(decision.queue);
  return (
    <section className="card" aria-labelledby="decision-queue-title">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="decision-queue-title" className="font-semibold">
          待决策事项
        </h2>
        <span className="text-sm text-muted">共 {fmtNumber(decision.total_available)} 条</span>
      </div>
      {queueEntries.length > 0 ? (
        <ul className="mt-3 flex flex-wrap gap-2">
          {queueEntries.map(([state, count]) => (
            <li key={state} className="flex items-center gap-1.5">
              <ConfirmationStateBadge state={state} />
              <span className="text-sm text-muted">{fmtNumber(count)}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {decision.items.length === 0 ? (
        <p className="mt-3 text-sm text-muted">当前没有待决策事项。</p>
      ) : (
        <ul className="section-stack mt-3">
          {decision.items.slice(0, 3).map((item, index) => (
            <li
              key={item.recommendation_id ?? `decision-${index}`}
              className="rounded-lg border border-line bg-surface p-3"
            >
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-mono text-ink">
                  {item.recommendation_id ? shortId(item.recommendation_id) : '（无 ID）'}
                </span>
                {item.domain ? <span className="badge border-line bg-panel text-muted">{item.domain}</span> : null}
                {item.recommendation_kind ? (
                  <span className="badge border-line bg-panel text-muted">{item.recommendation_kind}</span>
                ) : null}
                <ConfirmationStateBadge state={item.confirmation_state} />
              </div>
              <p className="mt-1.5 text-sm text-muted">
                时间窗 {item.horizon ?? '—'} · 置信度 {fmtConfidence(item.confidence)} · 确认状态{' '}
                {item.confirmation_state ?? '—'} · 到期 {fmtTime(item.expires_at)}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ProactiveCard({ proactive }: { proactive: OverviewData['proactive'] }) {
  if (proactive === null) {
    return (
      <StatePanel
        variant="partial"
        title="主动提醒暂不可用"
        unavailableAuthorities={['主动提醒']}
      />
    );
  }
  return (
    <section className="card" aria-labelledby="proactive-title">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="proactive-title" className="font-semibold">
          主动提醒
        </h2>
        <span className="text-sm text-muted">{fmtNumber(proactive.total_available)} 条候选</span>
      </div>
      {proactive.items.length === 0 ? (
        <p className="mt-3 text-sm text-muted">当前没有达到阈值的主动候选。</p>
      ) : (
        <ul className="section-stack mt-3">
          {proactive.items.slice(0, 3).map((c, index) => (
            <li
              key={c.candidate_id ?? `candidate-${index}`}
              className="rounded-lg border border-line bg-surface p-3"
            >
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-mono text-ink">
                  {c.candidate_id ? shortId(c.candidate_id) : '（无 ID）'}
                </span>
                {c.domains.map((d) => (
                  <span key={d} className="badge border-line bg-panel text-muted">
                    {d}
                  </span>
                ))}
              </div>
              <p className="mt-1.5 text-sm text-muted">
                到期 {fmtTime(c.expires_at)}
                {c.reason_codes.length > 0 ? ` · 触发：${c.reason_codes.join('、')}` : ''}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function ExternalCard({ external }: { external: OverviewData['external'] }) {
  if (external === null) {
    return (
      <StatePanel
        variant="partial"
        title="外部环境暂不可用"
        unavailableAuthorities={['外部环境']}
      />
    );
  }
  return (
    <section className="card" aria-labelledby="external-title">
      <h2 id="external-title" className="font-semibold">
        外部环境摘要
      </h2>
      <dl className="mt-3 grid grid-cols-3 gap-2 text-sm">
        <div>
          <dt className="text-muted">快照</dt>
          <dd className="mt-0.5 font-mono" title={external.snapshot_id ?? undefined}>
            {external.snapshot_id ? shortId(external.snapshot_id) : '未绑定'}
          </dd>
        </div>
        <div>
          <dt className="text-muted">来源数</dt>
          <dd className="mt-0.5">{fmtNumber(external.sources_count)}</dd>
        </div>
        <div>
          <dt className="text-muted">事实数</dt>
          <dd className="mt-0.5">{fmtNumber(external.facts_count)}</dd>
        </div>
      </dl>
      {/* spec §7.5：外部与个人事实必须明确隔离 */}
      <p className="mt-3 rounded-md border border-external bg-external-soft px-2 py-1.5 text-xs text-external">
        外部事实不会自动成为个人事实。
      </p>
    </section>
  );
}

function FreshnessFooter({ envelope }: { envelope: OverviewEnvelope }) {
  return (
    <footer className="card" aria-label="数据新鲜度">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
        <span className="inline-flex items-center gap-2">
          <span className="text-muted">Personal 数据</span>
          <FreshnessBadge asOf={envelope.freshness?.personal_as_of ?? null} />
        </span>
        <span className="text-muted">
          知识单元 {fmtNumber(envelope.data.knowledge?.unit_count ?? envelope.freshness?.knowledge_unit_count)}
        </span>
        <span className="text-muted">投影生成于 {fmtTime(envelope.generated_at)}</span>
      </div>
    </footer>
  );
}

/* ---------------- 页面 ---------------- */

export function OverviewPage() {
  const query = useOverview();

  if (query.isPending) {
    return (
      <div className="section-stack" aria-label="今日总览加载中">
        <StatePanel variant="loading" />
        <StatePanel variant="loading" />
        <StatePanel variant="loading" />
      </div>
    );
  }

  if (query.isError) {
    const err = query.error as ApiError;
    // network_error = 整个同源 API 不可达；与其余错误（http_*/invalid_json/schema_mismatch）
    // 区分为独立的 offline 态（D-37-03），而非笼统归为一种"加载失败"。
    return (
      <StatePanel
        variant={err.code === 'network_error' ? 'offline' : 'error'}
        title="今日总览加载失败"
        errorMessage={err.message}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const envelope = query.data;
  const { data } = envelope;

  return (
    <div className="section-stack">
      <h1 className="text-lg font-semibold">今日总览</h1>

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

      <NowStackCard data={data} />

      <div className="grid gap-4 md:grid-cols-2">
        <GoalsCard personal={data.personal} />
        <ChangesCard personal={data.personal} />
      </div>

      <DecisionQueueCard decision={data.decision} />

      <div className="grid gap-4 md:grid-cols-2">
        <ProactiveCard proactive={data.proactive} />
        <ExternalCard external={data.external} />
      </div>

      <FreshnessFooter envelope={envelope} />
    </div>
  );
}
