import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import type { ApiError } from '../../api/client';
import type { EvidenceReferenceInput } from '../../api/hooks';
import { useDecisionWorkspace } from '../../api/hooks';
import type {
  DecisionWorkspaceEnvelope,
  HistoryEvent,
  RecommendationDetail,
  SupportEntry,
  TypedRecord,
} from '../../api/schemas';
import { shortId, SnapshotChip } from '../../components/authority/SnapshotChip';
import {
  ActionStateBadge,
  ConfirmationStateBadge,
  ExpiryText,
} from '../../components/decision/stateBadges';
import { EvidenceDrawer } from '../../components/evidence/EvidenceDrawer';
import { StatePanel } from '../../components/feedback/StatePanel';
import {
  IconAlertTriangle,
  IconArrowLeft,
  IconCheckCircle,
  IconChevronRight,
  IconInfo,
  IconSearch,
  IconSparkles,
} from '../../components/icons';
import { fmtConfidence, fmtNumber, fmtTime } from '../../utils/format';

/**
 * 决策工作区（spec §7.3）：头部 + 三栏（决策条件 / 方案与证据 / 建议与限制）
 * + 底部标签页（历史 / 结果 / 效果）。
 * 节级降级：某一 Authority 失败只降级该节（authorities 四键
 * recommendation/history/outcomes/effectiveness），不拖垮整页。
 * causal_claim==false 的效果评估必须显著标注"非因果评估"。
 */

type TabKey = 'history' | 'outcomes' | 'effectiveness';

const TABS: ReadonlyArray<{ key: TabKey; label: string }> = [
  { key: 'history', label: '历史' },
  { key: 'outcomes', label: '结果' },
  { key: 'effectiveness', label: '效果' },
];

function errorAuthorities(envelope: DecisionWorkspaceEnvelope): Record<string, boolean> {
  const result: Record<string, boolean> = {};
  for (const [name, value] of Object.entries(envelope.authorities)) {
    result[name] = value === 'error';
  }
  return result;
}

/** 从 support[] 尽力提取 case_id（透传字段，可能没有）；找不到返回 null，绝不臆造 */
function deriveCaseId(recommendation: RecommendationDetail): string | null {
  for (const entry of recommendation.support) {
    const candidate = (entry as Record<string, unknown>)['case_id'];
    if (typeof candidate === 'string' && candidate) return candidate;
  }
  return null;
}

/**
 * 决策建议的稳定证据引用（Phase 37 Plan 03，EVID-01）：只用工作区已经持有的
 * recommendation_id + recommendation_checksum + snapshot_id 组装（support/checksum
 * 的全链证据读取交给服务端 evidence_resolve.get 内部复用 recommendations.get 的既有
 * 校验，本页不新增、不绕过任何 guarded session/action/outcome/prepare/confirm/execute
 * 流程）。三者任一缺失一律返回 null，不构造伪 evidence。
 */
function decisionEvidenceReference(recommendation: RecommendationDetail): EvidenceReferenceInput | null {
  if (!recommendation.recommendation_id || !recommendation.recommendation_checksum || !recommendation.snapshot_id) {
    return null;
  }
  return {
    subjectType: 'decision',
    stableId: recommendation.recommendation_id,
    snapshotId: recommendation.snapshot_id,
    checksum: recommendation.recommendation_checksum,
  };
}

/* ---------------- 三栏 ---------------- */

function FieldRow({ label, value, mono }: { label: string; value: string | null | undefined; mono?: boolean }) {
  return (
    <div className="break-words">
      <dt className="inline text-muted">{label}：</dt>
      <dd className={`inline ${mono ? 'font-mono text-xs' : ''}`}>{value ?? '未提供'}</dd>
    </div>
  );
}

function ConditionsColumn({ recommendation }: { recommendation: RecommendationDetail }) {
  return (
    <section className="card h-full" aria-labelledby="ws-conditions-title">
      <h2 id="ws-conditions-title" className="font-semibold">
        决策条件
      </h2>
      <dl className="mt-3 space-y-2 text-sm">
        <FieldRow label="policy_id" value={recommendation.policy_id} mono />
        <FieldRow label="时间窗口" value={recommendation.horizon} />
        <FieldRow label="置信度" value={fmtConfidence(recommendation.confidence)} />
        <FieldRow
          label="不确定性"
          value={
            recommendation.uncertainty === null || recommendation.uncertainty === undefined
              ? null
              : String(recommendation.uncertainty)
          }
        />
        <FieldRow label="主体" value={recommendation.subject} />
      </dl>
      <div className="mt-3">
        <h3 className="text-sm font-medium">rationale_codes</h3>
        {recommendation.rationale_codes.length === 0 ? (
          <p className="mt-1 text-sm text-muted">未提供</p>
        ) : (
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {recommendation.rationale_codes.map((code) => (
              <li key={code} className="badge border-line bg-panel font-mono text-xs text-muted">
                {code}
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function SupportRow({ entry }: { entry: SupportEntry }) {
  return (
    <li className="rounded-lg border border-line bg-surface p-2.5 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="badge border-line bg-panel text-muted">{entry.cognitive_type ?? '未提供'}</span>
        {entry.evidence_status ? (
          <span className="badge border-line bg-panel text-muted">{entry.evidence_status}</span>
        ) : null}
        <span className="font-mono text-xs text-muted" title={entry.authority_id ?? undefined}>
          {entry.authority_id ?? '未提供'}
        </span>
      </div>
      <dl className="mt-1.5 space-y-1 text-xs text-muted">
        <div className="break-all">
          <dt className="inline">record_id：</dt>
          <dd className="inline font-mono" title={entry.record_id ?? undefined}>
            {entry.record_id ? shortId(entry.record_id, 28) : '未提供'}
          </dd>
        </div>
        <div className="break-all">
          <dt className="inline">source_run_id：</dt>
          <dd className="inline font-mono" title={entry.source_run_id ?? undefined}>
            {entry.source_run_id ? shortId(entry.source_run_id, 28) : '未提供'}
          </dd>
        </div>
      </dl>
    </li>
  );
}

function EvidenceColumn({
  recommendation,
  linkedAnalysisRunId,
}: {
  recommendation: RecommendationDetail;
  linkedAnalysisRunId: string | null;
}) {
  return (
    <section className="card h-full" aria-labelledby="ws-evidence-title">
      <h2 id="ws-evidence-title" className="font-semibold">
        方案与证据
      </h2>
      {linkedAnalysisRunId ? (
        <p className="mt-2 text-sm">
          <span className="badge border-candidate bg-candidate-soft text-candidate">
            <IconSparkles className="h-3.5 w-3.5" />
            关联分析 run
          </span>{' '}
          <span className="font-mono text-xs break-all" title={linkedAnalysisRunId}>
            {shortId(linkedAnalysisRunId, 28)}
          </span>
        </p>
      ) : null}
      {recommendation.support.length === 0 ? (
        // AbstentionPanel 风格（spec §8）：信息不足时给出拒绝/谨慎原因
        <div className="mt-3 rounded-lg border border-uncertainty bg-uncertainty-soft p-3" role="note">
          <p className="flex items-start gap-1.5 text-sm text-uncertainty">
            <IconAlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              缺少支撑证据：该建议当前没有关联的支撑证据记录，信息不足。
              请谨慎对待其置信度，必要时先补充证据再确认。
            </span>
          </p>
        </div>
      ) : (
        <ul className="section-stack mt-3">
          {recommendation.support.map((entry, index) => (
            <SupportRow key={entry.record_id ?? `support-${index}`} entry={entry} />
          ))}
        </ul>
      )}
    </section>
  );
}

function AdviceColumn({
  recommendation,
  limitations,
}: {
  recommendation: RecommendationDetail;
  limitations: string[];
}) {
  // 缺失信息说明：关键字段为空的如实列出
  const missing: string[] = [];
  if (!recommendation.run_id) missing.push('run_id');
  if (!recommendation.expires_at) missing.push('expires_at');
  if (!recommendation.uncertainty && recommendation.uncertainty !== 0) missing.push('uncertainty');
  if (recommendation.rationale_codes.length === 0) missing.push('rationale_codes');

  return (
    <section className="card h-full" aria-labelledby="ws-advice-title">
      <h2 id="ws-advice-title" className="font-semibold">
        建议与限制
      </h2>
      <p className="mt-3">
        <span className="badge border-candidate bg-candidate-soft text-candidate">
          <IconSparkles className="h-3.5 w-3.5" />
          建议候选：{recommendation.recommendation_kind ?? '未提供'}
        </span>
      </p>
      {limitations.length > 0 ? (
        <div className="mt-3">
          <h3 className="text-sm font-medium">限制</h3>
          <ul className="mt-1 list-disc pl-5 text-sm text-muted">
            {limitations.map((limitation, i) => (
              <li key={i}>{limitation}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="mt-3">
        <h3 className="text-sm font-medium">缺失信息</h3>
        {missing.length === 0 ? (
          <p className="mt-1 flex items-center gap-1 text-sm text-verified">
            <IconCheckCircle className="h-3.5 w-3.5" />
            关键字段齐全
          </p>
        ) : (
          <p className="mt-1 text-sm text-muted">
            以下字段未提供：<span className="font-mono text-xs">{missing.join('、')}</span>
          </p>
        )}
      </div>
    </section>
  );
}

/* ---------------- DEC-01 决策比较（Phase 38） ---------------- */

function ComparisonField({ label, value, note }: { label: string; value: string | null; note?: string }) {
  return (
    <div className="break-words">
      <dt className="text-xs font-medium text-muted">{label}</dt>
      <dd className="mt-0.5 text-sm">{value ?? '未提供'}</dd>
      {note ? <p className="mt-0.5 text-xs text-muted">{note}</p> : null}
    </div>
  );
}

function ComparisonListField({ label, items, note }: { label: string; items: string[]; note?: string }) {
  return (
    <div className="break-words">
      <dt className="text-xs font-medium text-muted">{label}</dt>
      {items.length === 0 ? (
        <dd className="mt-0.5 text-sm text-muted">未提供</dd>
      ) : (
        <dd className="mt-0.5">
          <ul className="list-disc pl-5 text-sm">
            {items.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </dd>
      )}
      {note ? <p className="mt-0.5 text-xs text-muted">{note}</p> : null}
    </div>
  );
}

/**
 * DEC-01 完整决策比较（spec：问题/目标/硬约束/风险预算/候选方案/不行动基线/
 * 成本/机会成本/假设/反面证据/停止条件/缺失信息/限制），不得以单一人生分数
 * 替代解释（D-38-01）。当前 decision_workspace.get 的真实数据模型只包含单一
 * recommendation（无多候选比较、无 goal/no_action_baseline/risk_budget/
 * stop_conditions/opportunity_cost 字段，见 schemas.ts 顶部注释），因此以下
 * 逐项如实标注"未提供"而非臆造——一旦后端投影补齐，无需改动渲染逻辑。
 */
function DecisionComparisonSection({ recommendation }: { recommendation: RecommendationDetail }) {
  const isProjectDomain = recommendation.domain === 'project';
  return (
    <section className="card" aria-labelledby="ws-comparison-title">
      <h2 id="ws-comparison-title" className="font-semibold">
        决策比较（DEC-01）
      </h2>
      <p className="mt-1 text-xs text-muted">
        Recommendation 是候选，不是事实或用户决定；以下逐项如实标注"未提供"，不用单一分数替代解释。
      </p>
      <dl className="mt-3 grid gap-x-6 gap-y-4 sm:grid-cols-2">
        <ComparisonField
          label="决策问题"
          value={null}
          note="Projection 未提供独立的决策问题陈述；相关信息见「决策条件」列的主体/领域/范围。"
        />
        <ComparisonField label="目标（goal）" value={null} note="Projection 当前未暴露决策目标字段。" />
        <ComparisonListField label="硬约束与成本（costs_constraints）" items={recommendation.costs_constraints} />
        <ComparisonField
          label="风险预算（risk_budget）"
          value={isProjectDomain ? 'low' : null}
          note={
            isProjectDomain
              ? 'project 域的受控会话固定为 low（系统级不变量，唯一开放路径）。'
              : '仅 project 域的受控会话固定风险预算为 low；当前建议不属于 project 域，无法确定风险预算。'
          }
        />
        <div className="break-words sm:col-span-2">
          <dt className="text-xs font-medium text-muted">候选方案</dt>
          <dd className="mt-0.5 text-sm">
            {recommendation.recommendation_kind ?? '未提供'}
            {recommendation.target ? `　目标对象：${recommendation.target}` : ''}
            {recommendation.expected_benefit ? `　预期收益：${recommendation.expected_benefit}` : ''}
          </dd>
          <p className="mt-0.5 text-xs text-muted">
            Projection 当前只提供该单一建议候选，无法展示与其他候选方案（如 A/B/C）的结构化比较表。
          </p>
        </div>
        <ComparisonField label="不行动基线（no_action_baseline）" value={null} note="Projection 当前未暴露不行动基线。" />
        <ComparisonField label="机会成本（opportunity_cost）" value={null} note="Projection 当前未暴露机会成本。" />
        <ComparisonListField label="假设（assumptions）" items={recommendation.assumptions} />
        <ComparisonListField label="反面证据（contraindications）" items={recommendation.contraindications} />
        <ComparisonField label="停止条件（stop_conditions）" value={null} note="Projection 当前未暴露停止条件。" />
      </dl>
    </section>
  );
}

/* ---------------- 标签页 ---------------- */

function HistoryPanel({ events }: { events: HistoryEvent[] }) {
  if (events.length === 0) {
    return (
      <StatePanel
        variant="empty"
        title="暂无历史事件"
        description="该建议的事件链为空。"
      />
    );
  }
  return (
    <>
      <p className="mb-3 flex items-center gap-1.5 text-xs text-muted">
        <IconInfo className="h-3.5 w-3.5 shrink-0" />
        recommendations.history 不暴露事件时间戳 / status，仅展示链上校验字段。
      </p>
      <ol className="section-stack">
        {events.map((event, index) => (
          <li
            key={event.event_id ?? `event-${index}`}
            className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-line bg-surface p-3 text-sm"
          >
            <span className="font-mono text-xs text-muted">#{fmtNumber(event.sequence)}</span>
            <span className="badge border-line bg-panel text-ink">{event.event_type ?? '未提供'}</span>
            <span className="font-mono text-xs break-all" title={event.event_id ?? undefined}>
              事件 {event.event_id ? shortId(event.event_id, 20) : '未提供'}
            </span>
            <span className="font-mono text-xs text-muted break-all" title={event.payload_checksum ?? undefined}>
              校验 {event.payload_checksum ? shortId(event.payload_checksum, 16) : '未提供'}
            </span>
          </li>
        ))}
      </ol>
    </>
  );
}

function TypedRecordList({ records, idKey }: { records: TypedRecord[]; idKey: 'outcome_id' | 'assessment_id' }) {
  return (
    <ul className="section-stack">
      {records.map((record, index) => (
        <li key={(record[idKey] as string | undefined) ?? `record-${index}`} className="rounded-lg border border-line bg-surface p-3 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs" title={(record[idKey] as string | undefined) ?? undefined}>
              {typeof record[idKey] === 'string' ? shortId(record[idKey] as string, 24) : '（无 ID）'}
            </span>
            {record.record_type ? <span className="badge border-line bg-panel text-muted">{record.record_type}</span> : null}
            {record.verdict ? <span className="badge border-line bg-panel text-ink">{record.verdict}</span> : null}
            {record.adherence_status ? (
              <span className="badge border-line bg-panel text-muted">{record.adherence_status}</span>
            ) : null}
          </div>
          <dl className="mt-2 grid gap-x-6 gap-y-1 text-xs text-muted sm:grid-cols-2">
            <div>
              <dt className="inline">metric：</dt>
              <dd className="inline font-mono">{record.metric === null || record.metric === undefined ? '未提供' : String(record.metric)}</dd>
            </div>
            <div>
              <dt className="inline">unit：</dt>
              <dd className="inline">{record.unit ?? '未提供'}</dd>
            </div>
            <div>
              <dt className="inline">rule：</dt>
              <dd className="inline font-mono">
                {record.rule_id ?? '未提供'}
                {record.rule_version ? `@${record.rule_version}` : ''}
              </dd>
            </div>
            <div>
              <dt className="inline">uncertainty：</dt>
              <dd className="inline">
                {record.uncertainty === null || record.uncertainty === undefined ? '未提供' : String(record.uncertainty)}
              </dd>
            </div>
          </dl>
        </li>
      ))}
    </ul>
  );
}

function OutcomesPanel({ outcomes }: { outcomes: TypedRecord[] }) {
  if (outcomes.length === 0) {
    return (
      <StatePanel
        variant="empty"
        title="尚未记录 Outcome"
        description="行动完成后的真实结果会记录在这里。"
        nextStep="可通过会话推进视图的 observe 步骤记录结果观察。"
      />
    );
  }
  return (
    <>
      <p className="mb-3 flex items-center gap-1.5 text-xs text-uncertainty">
        <IconAlertTriangle className="h-3.5 w-3.5 shrink-0" />
        结果记录不自动证明建议导致了结果。
      </p>
      <TypedRecordList records={outcomes} idKey="outcome_id" />
    </>
  );
}

function EffectivenessPanel({ effectiveness }: { effectiveness: TypedRecord[] }) {
  if (effectiveness.length === 0) {
    return (
      <StatePanel
        variant="empty"
        title="尚未进行效果评估"
        description="校准规则运行后，非因果效果评估会显示在这里。"
      />
    );
  }
  const allNonCausal = effectiveness.every((record) => record.causal_claim === false);
  return (
    <>
      {allNonCausal ? (
        // spec §7.3：causal_claim==false 必须显著标注
        <div className="mb-3 rounded-lg border border-uncertainty bg-uncertainty-soft p-3" role="note">
          <p className="flex items-start gap-1.5 text-sm font-medium text-uncertainty">
            <IconAlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            非因果评估：结果不证明建议导致了结果。
          </p>
        </div>
      ) : null}
      <TypedRecordList records={effectiveness} idKey="assessment_id" />
    </>
  );
}

/* ---------------- 页面 ---------------- */

function WorkspaceBody({ envelope, recommendationId }: { envelope: DecisionWorkspaceEnvelope; recommendationId: string }) {
  const navigate = useNavigate();
  const [tab, setTab] = useState<TabKey>('history');
  const [openEvidence, setOpenEvidence] = useState<{ reference: EvidenceReferenceInput; label: string } | null>(null);
  const { data } = envelope;
  const authorityError = errorAuthorities(envelope);
  const recommendation = data.recommendation;

  if (!recommendation) {
    return (
      <StatePanel
        variant="partial"
        title="建议详情暂不可用"
        unavailableAuthorities={authorityError['recommendation'] ? ['决策分析 · recommendation'] : []}
        description={
          authorityError['recommendation']
            ? 'recommendation Authority 本次未返回数据。'
            : `未找到 recommendation_id 为 ${recommendationId} 的建议。`
        }
      />
    );
  }

  const caseId = deriveCaseId(recommendation);
  const evidenceReference = decisionEvidenceReference(recommendation);

  return (
    <>
      <header className="card">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="font-mono text-lg font-semibold break-all" title={`完整 ID：${recommendation.recommendation_id ?? recommendationId}`}>
            {shortId(recommendation.recommendation_id ?? recommendationId, 24)}
          </h1>
          <span className="badge border-line bg-panel text-muted">{recommendation.domain ?? '未提供'}</span>
          {recommendation.scope ? (
            <span className="badge border-line bg-panel text-muted">范围 {recommendation.scope}</span>
          ) : null}
          <ConfirmationStateBadge state={recommendation.confirmation_state} />
          <ActionStateBadge state={recommendation.action_state} />
          <SnapshotChip label="Personal" snapshotId={recommendation.snapshot_id ?? null} />
        </div>
        <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
          <span>决策工作区</span>
          <ExpiryText expiresAt={recommendation.expires_at} />
          <span>
            当前序号 <span className="font-mono">{fmtNumber(recommendation.current_sequence)}</span>
          </span>
          <span>投影生成于 {fmtTime(envelope.generated_at)}</span>
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() =>
              void navigate(
                `/sessions/new?intent=action&from=${encodeURIComponent(recommendationId)}${caseId ? `&case_id=${encodeURIComponent(caseId)}` : ''}`,
              )
            }
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-white transition-colors hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <IconChevronRight className="h-4 w-4" />
            记录行动/结果
          </button>
          {evidenceReference ? (
            <button
              type="button"
              onClick={() =>
                setOpenEvidence({
                  reference: evidenceReference,
                  label: `${recommendation.domain ?? ''} · ${recommendation.recommendation_kind ?? '决策建议'}`,
                })
              }
              className="inline-flex items-center gap-1.5 rounded-md border border-line bg-panel px-3 py-1.5 text-sm text-ink transition-colors hover:bg-surface focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <IconSearch className="h-4 w-4" />
              查看证据
            </button>
          ) : null}
          <p className="text-xs text-muted">
            决策确认写入 Pilot 权威案例；记录行动/结果需要编排会话与 case_id
            {caseId ? '（已从支撑证据预填）' : '（工作区投影未暴露，需手动输入，不臆造）'}。
          </p>
        </div>
      </header>

      <DecisionComparisonSection recommendation={recommendation} />

      <div className="grid gap-4 lg:grid-cols-3">
        <ConditionsColumn recommendation={recommendation} />
        <EvidenceColumn recommendation={recommendation} linkedAnalysisRunId={data.linked_analysis_run_id} />
        <AdviceColumn recommendation={recommendation} limitations={envelope.limitations} />
      </div>

      <section className="card" aria-label="历史、结果与效果">
        <div role="tablist" aria-label="工作区标签页" className="flex gap-1 border-b border-line">
          {TABS.map((item) => (
            <button
              key={item.key}
              type="button"
              role="tab"
              aria-selected={tab === item.key}
              onClick={() => setTab(item.key)}
              className={`rounded-t-md px-3 py-2 text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-primary ${
                tab === item.key ? 'bg-primary-soft font-medium text-primary' : 'text-muted hover:bg-surface'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>
        <div role="tabpanel" className="pt-4">
          {tab === 'history' ? (
            authorityError['history'] ? (
              <StatePanel variant="partial" title="历史暂不可用" unavailableAuthorities={['决策分析 · history']} />
            ) : (
              <HistoryPanel events={data.history} />
            )
          ) : null}
          {tab === 'outcomes' ? (
            authorityError['outcomes'] ? (
              <StatePanel variant="partial" title="结果暂不可用" unavailableAuthorities={['决策分析 · outcomes']} />
            ) : (
              <OutcomesPanel outcomes={data.outcomes} />
            )
          ) : null}
          {tab === 'effectiveness' ? (
            authorityError['effectiveness'] ? (
              <StatePanel variant="partial" title="效果暂不可用" unavailableAuthorities={['决策分析 · effectiveness']} />
            ) : (
              <EffectivenessPanel effectiveness={data.effectiveness} />
            )
          ) : null}
        </div>
      </section>

      {openEvidence ? (
        <EvidenceDrawer
          reference={openEvidence.reference}
          subjectLabel={openEvidence.label}
          onClose={() => setOpenEvidence(null)}
        />
      ) : null}
    </>
  );
}

export function DecisionWorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const query = useDecisionWorkspace(id);

  if (!id) {
    return (
      <StatePanel
        variant="empty"
        title="缺少 recommendation_id"
        description="工作区需要建议 ID 才能加载。"
        nextStep="返回决策中心选择一条建议。"
      />
    );
  }

  if (query.isPending) {
    return (
      <div className="section-stack" aria-label="决策工作区加载中">
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
        title="决策工作区加载失败"
        errorMessage={err.message}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const envelope = query.data;

  return (
    <div className="section-stack">
      <p>
        <Link
          to="/decisions"
          className="inline-flex items-center gap-1 text-sm text-primary transition-colors hover:underline focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <IconArrowLeft className="h-4 w-4" />
          返回决策中心
        </Link>
      </p>

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

      <WorkspaceBody envelope={envelope} recommendationId={id} />
    </div>
  );
}
