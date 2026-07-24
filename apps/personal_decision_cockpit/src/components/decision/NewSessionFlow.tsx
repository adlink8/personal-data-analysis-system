import { useState } from 'react';
import {
  deriveActorIdentityHash,
  newIdempotencyKey,
  OrchestrationError,
  sessionConfirm,
  sessionPrepare,
  type OperationResult,
  type OrchestrationPreview,
} from '../../api/orchestration';
import { shortId } from '../authority/SnapshotChip';
import { TypedRecoveryPanel } from '../feedback/TypedRecoveryPanel';
import { IconPlus, IconX } from '../icons';
import { ConfirmDrawer } from './ConfirmDrawer';

/**
 * 新建决策会话流程（spec §5.2 / §5.3）：
 * 表单（goal + constraints + weights，固定 domain=project / risk_budget=low）
 * → POST /agent/session/prepare → ConfirmDrawer 展示 P0 exact preview
 * → POST /agent/session/confirm → OperationResult（sequence/event_id/checksum）。
 * 失败走 TypedRecoveryPanel，不静默、不中断。
 */

interface WeightRow {
  key: string;
  value: string;
}

interface NewSessionFlowProps {
  /** confirm 成功后回调（通常跳转会话推进视图 /sessions/<id>） */
  onCreated: (sessionId: string) => void;
}

type FlowError = OrchestrationError | null;

function validateForm(goal: string, constraints: string[], weights: WeightRow[]): string | null {
  if (!goal.trim()) return '决策问题（goal）必填';
  if (constraints.every((item) => !item.trim())) return '至少需要 1 条非空约束';
  const filled = weights.filter((row) => row.key.trim());
  if (filled.length === 0) return '至少需要 1 个权重';
  for (const row of filled) {
    const parsed = Number.parseFloat(row.value);
    if (Number.isNaN(parsed) || parsed < 0 || parsed > 1) return `权重「${row.key}」必须是 0..1 之间的数值`;
  }
  return null;
}

export function NewSessionFlow({ onCreated }: NewSessionFlowProps) {
  const [goal, setGoal] = useState('');
  const [constraints, setConstraints] = useState<string[]>(['']);
  const [weights, setWeights] = useState<WeightRow[]>([{ key: '', value: '0.5' }]);
  const [formError, setFormError] = useState<string | null>(null);

  const [busy, setBusy] = useState(false);
  const [flowError, setFlowError] = useState<FlowError>(null);
  const [preview, setPreview] = useState<OrchestrationPreview | null>(null);
  // 幂等键与 preview 一一对应：同一次 confirm 的重试复用同一键
  const [idempotencyKey, setIdempotencyKey] = useState('');
  const [result, setResult] = useState<OperationResult | null>(null);

  async function handlePrepare() {
    const message = validateForm(goal, constraints, weights);
    setFormError(message);
    if (message) return;
    setBusy(true);
    setFlowError(null);
    try {
      const actor = await deriveActorIdentityHash();
      const cleanWeights: Record<string, number> = {};
      for (const row of weights) {
        if (row.key.trim()) cleanWeights[row.key.trim()] = Number.parseFloat(row.value);
      }
      const prepared = await sessionPrepare({
        goal: goal.trim(),
        constraints: constraints.map((item) => item.trim()).filter(Boolean),
        weights: cleanWeights,
        actor_identity_hash: actor,
        domain: 'project',
        risk_budget: 'low',
      });
      setPreview(prepared);
      setIdempotencyKey(newIdempotencyKey('confirm'));
    } catch (error) {
      setFlowError(
        error instanceof OrchestrationError
          ? error
          : new OrchestrationError({ code: 'unknown_error', message: '未知错误' }),
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirm() {
    if (!preview) return;
    setBusy(true);
    setFlowError(null);
    try {
      const confirmed = await sessionConfirm(preview, idempotencyKey);
      setResult(confirmed);
      setPreview(null);
    } catch (error) {
      setFlowError(
        error instanceof OrchestrationError
          ? error
          : new OrchestrationError({ code: 'unknown_error', message: '未知错误' }),
      );
      // confirm 失败：保留 preview 与幂等键，允许同一键重试（抽屉保持打开）
    } finally {
      setBusy(false);
    }
  }

  /* ---------- confirm 成功：OperationResult ---------- */
  if (result) {
    return (
      <div className="section-stack">
        <TypedRecoveryPanel replayed={result.replayed} />
        {!result.replayed ? (
          <section className="card border-verified bg-verified-soft" aria-label="会话已创建">
            <h3 className="font-medium text-verified">决策会话已创建并确认</h3>
            <dl className="mt-2 space-y-1 text-sm">
              <div>
                <dt className="inline text-muted">sequence：</dt>
                <dd className="inline font-mono">{result.sequence}</dd>
              </div>
              <div>
                <dt className="inline text-muted">event_id：</dt>
                <dd className="inline font-mono text-xs break-all" title={result.event_id}>
                  {shortId(result.event_id, 24)}
                </dd>
              </div>
              <div>
                <dt className="inline text-muted">event_checksum：</dt>
                <dd className="inline font-mono text-xs break-all" title={result.event_checksum}>
                  {shortId(result.event_checksum, 24)}
                </dd>
              </div>
            </dl>
          </section>
        ) : null}
        <p className="text-sm text-muted">
          后续每一跳（generate → … → calibrate）都需要重新 preview 并独立确认，前端不提供一键完成入口。
        </p>
        <div>
          <button
            type="button"
            onClick={() => onCreated(result.session_id)}
            className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-white transition-colors hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-primary"
          >
            进入会话推进视图
          </button>
        </div>
      </div>
    );
  }

  /* ---------- prepare 表单 ---------- */
  return (
    <div className="section-stack">
      <section className="card" aria-labelledby="new-session-form-title">
        <h3 id="new-session-form-title" className="font-semibold">
          定义决策问题
        </h3>
        <p className="mt-0.5 text-sm text-muted">
          提交后先生成 exact preview，逐项核对并显式确认后才会写入第一条事件。
        </p>

        <div className="mt-3 space-y-4">
          <div>
            <label htmlFor="session-goal" className="text-sm font-medium">
              决策问题（goal）
            </label>
            <input
              id="session-goal"
              type="text"
              value={goal}
              onChange={(event) => setGoal(event.target.value)}
              placeholder="例如：未来 8 周如何分配英语、项目和求职时间"
              className="mt-1 w-full rounded-md border border-line bg-panel px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          <div>
            <span className="text-sm font-medium">约束（constraints，至少 1 条）</span>
            <ul className="mt-1 space-y-2">
              {constraints.map((value, index) => (
                <li key={index} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={value}
                    aria-label={`约束 ${index + 1}`}
                    onChange={(event) =>
                      setConstraints((rows) => rows.map((row, i) => (i === index ? event.target.value : row)))
                    }
                    placeholder="例如：每周总投入不超过 30 小时"
                    className="flex-1 rounded-md border border-line bg-panel px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                  <button
                    type="button"
                    aria-label={`删除约束 ${index + 1}`}
                    onClick={() => setConstraints((rows) => (rows.length > 1 ? rows.filter((_, i) => i !== index) : rows))}
                    className="rounded-md border border-line p-1.5 text-muted transition-colors hover:bg-surface focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    <IconX />
                  </button>
                </li>
              ))}
            </ul>
            <button
              type="button"
              onClick={() => setConstraints((rows) => [...rows, ''])}
              className="mt-2 inline-flex items-center gap-1 text-sm text-primary transition-colors hover:underline focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <IconPlus className="h-3.5 w-3.5" />
              添加约束
            </button>
          </div>

          <div>
            <span className="text-sm font-medium">权重（weights，键 + 0..1 数值，至少 1 个）</span>
            <ul className="mt-1 space-y-2">
              {weights.map((row, index) => (
                <li key={index} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={row.key}
                    aria-label={`权重 ${index + 1} 名称`}
                    onChange={(event) =>
                      setWeights((rows) => rows.map((item, i) => (i === index ? { ...item, key: event.target.value } : item)))
                    }
                    placeholder="维度，如 career"
                    className="flex-1 rounded-md border border-line bg-panel px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                  <input
                    type="number"
                    value={row.value}
                    aria-label={`权重 ${index + 1} 数值`}
                    min={0}
                    max={1}
                    step={0.05}
                    onChange={(event) =>
                      setWeights((rows) => rows.map((item, i) => (i === index ? { ...item, value: event.target.value } : item)))
                    }
                    className="w-24 rounded-md border border-line bg-panel px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                  />
                  <button
                    type="button"
                    aria-label={`删除权重 ${index + 1}`}
                    onClick={() => setWeights((rows) => (rows.length > 1 ? rows.filter((_, i) => i !== index) : rows))}
                    className="rounded-md border border-line p-1.5 text-muted transition-colors hover:bg-surface focus:outline-none focus:ring-2 focus:ring-primary"
                  >
                    <IconX />
                  </button>
                </li>
              ))}
            </ul>
            <button
              type="button"
              onClick={() => setWeights((rows) => [...rows, { key: '', value: '0.5' }])}
              className="mt-2 inline-flex items-center gap-1 text-sm text-primary transition-colors hover:underline focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <IconPlus className="h-3.5 w-3.5" />
              添加权重
            </button>
          </div>

          {/* 固定边界：只读展示，不可改 */}
          <dl className="flex flex-wrap gap-2 text-sm">
            <div className="badge border-line bg-panel text-ink">
              domain <span className="font-mono">project</span>（固定）
            </div>
            <div className="badge border-line bg-panel text-ink">
              risk_budget <span className="font-mono">low</span>（固定）
            </div>
          </dl>
          <p className="text-xs text-muted">
            操作者身份（actor_identity_hash）由浏览器本地随机串经 SHA-256 派生，不含真实用户标识、不持久化；
            高风险域（健康/财务/关系）与外部动作被服务端词表直接拒绝。
          </p>

          {formError ? (
            <p role="alert" className="text-sm text-risk">
              {formError}
            </p>
          ) : null}

          <div>
            <button
              type="button"
              onClick={() => void handlePrepare()}
              disabled={busy}
              className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-white transition-colors hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-primary disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy && !preview ? '正在生成…' : '生成 exact preview（prepare）'}
            </button>
          </div>
        </div>
      </section>

      {flowError ? (
        <TypedRecoveryPanel
          error={flowError}
          operationLabel="创建决策会话"
          onRetry={flowError.retryable ? () => void (preview ? handleConfirm() : handlePrepare()) : undefined}
        />
      ) : null}

      <ConfirmDrawer
        open={preview !== null}
        title="创建决策会话"
        preview={preview}
        eventDescription="将创建会话并写入第一条 confirm 事件（sequence 1），绑定当前 Personal/External 快照。"
        confirmLabel='确认写入"创建决策会话"'
        idempotencyKey={idempotencyKey}
        busy={busy}
        onConfirm={() => void handleConfirm()}
        onClose={() => setPreview(null)}
      />
    </div>
  );
}
