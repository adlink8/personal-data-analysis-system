import type { ReactNode } from 'react';
import type { ApiError } from '../../api/client';
import { usePiOperationMutation, usePiOperations, useSystemStatus } from '../../api/hooks';
import type { PiOperations, SystemStatusEnvelope } from '../../api/schemas';
import { shortId } from '../../components/authority/SnapshotChip';
import { StatePanel } from '../../components/feedback/StatePanel';
import { IconAlertTriangle } from '../../components/icons';
import { SystemHealthStrip } from '../../components/system/SystemHealthStrip';
import { fmtNumber, fmtTime } from '../../utils/format';

/**
 * 系统状态（spec §7.8）：用户态区 + 默认折叠的开发者区域。
 * 普通首页不放大量工程指标。
 */

// Active KU pointer 文件名（仓库约定：var/db/knowledge_index_active.txt）
const POINTER_FILE = 'var/db/knowledge_index_active.txt';

// 四个 Authority DB 的展示名（spec §7.8）
const AUTHORITY_DB_LABELS: ReadonlyArray<{ key: string; label: string }> = [
  { key: 'external', label: '外部环境' },
  { key: 'decision_analysis', label: '决策分析' },
  { key: 'project_pilot', label: '项目试点' },
  { key: 'recommendation_calibration', label: '推荐校准' },
];

function BoolText({ value, trueText, falseText }: { value: boolean | null; trueText: string; falseText: string }) {
  if (value === null) return <span className="text-muted">未知</span>;
  return value ? (
    <span className="text-verified">{trueText}</span>
  ) : (
    <span className="text-risk">{falseText}</span>
  );
}

function DefinitionItem({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-line bg-surface p-3">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="mt-1 break-words text-sm">{children}</dd>
    </div>
  );
}

function UserSection({ envelope }: { envelope: SystemStatusEnvelope }) {
  const { knowledge } = envelope.data;
  return (
    <section className="card" aria-labelledby="system-user-title">
      <h2 id="system-user-title" className="font-semibold">
        运行概览
      </h2>
      <dl className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <DefinitionItem label="Chroma 向量库">
          <BoolText value={knowledge.available} trueText="可用" falseText="不可用" />
        </DefinitionItem>
        <DefinitionItem label="Active KU Collection">
          <span className="font-mono">{knowledge.active_collection ?? '—'}</span>
        </DefinitionItem>
        <DefinitionItem label="知识单元数">{fmtNumber(knowledge.unit_count)}</DefinitionItem>
        <DefinitionItem label="Serving Snapshot">
          <span className="font-mono" title={knowledge.serving_snapshot_id ?? undefined}>
            {knowledge.serving_snapshot_id ? shortId(knowledge.serving_snapshot_id) : '未绑定'}
          </span>
        </DefinitionItem>
        <DefinitionItem label="快照漂移（snapshot_drift）">
          {(() => {
            // 后端真实返回为漂移条目数组（空数组=无漂移），兼容布尔；JS 空数组为真值，须先归一化
            const raw = knowledge.snapshot_drift;
            const drift = Array.isArray(raw) ? raw.length > 0 : raw === true;
            if (raw === null || raw === undefined) return <span className="text-muted">未知</span>;
            return drift ? (
              <span className="text-uncertainty">存在漂移{Array.isArray(raw) ? `（${raw.length} 项）` : ''}</span>
            ) : (
              <span className="text-verified">无漂移</span>
            );
          })()}
        </DefinitionItem>
        <DefinitionItem label="Active Pointer 文件">
          <BoolText value={knowledge.pointer_exists} trueText="存在" falseText="缺失" />
        </DefinitionItem>
        <DefinitionItem label="投影生成时间">{fmtTime(envelope.generated_at)}</DefinitionItem>
      </dl>
    </section>
  );
}

function DeveloperSection({ envelope }: { envelope: SystemStatusEnvelope }) {
  const { knowledge, authority_dbs } = envelope.data;
  const bindings = envelope.snapshot_bindings;
  return (
    <details className="card">
      <summary className="cursor-pointer select-none rounded-md text-sm font-medium text-muted focus:outline-none focus:ring-2 focus:ring-primary">
        开发者区域（完整 ID / 校验和 / Authority DB，默认折叠）
      </summary>
      <div className="mt-4 space-y-4">
        <section>
          <h3 className="text-sm font-medium">完整快照 ID 与校验和</h3>
          <dl className="mt-2 space-y-1.5 text-sm">
            {(
              [
                ['Personal Snapshot', bindings.personal],
                ['External Snapshot', bindings.external],
                ['Serving Snapshot（绑定）', bindings.serving],
                ['Serving Snapshot（知识库）', knowledge.serving_snapshot_id],
                ['Snapshot Hash', knowledge.snapshot_hash],
              ] as const
            ).map(([label, value]) => (
              <div key={label} className="flex flex-wrap gap-2">
                <dt className="w-48 shrink-0 text-muted">{label}</dt>
                <dd className="min-w-0 flex-1 break-all font-mono text-xs">{value ?? '未绑定'}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section>
          <h3 className="text-sm font-medium">Authority 数据库</h3>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[32rem] text-left text-sm">
              <thead>
                <tr className="border-b border-line text-xs text-muted">
                  <th scope="col" className="py-1.5 pr-3 font-medium">Authority</th>
                  <th scope="col" className="py-1.5 pr-3 font-medium">路径</th>
                  <th scope="col" className="py-1.5 pr-3 font-medium">存在</th>
                  <th scope="col" className="py-1.5 font-medium">可读</th>
                </tr>
              </thead>
              <tbody>
                {AUTHORITY_DB_LABELS.map(({ key, label }) => {
                  const db = authority_dbs[key];
                  return (
                    <tr key={key} className="border-b border-line last:border-0">
                      <td className="py-1.5 pr-3">{label}</td>
                      <td className="py-1.5 pr-3 font-mono text-xs">{db?.path ?? '未知'}</td>
                      <td className="py-1.5 pr-3">
                        {db ? <BoolText value={db.exists} trueText="是" falseText="否" /> : <span className="text-muted">未知</span>}
                      </td>
                      <td className="py-1.5">
                        {db ? <BoolText value={db.readable} trueText="是" falseText="否" /> : <span className="text-muted">未知</span>}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>

        <p className="text-sm text-muted">
          Active pointer 文件：<code className="text-xs">{POINTER_FILE}</code>
        </p>
      </div>
    </details>
  );
}

function OperationStatus({ data }: { data: PiOperations }) {
  const cancel = usePiOperationMutation('cancel');
  const resume = usePiOperationMutation('resume');
  const reconcile = usePiOperationMutation('reconcile');
  const operations = data.operations;
  const mutate = (action: 'cancel' | 'resume' | 'reconcile', operation: PiOperations['operations'][number]) => {
    const mutation = action === 'cancel' ? cancel : action === 'resume' ? resume : reconcile;
    mutation.mutate({ operation_id: operation.operation_id, expected_version: operation.version, idempotency_key: `cockpit:${action}:${operation.operation_id}:${operation.version}`, ...(action === 'reconcile' ? { receipt_refs: [], fingerprint_refs: [] } : {}) });
  };
  return (
    <section className="card" aria-labelledby="pi-operation-title">
      <h2 id="pi-operation-title" className="font-semibold">Kernel 操作控制面</h2>
      <p className="mt-1 text-sm text-muted">只显示 Task、Session、Skill、Tool、Provider 与 Authority transaction 的元数据；控制意图仍由 Kernel 校验版本和幂等键。</p>
      {data.state !== 'ready' ? <p className="mt-2 text-sm text-uncertainty">Kernel 当前不可用：{data.recovery_action}</p> : null}
      {operations.length === 0 ? <p className="mt-3 text-sm text-muted">暂无可投影操作。</p> : (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[48rem] text-left text-sm">
            <thead><tr className="border-b border-line text-xs text-muted"><th className="py-1.5 pr-3">操作</th><th className="py-1.5 pr-3">平面</th><th className="py-1.5 pr-3">状态</th><th className="py-1.5 pr-3">版本</th><th className="py-1.5">受控动作</th></tr></thead>
            <tbody>{operations.map((operation) => (
              <tr key={operation.operation_id} className="border-b border-line last:border-0">
                <td className="py-1.5 pr-3 font-mono text-xs">{shortId(operation.operation_id)}</td><td className="py-1.5 pr-3">{operation.operation_kind}</td><td className="py-1.5 pr-3">{operation.state}</td><td className="py-1.5 pr-3">{operation.version}</td>
                <td className="py-1.5"><div className="flex gap-2">{operation.allowed_actions.filter((action): action is 'cancel' | 'resume' | 'reconcile' => action === 'cancel' || action === 'resume' || action === 'reconcile').map((action) => <button key={action} type="button" className="rounded border border-line px-2 py-1 text-xs" onClick={() => mutate(action, operation)} disabled={cancel.isPending || resume.isPending || reconcile.isPending}>{action}</button>)}</div></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function SystemPage() {
  const query = useSystemStatus();
  const operations = usePiOperations();

  if (query.isPending) {
    return (
      <div className="section-stack" aria-label="系统状态加载中">
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
        title="系统状态加载失败"
        errorMessage={err.message}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const envelope = query.data;

  return (
    <div className="section-stack">
      <h1 className="text-lg font-semibold">系统状态</h1>

      <p className="card text-sm text-muted" role="note">
        Cockpit 仅展示只读观测；不能启动、停止、重启、杀掉进程或配置 Tunnel。
      </p>

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

      <SystemHealthStrip data={envelope.data} />
      <UserSection envelope={envelope} />
      <DeveloperSection envelope={envelope} />
      {!operations.isPending && !operations.isError && operations.data ? <OperationStatus data={operations.data} /> : null}
    </div>
  );
}
