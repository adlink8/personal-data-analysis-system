import { useEffect, useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  deriveActorIdentityHash,
  newIdempotencyKey,
  NEXT_TRANSITION_BY_STATE,
  OrchestrationError,
  sessionExecute,
  sessionPreview,
  sessionResume,
  transitionMeta,
  nowIso,
  type OperationResult,
  type OrchestrationPreview,
  type SessionResume,
  type TransitionKey,
} from '../../api/orchestration';
import { shortId } from '../../components/authority/SnapshotChip';
import { ConfirmDrawer } from '../../components/decision/ConfirmDrawer';
import { DecisionStageStepper } from '../../components/decision/DecisionStageStepper';
import { NewSessionFlow } from '../../components/decision/NewSessionFlow';
import { StatePanel } from '../../components/feedback/StatePanel';
import { TypedRecoveryPanel } from '../../components/feedback/TypedRecoveryPanel';
import { IconAlertTriangle, IconArrowLeft, IconCheckCircle, IconChevronRight, IconInfo } from '../../components/icons';

/**
 * 会话推进视图（spec §5.3 / §12）：
 * GET /agent/session/resume 恢复会话 → 显示当前 state/sequence + DecisionStageStepper
 * → 仅合法下一跳可点 → 每跳先 preview（exact preview）再独立确认 execute。
 * 失败走 TypedRecoveryPanel，会话不中断（可 resume）；Replay 显示"已返回原事件，未重复写入"。
 * 硬性约束：不提供"一键完成全部阶段"入口。
 */

/* ---------------- 会话 state 词表 ---------------- */

const SESSION_STATE_LABELS: Record<string, string> = {
  confirmed: '已确认',
  generated: '已生成',
  published: '已发布',
  decided: '已决策',
  preregistered: '已预注册',
  action_started: '行动已开始',
  action_completed: '行动已完成',
  observed: '已记录结果',
  calibrated: '已校准',
};

/* ---------------- 各 transition 的 payload 表单规格 ---------------- */

interface FieldSpec {
  name: string;
  label: string;
  kind: 'text' | 'number' | 'select' | 'list' | 'fixed';
  required?: boolean;
  options?: ReadonlyArray<{ value: string; label: string }>;
  placeholder?: string;
  hint?: string;
  fixedValue?: string;
}

const PILOT_SEQUENCE_FIELD: FieldSpec = {
  name: 'pilot_expected_sequence',
  label: 'pilot_expected_sequence（Pilot 案例当前事件序号，乐观锁）',
  kind: 'number',
  required: true,
  placeholder: '例如 3',
};

const TRANSITION_FIELDS: Record<string, ReadonlyArray<FieldSpec>> = {
  generate: [],
  publish: [
    { name: 'run_id', label: 'run_id（分析运行 ID）', kind: 'text', required: true },
    { name: 'candidate_id', label: 'candidate_id（候选 ID）', kind: 'text', required: true },
    { name: 'selected_option_id', label: 'selected_option_id（选定方案 ID）', kind: 'text', required: true },
    { name: 'case_confirmation_event_id', label: 'case_confirmation_event_id（案例确认事件 ID）', kind: 'text', required: true },
  ],
  decide: [
    { name: 'case_id', label: 'case_id（Pilot 权威案例 ID）', kind: 'text', required: true },
    {
      name: 'decision',
      label: '决策',
      kind: 'select',
      required: true,
      options: [
        { value: 'accept', label: '接受（accept）' },
        { value: 'reject', label: '拒绝（reject）' },
        { value: 'defer', label: '延迟（defer）' },
      ],
    },
    { name: 'confirmed_case_checksum', label: 'confirmed_case_checksum（已核对案例 checksum）', kind: 'text', required: true },
    { name: 'reason_code', label: 'reason_code（理由代码）', kind: 'text', required: true, placeholder: '例如 user_confirmed' },
    PILOT_SEQUENCE_FIELD,
  ],
  preregister: [
    { name: 'case_id', label: 'case_id（Pilot 权威案例 ID）', kind: 'text', required: true },
    { name: 'metric', label: 'metric（度量指标）', kind: 'text', required: true, placeholder: '例如 weekly_hours' },
    { name: 'unit', label: 'unit（单位）', kind: 'text', required: true, placeholder: '例如 hours' },
    { name: 'baseline', label: 'baseline（基线值）', kind: 'number', required: true },
    { name: 'target', label: 'target（目标值）', kind: 'number', required: true },
    { name: 'direction', label: 'direction（方向）', kind: 'text', required: true, placeholder: '例如 higher_is_better' },
    { name: 'window_start', label: 'window_start（窗口开始，ISO 时间）', kind: 'text', required: true, placeholder: '2026-07-20T00:00:00Z' },
    { name: 'window_end', label: 'window_end（窗口结束，ISO 时间）', kind: 'text', required: true, placeholder: '2026-09-14T00:00:00Z' },
    { name: 'collection_source', label: 'collection_source（数据来源）', kind: 'text', required: true, placeholder: '例如 manual_log' },
    { name: 'estimated_time_minutes', label: 'estimated_time_minutes（预计耗时分钟）', kind: 'number' },
    { name: 'estimated_cost', label: 'estimated_cost（预计成本）', kind: 'number' },
    PILOT_SEQUENCE_FIELD,
  ],
  action_start: [
    { name: 'case_id', label: 'case_id（Pilot 权威案例 ID）', kind: 'text', required: true },
    { name: 'action_state', label: 'action_state（固定）', kind: 'fixed', fixedValue: 'started' },
    { name: 'description', label: 'description（行动描述）', kind: 'text', required: true },
    { name: 'operator', label: 'operator（操作者，默认 user）', kind: 'text', placeholder: 'user' },
    PILOT_SEQUENCE_FIELD,
  ],
  action_complete: [
    { name: 'case_id', label: 'case_id（Pilot 权威案例 ID）', kind: 'text', required: true },
    { name: 'action_state', label: 'action_state（固定）', kind: 'fixed', fixedValue: 'completed' },
    { name: 'description', label: 'description（完成内容描述）', kind: 'text', required: true },
    { name: 'operator', label: 'operator（操作者，默认 user）', kind: 'text', placeholder: 'user' },
    PILOT_SEQUENCE_FIELD,
  ],
  observe: [
    { name: 'case_id', label: 'case_id（Pilot 权威案例 ID）', kind: 'text', required: true },
    { name: 'observed_value', label: 'observed_value（实际观测值）', kind: 'number', required: true },
    { name: 'actual_time_minutes', label: 'actual_time_minutes（实际耗时分钟）', kind: 'number' },
    { name: 'actual_cost', label: 'actual_cost（实际成本）', kind: 'number' },
    { name: 'completion', label: 'completion（完成情况）', kind: 'text', placeholder: '例如 complete / partial' },
    { name: 'quality', label: 'quality（质量自评 0..1）', kind: 'number' },
    { name: 'satisfaction', label: 'satisfaction（满意度自评 0..1）', kind: 'number' },
    { name: 'side_effects', label: 'side_effects（未预期副作用，逗号分隔）', kind: 'list' },
    { name: 'regret', label: 'regret（后悔度 0..1，可空）', kind: 'number' },
    { name: 'confounders', label: 'confounders（混杂因素，逗号分隔）', kind: 'list' },
    { name: 'source', label: 'source（观察来源）', kind: 'text', placeholder: '例如 manual_log' },
    { name: 'observed_at', label: 'observed_at（观察时间，留空取当前时间）', kind: 'text', placeholder: '2026-07-19T10:00:00Z' },
    PILOT_SEQUENCE_FIELD,
  ],
  calibrate: [
    { name: 'protocol_id', label: 'protocol_id（校准协议 ID）', kind: 'text', required: true },
  ],
};

/** 表单值 → payload.input；返回错误文案或 payload */
function buildPayload(
  transition: TransitionKey,
  fields: ReadonlyArray<FieldSpec>,
  values: Record<string, string>,
): { error: string } | { payload: Record<string, unknown> } {
  if (transition === 'generate') {
    // generate 的 input 固定为空证据集（真实证据由服务端 generation runner 组装）
    return { payload: { personal_evidence: [], external_evidence: [] } };
  }
  const payload: Record<string, unknown> = {};
  for (const field of fields) {
    const raw = (values[field.name] ?? '').trim();
    if (field.kind === 'fixed') {
      payload[field.name] = field.fixedValue ?? '';
      continue;
    }
    if (field.required && !raw) return { error: `「${field.label}」必填` };
    if (!raw) {
      // 可空字段：observed_at 留空取当前时间；operator 默认 user；其余省略
      if (field.name === 'observed_at') payload[field.name] = nowIso();
      else if (field.name === 'operator') payload[field.name] = 'user';
      continue;
    }
    if (field.kind === 'number') {
      const parsed = Number.parseFloat(raw);
      if (Number.isNaN(parsed)) return { error: `「${field.label}」必须是数值` };
      payload[field.name] = parsed;
    } else if (field.kind === 'list') {
      payload[field.name] = raw.split(/[，,\n]/).map((item) => item.trim()).filter(Boolean);
    } else {
      payload[field.name] = raw;
    }
  }
  return { payload };
}

/* ---------------- manifest 摘要 ---------------- */

function ManifestCard({ manifest }: { manifest: Record<string, unknown> }) {
  const goal = typeof manifest['goal'] === 'string' ? (manifest['goal'] as string) : null;
  const constraints = Array.isArray(manifest['constraints'])
    ? (manifest['constraints'] as unknown[]).filter((item): item is string => typeof item === 'string')
    : [];
  const weights =
    manifest['weights'] && typeof manifest['weights'] === 'object'
      ? Object.entries(manifest['weights'] as Record<string, unknown>)
      : [];
  return (
    <section className="card" aria-labelledby="session-manifest-title">
      <h2 id="session-manifest-title" className="font-semibold">
        决策问题与边界
      </h2>
      <p className="mt-2 text-sm">{goal ?? '未提供'}</p>
      {constraints.length > 0 ? (
        <ul className="mt-2 list-disc pl-5 text-sm text-muted">
          {constraints.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}
      <div className="mt-2 flex flex-wrap gap-1.5">
        {weights.map(([key, value]) => (
          <span key={key} className="badge border-line bg-panel font-mono text-xs text-muted">
            {key}={String(value)}
          </span>
        ))}
        <span className="badge border-line bg-panel text-ink">domain project（固定）</span>
        <span className="badge border-line bg-panel text-ink">risk_budget low（固定）</span>
      </div>
    </section>
  );
}

/* ---------------- 下一跳执行面板 ---------------- */

interface StepPanelProps {
  session: SessionResume;
  transition: TransitionKey;
  caseIdPrefill: string | null;
  onExecuted: (result: OperationResult) => void;
}

function StepPanel({ session, transition, caseIdPrefill, onExecuted }: StepPanelProps) {
  const meta = transitionMeta(transition);
  const fields = TRANSITION_FIELDS[transition] ?? [];
  const [values, setValues] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [stepError, setStepError] = useState<OrchestrationError | null>(null);
  const [preview, setPreview] = useState<OrchestrationPreview | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState('');

  // 切换 transition（会话推进）时重置表单与未完成的 preview；case_id 尽力预填
  useEffect(() => {
    const initial: Record<string, string> = {};
    if (caseIdPrefill) initial['case_id'] = caseIdPrefill;
    setValues(initial);
    setFormError(null);
    setStepError(null);
    setPreview(null);
    setIdempotencyKey(newIdempotencyKey(transition));
  }, [transition, caseIdPrefill]);

  if (!meta) return null;

  const needsCaseId = fields.some((field) => field.name === 'case_id');

  async function handlePreview() {
    const built = buildPayload(transition, fields, values);
    setFormError(null);
    if ('error' in built) {
      setFormError(built.error);
      return;
    }
    setBusy(true);
    setStepError(null);
    try {
      const actor = await deriveActorIdentityHash();
      const prepared = await sessionPreview({
        session_id: session.session_id,
        transition,
        payload: built.payload,
        actor_identity_hash: actor,
        expected_sequence: session.sequence,
      });
      setPreview(prepared);
      // 幂等键与本次 preview 绑定：execute 重试复用同一键
      setIdempotencyKey(newIdempotencyKey(transition));
    } catch (error) {
      setStepError(error instanceof OrchestrationError ? error : new OrchestrationError({ code: 'unknown_error', message: '未知错误' }));
    } finally {
      setBusy(false);
    }
  }

  async function handleExecute() {
    if (!preview) return;
    setBusy(true);
    setStepError(null);
    try {
      const result = await sessionExecute(transition, preview, idempotencyKey);
      setPreview(null);
      onExecuted(result);
    } catch (error) {
      // 保留 preview 与幂等键：可用同一键安全重试，或恢复会话后重新 preview
      setStepError(error instanceof OrchestrationError ? error : new OrchestrationError({ code: 'unknown_error', message: '未知错误' }));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card" aria-labelledby="session-next-step-title">
      <h2 id="session-next-step-title" className="flex items-center gap-2 font-semibold">
        下一步：{meta.label}
        <span className="badge border-primary bg-primary-soft font-mono text-xs text-primary">{transition}</span>
      </h2>
      <p className="mt-0.5 text-sm text-muted">{meta.eventDescription}（sequence {session.sequence + 1}）。</p>

      {transition === 'decide' ? (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-muted">
          <IconInfo className="h-3.5 w-3.5 shrink-0" />
          决策确认写入 Pilot 权威案例。
        </p>
      ) : null}
      {transition === 'calibrate' ? (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-uncertainty">
          <IconAlertTriangle className="h-3.5 w-3.5 shrink-0" />
          校准为非因果评估，不会自动 promote 任何建议。
        </p>
      ) : null}
      {transition === 'observe' ? (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-uncertainty">
          <IconAlertTriangle className="h-3.5 w-3.5 shrink-0" />
          结果记录不自动证明建议导致了结果。
        </p>
      ) : null}

      {needsCaseId && !caseIdPrefill ? (
        <p className="mt-2 flex items-center gap-1.5 text-xs text-uncertainty">
          <IconAlertTriangle className="h-3.5 w-3.5 shrink-0" />
          case_id 未自动预填（工作区投影未暴露 Pilot case_id），请手动输入——前端不臆造 case_id。
        </p>
      ) : null}

      {fields.length > 0 ? (
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {fields.map((field) => (
            <div key={field.name} className={field.kind === 'list' || field.name === 'description' ? 'sm:col-span-2' : ''}>
              <label htmlFor={`field-${transition}-${field.name}`} className="text-sm font-medium">
                {field.label}
                {field.required ? <span className="text-risk"> *</span> : null}
              </label>
              {field.kind === 'fixed' ? (
                <p className="mt-1 rounded-md border border-line bg-surface px-2 py-1.5 font-mono text-sm text-muted">
                  {field.fixedValue}
                </p>
              ) : field.kind === 'select' ? (
                <select
                  id={`field-${transition}-${field.name}`}
                  value={values[field.name] ?? ''}
                  onChange={(event) => setValues((current) => ({ ...current, [field.name]: event.target.value }))}
                  className="mt-1 w-full rounded-md border border-line bg-panel px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <option value="">请选择</option>
                  {field.options?.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id={`field-${transition}-${field.name}`}
                  type={field.kind === 'number' ? 'number' : 'text'}
                  value={values[field.name] ?? ''}
                  placeholder={field.placeholder}
                  onChange={(event) => setValues((current) => ({ ...current, [field.name]: event.target.value }))}
                  className="mt-1 w-full rounded-md border border-line bg-panel px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
              )}
              {field.hint ? <p className="mt-0.5 text-xs text-muted">{field.hint}</p> : null}
            </div>
          ))}
        </div>
      ) : (
        <p className="mt-3 rounded-lg border border-line bg-surface p-3 text-sm text-muted">
          本步骤 payload 固定为 <span className="font-mono text-xs">{'{personal_evidence:[],external_evidence:[]}'}</span>
          ；真实证据由服务端 generation runner 组装。若服务端未配置 runner，执行时会返回
          generation_provider_unavailable，恢复说明见错误面板。
        </p>
      )}

      {formError ? (
        <p role="alert" className="mt-3 text-sm text-risk">
          {formError}
        </p>
      ) : null}

      <div className="mt-4">
        <button
          type="button"
          onClick={() => void handlePreview()}
          disabled={busy}
          className="rounded-md border border-primary bg-primary-soft px-3 py-2 text-sm font-medium text-primary transition-colors hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-primary disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy && !preview ? '正在生成…' : `生成 exact preview（${meta.label}）`}
        </button>
      </div>

      {stepError ? (
        <div className="mt-3">
          <TypedRecoveryPanel
            error={stepError}
            operationLabel={meta.label}
            onRetry={stepError.retryable && preview ? () => void handleExecute() : undefined}
          />
        </div>
      ) : null}

      <ConfirmDrawer
        open={preview !== null}
        title={meta.label}
        preview={preview}
        eventDescription={`${meta.eventDescription}（sequence ${session.sequence + 1}）。`}
        confirmLabel={`确认写入"${meta.label}"`}
        idempotencyKey={idempotencyKey}
        busy={busy}
        onConfirm={() => void handleExecute()}
        onClose={() => setPreview(null)}
      />
    </section>
  );
}

/* ---------------- 恢复会话入口（/sessions/new 辅助） ---------------- */

function ResumeEntryCard() {
  const navigate = useNavigate();
  const [sessionId, setSessionId] = useState('');
  return (
    <section className="card" aria-labelledby="resume-entry-title">
      <h2 id="resume-entry-title" className="font-semibold">
        恢复已有会话
      </h2>
      <p className="mt-0.5 text-sm text-muted">输入 session_id 继续推进（只读 resume 后再决定下一跳）。</p>
      <div className="mt-2 flex gap-2">
        <input
          type="text"
          value={sessionId}
          onChange={(event) => setSessionId(event.target.value)}
          aria-label="session_id"
          placeholder="ors_…"
          className="flex-1 rounded-md border border-line bg-panel px-2 py-1.5 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        />
        <button
          type="button"
          onClick={() => sessionId.trim() && void navigate(`/sessions/${encodeURIComponent(sessionId.trim())}`)}
          className="inline-flex items-center gap-1 rounded-md border border-line px-3 py-1.5 text-sm text-ink transition-colors hover:bg-surface focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <IconChevronRight className="h-4 w-4" />
          打开
        </button>
      </div>
    </section>
  );
}

/* ---------------- 页面 ---------------- */

function SessionAdvanceView({ sessionId }: { sessionId: string }) {
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const [lastResult, setLastResult] = useState<OperationResult | null>(null);
  const caseIdPrefill = searchParams.get('case_id');
  const fromRecommendation = searchParams.get('from');

  const query = useQuery({
    queryKey: ['orchestration', 'session', sessionId],
    queryFn: () => sessionResume(sessionId),
    staleTime: 0,
    retry: 1,
  });

  const error = query.error;
  const session = query.data;

  const content = useMemo(() => {
    if (!session) return null;
    const next = NEXT_TRANSITION_BY_STATE[session.state] ?? null;
    return { session, next };
  }, [session]);

  async function handleExecuted(result: OperationResult) {
    setLastResult(result);
    await queryClient.invalidateQueries({ queryKey: ['orchestration', 'session', sessionId] });
  }

  return (
    <div className="section-stack">
      <p className="flex flex-wrap gap-4">
        <Link
          to="/decisions"
          className="inline-flex items-center gap-1 text-sm text-primary transition-colors hover:underline focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <IconArrowLeft className="h-4 w-4" />
          返回决策中心
        </Link>
        {fromRecommendation ? (
          <Link
            to={fromRecommendation === '/actions' ? '/actions' : `/decisions/${encodeURIComponent(fromRecommendation)}`}
            className="inline-flex items-center gap-1 text-sm text-primary transition-colors hover:underline focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <IconArrowLeft className="h-4 w-4" />
            {fromRecommendation === '/actions' ? '返回行动与结果' : '返回来源决策工作区'}
          </Link>
        ) : null}
      </p>

      {query.isPending ? (
        <div className="section-stack" aria-label="会话恢复中">
          <StatePanel variant="loading" />
          <StatePanel variant="loading" />
        </div>
      ) : query.isError ? (
        error instanceof OrchestrationError ? (
          <TypedRecoveryPanel error={error} operationLabel="恢复会话" onResume={() => void query.refetch()} />
        ) : (
          <StatePanel variant="error" title="会话恢复失败" errorMessage="未知错误" onRetry={() => void query.refetch()} />
        )
      ) : content ? (
        <>
          <header className="card">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-lg font-semibold">会话推进</h1>
              <span className="font-mono text-sm break-all" title={`完整 session_id：${content.session.session_id}`}>
                {shortId(content.session.session_id, 24)}
              </span>
              <span className="badge border-primary bg-primary-soft text-primary">
                {SESSION_STATE_LABELS[content.session.state] ?? content.session.state}
              </span>
            </div>
            <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted">
              <span>
                当前序号 <span className="font-mono">{content.session.sequence}</span>
              </span>
              <span className="break-all">
                最近事件校验{' '}
                <span className="font-mono text-xs" title={content.session.last_event_checksum}>
                  {shortId(content.session.last_event_checksum, 20)}
                </span>
              </span>
            </p>
            <div className="mt-3">
              <DecisionStageStepper currentTransition={content.next} />
            </div>
          </header>

          <ManifestCard manifest={content.session.manifest} />

          {lastResult ? (
            <div className="section-stack">
              <TypedRecoveryPanel replayed={lastResult.replayed} />
              <section className="card border-verified bg-verified-soft" aria-label="上一跳写入结果">
                <h2 className="flex items-center gap-1.5 font-medium text-verified">
                  <IconCheckCircle className="h-4 w-4" />
                  「{transitionMeta(lastResult.operation)?.label ?? lastResult.operation}」已写入
                </h2>
                <dl className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-sm">
                  <div>
                    <dt className="inline text-muted">sequence：</dt>
                    <dd className="inline font-mono">{lastResult.sequence}</dd>
                  </div>
                  <div className="break-all">
                    <dt className="inline text-muted">event_id：</dt>
                    <dd className="inline font-mono text-xs" title={lastResult.event_id}>
                      {shortId(lastResult.event_id, 24)}
                    </dd>
                  </div>
                  <div className="break-all">
                    <dt className="inline text-muted">event_checksum：</dt>
                    <dd className="inline font-mono text-xs" title={lastResult.event_checksum}>
                      {shortId(lastResult.event_checksum, 24)}
                    </dd>
                  </div>
                </dl>
              </section>
            </div>
          ) : null}

          {content.next ? (
            <StepPanel
              session={content.session}
              transition={content.next}
              caseIdPrefill={caseIdPrefill}
              onExecuted={(result) => void handleExecuted(result)}
            />
          ) : (
            <StatePanel
              variant="empty"
              title="会话已完成全部阶段"
              description="confirm → calibrate 链已走完，事件全部追加完毕。"
            />
          )}

          <p className="flex items-center gap-1.5 text-xs text-muted">
            <IconInfo className="h-3.5 w-3.5 shrink-0" />
            每一跳都需要重新 preview 并独立确认；前端不提供一键完成全部阶段入口。
          </p>
        </>
      ) : null}
    </div>
  );
}

export function SessionPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  if (!id || id === 'new') {
    const intent = searchParams.get('intent');
    const caseId = searchParams.get('case_id');
    const from = searchParams.get('from');
    // 保留 case_id / from 参数进入推进视图（行动步骤预填与回链）
    const suffix = [caseId ? `case_id=${encodeURIComponent(caseId)}` : '', from ? `from=${encodeURIComponent(from)}` : '']
      .filter(Boolean)
      .join('&');
    // 回链目标：/actions 为行动与结果页，其余 from 视为 recommendation_id 回工作区
    const backLink =
      from === '/actions'
        ? { to: '/actions', label: '返回行动与结果' }
        : from
          ? { to: `/decisions/${encodeURIComponent(from)}`, label: '返回决策工作区' }
          : { to: '/decisions', label: '返回决策中心' };
    return (
      <div className="section-stack">
        <p>
          <Link
            to={backLink.to}
            className="inline-flex items-center gap-1 text-sm text-primary transition-colors hover:underline focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <IconArrowLeft className="h-4 w-4" />
            {backLink.label}
          </Link>
        </p>
        <header className="card">
          <h1 className="text-lg font-semibold">新建决策会话</h1>
          <p className="mt-1 text-sm text-muted">
            Guarded Orchestration 写流程：prepare → exact preview → 显式 confirm，随后逐跳推进。
          </p>
        </header>
        {intent === 'action' ? (
          <div className="card border-uncertainty bg-uncertainty-soft" role="note">
            <p className="flex items-start gap-1.5 text-sm text-uncertainty">
              <IconAlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                你从决策工作区进入，目标是记录行动/结果（action_start / observe）。会话链严格线性，
                需依次推进到对应步骤；case_id {caseId ? '已尽力预填' : '无法预填，需手动输入（前端不臆造 case_id）'}。
              </span>
            </p>
          </div>
        ) : null}
        {intent === 'observe' ? (
          <div className="card border-uncertainty bg-uncertainty-soft" role="note">
            <p className="flex items-start gap-1.5 text-sm text-uncertainty">
              <IconAlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>
                你从行动与结果页进入，目标是记录结果观察（observe）。会话链严格线性：需经
                confirm → … → action_complete 逐步推进到 observe，不能跳段；每跳都要独立 preview 并显式确认。
              </span>
            </p>
          </div>
        ) : null}
        <NewSessionFlow onCreated={(sessionId) => void navigate(`/sessions/${encodeURIComponent(sessionId)}${suffix ? `?${suffix}` : ''}`)} />
        <ResumeEntryCard />
      </div>
    );
  }

  return <SessionAdvanceView sessionId={id} />;
}
