import { useState } from 'react';
import { usePiRuntimeStatus, usePiRuntimeTasks } from '../../api/hooks';
import { StatePanel } from '../../components/feedback/StatePanel';

const stateText: Record<string, string> = {
  queued: '排队中', claimed: '已领取', running: '处理中', cancel_requested: '已请求取消',
  succeeded: '已完成', failed: '失败', outcome_unknown: '结果状态未知', offline: '离线', stale: '观测已过期',
};

export function PiRuntimePage() {
  const status = usePiRuntimeStatus();
  const tasks = usePiRuntimeTasks();
  const [selected, setSelected] = useState<string | null>(null);
  if (status.isPending || tasks.isPending) return <StatePanel variant="loading" />;
  if (status.isError || tasks.isError) return <StatePanel variant="error" title="AI Runtime 暂不可用" onRetry={() => { void status.refetch(); void tasks.refetch(); }} />;
  const current = tasks.data.tasks.find((task) => task.task_id === selected) ?? tasks.data.tasks[0];
  return (
    <div className="section-stack" data-testid="pi-runtime-page">
      <h1 className="text-lg font-semibold">AI Runtime</h1>
      <section className="card" aria-labelledby="pi-kernel-status">
        <h2 id="pi-kernel-status" className="font-semibold">Kernel 状态</h2>
        <p className="mt-2 text-sm" role="status" aria-label={`Kernel ${status.data.state}`}>{status.data.state === 'ready' ? '就绪' : status.data.state}</p>
        <p className="mt-1 text-xs text-muted">观测时间：{status.data.observed_at} · Provider calls：{status.data.provider_calls}</p>
      </section>
      <section className="card" aria-labelledby="pi-task-list">
        <h2 id="pi-task-list" className="font-semibold">任务</h2>
        {tasks.data.tasks.length === 0 ? <p className="mt-3 text-sm text-muted">暂无任务</p> : (
          <ul className="mt-3 space-y-2" role="listbox" aria-label="Pi 任务列表">
            {tasks.data.tasks.map((task) => (
              <li key={task.event_id || task.task_id}>
                <button type="button" role="option" aria-selected={current?.task_id === task.task_id} onClick={() => setSelected(task.task_id)} className="w-full rounded-md border border-line p-3 text-left focus:outline-none focus:ring-2 focus:ring-primary">
                  <span className="font-mono text-xs">{task.task_id}</span>
                  <span className="ml-3 text-sm">{stateText[task.state] ?? task.state}</span>
                  <span className="ml-3 text-xs text-muted">v{task.version}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="card" aria-labelledby="pi-timeline">
        <h2 id="pi-timeline" className="font-semibold">任务时间线</h2>
        {current ? <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2"><div><dt className="text-muted">状态</dt><dd>{stateText[current.state] ?? current.state}</dd></div><div><dt className="text-muted">恢复动作</dt><dd>{current.recovery_action}</dd></div><div><dt className="text-muted">证据引用数</dt><dd>{current.evidence_refs.length}</dd></div><div><dt className="text-muted">观测时间</dt><dd>{current.observed_at}</dd></div></dl> : <p className="mt-3 text-sm text-muted">选择任务查看元数据。</p>}
      </section>
      <p className="card text-sm text-muted" role="note">隐私提示：页面只展示任务、会话、状态和证据引用，不展示提示词、模型正文或 Tool 输入输出。</p>
    </div>
  );
}
