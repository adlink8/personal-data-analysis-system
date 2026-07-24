import { Link } from 'react-router-dom';
import type { ApiError } from '../../api/client';
import { useActionsRecent, useCalibrationOverview } from '../../api/hooks';
import type { ActionEffectivenessRecord, ActionItem, ActionOutcomeRecord } from '../../api/schemas';
import { CalibrationPanel } from '../../components/action/CalibrationPanel';
import { OutcomeTimeline } from '../../components/action/OutcomeTimeline';
import { shortId } from '../../components/authority/SnapshotChip';
import {
  ActionStateBadge,
  ConfirmationStateBadge,
  ExpiryText,
} from '../../components/decision/stateBadges';
import { StatePanel } from '../../components/feedback/StatePanel';
import { IconAlertTriangle, IconChevronRight } from '../../components/icons';
import { fmtNumber, fmtTime, fmtUnknown } from '../../utils/format';

/**
 * 行动与结果页（spec §7.4）：把决策从"语言建议"转换为可追踪的真实过程。
 * 顶部摘要条（total_available / shown / with_outcome / awaiting_outcome）；
 * 主视图每条推荐一个六节点 OutcomeTimeline + outcome 展开区 + effectiveness（非因果标注）；
 * 底部 CalibrationPanel（/ui/calibration/overview）。
 * loading / empty / partial / error 全走 StatePanel；单条 error 只降级该条。
 * 写入约束：记录结果链到 /sessions/new?intent=observe&from=/actions，会话链严格线性不能跳段，
 * 本页不新增任何写入路径。
 */

/* ---------------- outcome 展开区 ---------------- */

// outcome 真实字段不确定：按观察记录常用键尽力渲染，缺失显"未提供"；其余键原样透传
const OUTCOME_FIELDS: ReadonlyArray<{ key: string; label: string; kind?: 'time' }> = [
  { key: 'completion', label: '实际完成' },
  { key: 'observed_value', label: '实际观测值' },
  { key: 'actual_time_minutes', label: '实际耗时（分钟）' },
  { key: 'actual_cost', label: '实际成本' },
  { key: 'quality', label: '质量自评' },
  { key: 'satisfaction', label: '满意度' },
  { key: 'side_effects', label: '未预期副作用' },
  { key: 'regret', label: '后悔度' },
  { key: 'confounders', label: '混杂因素' },
  { key: 'source', label: '观察来源' },
  { key: 'observed_at', label: '观察时间', kind: 'time' },
];

function fmtOutcomeValue(value: unknown, kind?: 'time'): string {
  if (value === null || value === undefined || value === '') return '未提供';
  if (Array.isArray(value)) {
    return value.length === 0 ? '未提供' : value.map((item) => fmtUnknown(item, 40)).join('、');
  }
  if (kind === 'time') return fmtTime(String(value));
  return fmtUnknown(value);
}

/** 透传字段（已知键以外）渲染为 key=value 徽标，完整值放 title */
function ExtraFieldBadges({ record, exclude }: { record: Record<string, unknown>; exclude: ReadonlyArray<string> }) {
  const extraKeys = Object.keys(record).filter(
    (key) => !exclude.includes(key) && record[key] !== null && record[key] !== undefined,
  );
  if (extraKeys.length === 0) return null;
  return (
    <p className="flex flex-wrap gap-1.5">
      {extraKeys.map((key) => (
        <span key={key} className="badge border-line bg-surface font-mono text-xs text-muted" title={fmtUnknown(record[key], 500)}>
          {key}={fmtUnknown(record[key], 32)}
        </span>
      ))}
    </p>
  );
}

function OutcomeRecordView({ record, index }: { record: ActionOutcomeRecord; index: number }) {
  const outcomeId = typeof record['outcome_id'] === 'string' ? (record['outcome_id'] as string) : null;
  return (
    <div className="section-stack rounded-lg border border-line bg-panel p-3">
      <p className="text-xs text-muted">
        结果 #{index + 1}
        {outcomeId ? (
          <>
            {' · '}
            <span className="font-mono break-all" title={outcomeId}>
              {shortId(outcomeId, 24)}
            </span>
          </>
        ) : null}
      </p>
      <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
        {OUTCOME_FIELDS.map((field) => (
          <div key={field.key} className="break-words">
            <dt className="inline text-muted">{field.label}：</dt>
            <dd className="inline">{fmtOutcomeValue(record[field.key], field.kind)}</dd>
          </div>
        ))}
      </dl>
      <ExtraFieldBadges record={record} exclude={OUTCOME_FIELDS.map((field) => field.key)} />
    </div>
  );
}

function EffectivenessList({ records }: { records: ActionEffectivenessRecord[] }) {
  const allNonCausal = records.every((record) => record.causal_claim === false);
  return (
    <div className="section-stack">
      {allNonCausal ? (
        // spec §7.3/§7.4：causal_claim==false 必须显著标注
        <p
          className="flex items-start gap-1.5 rounded-lg border border-uncertainty bg-uncertainty-soft p-3 text-sm font-medium text-uncertainty"
          role="note"
        >
          <IconAlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          非因果评估：结果不证明建议导致了结果。
        </p>
      ) : null}
      {records.map((record, index) => (
        <div key={index} className="section-stack rounded-lg border border-line bg-panel p-3">
          <p className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-muted">效果评估 #{index + 1}</span>
            {record.verdict ? (
              <span className="badge border-line bg-surface text-ink">{record.verdict}</span>
            ) : (
              <span className="text-muted">verdict 未提供</span>
            )}
            {record.causal_claim === false ? (
              <span className="badge border-uncertainty bg-uncertainty-soft text-uncertainty">
                <IconAlertTriangle className="h-3.5 w-3.5" />
                非因果
              </span>
            ) : null}
          </p>
          <ExtraFieldBadges record={record} exclude={['verdict', 'causal_claim']} />
        </div>
      ))}
    </div>
  );
}

/* ---------------- 单条推荐卡 ---------------- */

function ActionItemCard({ item }: { item: ActionItem }) {
  const rid = item.recommendation_id ?? '';
  return (
    <article className="card section-stack" aria-label={rid ? `行动时间线 ${rid}` : '行动时间线'}>
      <header className="flex flex-wrap items-center gap-2">
        {rid ? (
          <Link
            to={`/decisions/${encodeURIComponent(rid)}`}
            className="font-mono text-sm font-medium text-primary transition-colors hover:underline focus:outline-none focus:ring-2 focus:ring-primary"
            title={`完整 ID：${rid}（点击打开决策工作区）`}
          >
            {shortId(rid)}
          </Link>
        ) : (
          <span className="font-mono text-sm text-muted">（无 recommendation_id）</span>
        )}
        <span className="badge border-line bg-panel text-muted">{item.domain ?? '未提供'}</span>
        <span className="badge border-candidate bg-candidate-soft text-candidate">
          {item.recommendation_kind ?? '未提供'}
        </span>
        <ConfirmationStateBadge state={item.confirmation_state} />
        <ActionStateBadge state={item.action_state} />
        <ExpiryText expiresAt={item.expires_at} />
      </header>

      {item.error ? (
        // 单条组装失败只降级该条，不拖垮整页
        <StatePanel
          variant="partial"
          title="该条组装失败"
          description={`后端返回错误：${item.error}（其余条目不受影响）`}
        />
      ) : (
        <>
          <OutcomeTimeline stages={item.timeline} />

          <details className="rounded-lg border border-line bg-surface">
            <summary className="cursor-pointer px-3 py-2 text-sm font-medium transition-colors hover:bg-panel focus:outline-none focus:ring-2 focus:ring-primary">
              结果与效果评估（结果 {item.outcomes.length} 条 / 评估 {item.effectiveness.length} 条）
            </summary>
            <div className="section-stack border-t border-line p-3">
              {/* spec §7.4 硬性提示 */}
              <p className="flex items-center gap-1.5 text-xs text-uncertainty">
                <IconAlertTriangle className="h-3.5 w-3.5 shrink-0" />
                结果记录不自动证明建议导致了结果。
              </p>
              {item.outcomes.length === 0 ? (
                <p className="text-sm text-muted">尚未记录结果：行动完成后的真实观察会显示在这里。</p>
              ) : (
                item.outcomes.map((record, index) => <OutcomeRecordView key={index} record={record} index={index} />)
              )}
              {item.effectiveness.length > 0 ? <EffectivenessList records={item.effectiveness} /> : null}
            </div>
          </details>

          <p className="flex flex-wrap items-center gap-2 text-sm">
            <Link
              to="/sessions/new?intent=observe&from=/actions"
              className="inline-flex items-center gap-1.5 rounded-md border border-primary bg-primary-soft px-3 py-1.5 text-sm font-medium text-primary transition-colors hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <IconChevronRight className="h-4 w-4" />
              记录结果
            </Link>
            <span className="text-xs text-muted">经 Guarded 会话链逐跳推进，每跳 exact preview + 显式确认。</span>
          </p>
        </>
      )}
    </article>
  );
}

/* ---------------- 行动与结果区 ---------------- */

function ActionsRecentSection() {
  const query = useActionsRecent();

  if (query.isPending) {
    return (
      <div className="section-stack" aria-label="行动与结果加载中">
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
        title="行动与结果加载失败"
        errorMessage={err.message}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const envelope = query.data;
  const { data } = envelope;
  const total = data.total_available ?? 0;

  return (
    <section className="section-stack" aria-labelledby="actions-recent-title">
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

      <div className="card">
        <div className="flex flex-wrap items-center gap-2">
          <h2 id="actions-recent-title" className="font-semibold">
            最近行动
          </h2>
          <span className="badge border-line bg-panel text-muted">共 {fmtNumber(data.total_available)} 条</span>
          <span className="badge border-line bg-panel text-muted">本次展示 {fmtNumber(data.shown)} 条</span>
          <span className="badge border-verified bg-verified-soft text-verified">
            已有结果 {fmtNumber(data.with_outcome)} 条
          </span>
          <span className="badge border-uncertainty bg-uncertainty-soft text-uncertainty">
            等待结果 {fmtNumber(data.awaiting_outcome)} 条
          </span>
        </div>
        <p className="mt-2 text-xs text-muted">投影生成于 {fmtTime(envelope.generated_at)}（每分钟自动刷新）</p>
      </div>

      {total === 0 && data.items.length === 0 ? (
        <StatePanel
          variant="empty"
          title="当前没有行动与结果记录"
          description="还没有进入行动阶段的建议：接受建议并开始行动后，六阶段时间线会显示在这里。"
          nextStep="可从顶栏「新建决策」发起一个 Guarded 决策会话，或先到决策中心查看待确认建议。"
        />
      ) : (
        data.items.map((item, index) => (
          <ActionItemCard key={item.recommendation_id ?? `item-${index}`} item={item} />
        ))
      )}
    </section>
  );
}

/* ---------------- 校准区 ---------------- */

function CalibrationSection() {
  const query = useCalibrationOverview();

  if (query.isPending) {
    return <StatePanel variant="loading" />;
  }

  if (query.isError) {
    const err = query.error as ApiError;
    return (
      <StatePanel
        variant="error"
        title="校准总览加载失败"
        errorMessage={err.message}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const envelope = query.data;
  return (
    <div className="section-stack">
      {envelope.partial || envelope.limitations.length > 0 ? (
        <div className="card border-uncertainty bg-uncertainty-soft" role="status">
          <p className="flex items-center gap-2 text-sm font-medium text-uncertainty">
            <IconAlertTriangle />
            校准投影为部分可用
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
      <CalibrationPanel data={envelope.data} />
    </div>
  );
}

/* ---------------- 页面 ---------------- */

export function ActionsPage() {
  return (
    <div className="section-stack">
      <header className="card">
        <h1 className="text-lg font-semibold">行动与结果</h1>
        <p className="mt-2 text-sm text-muted">
          每条推荐的 建议 → 决策 → 行动开始 → 行动完成 → 结果 → 效果评估 六阶段纵向时间线，把决策从
          &ldquo;语言建议&rdquo;转换为可追踪的真实过程。
        </p>
        <p
          className="mt-2 flex items-start gap-1.5 rounded-lg border border-uncertainty bg-uncertainty-soft p-3 text-sm text-uncertainty"
          role="note"
        >
          <IconAlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          记录结果需经会话链逐步推进到 observe（confirm → … → action_complete → observe），不能跳段；
          结果记录不自动证明建议导致了结果。
        </p>
      </header>

      <ActionsRecentSection />
      <CalibrationSection />
    </div>
  );
}
