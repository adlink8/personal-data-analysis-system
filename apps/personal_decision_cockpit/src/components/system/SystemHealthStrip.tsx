import type { SystemStatusData } from '../../api/schemas';
import { fmtTime } from '../../utils/format';

const STATE_LABELS: Record<string, string> = {
  healthy: '已验证可用',
  reachable_only: '仅 listener 可达',
  unavailable: '不可用',
  stale_observation: '过期观测',
  unknown: '未知',
  partial: '部分可用',
};

function ObservationCard({ observation }: { observation: SystemStatusData['observations'][number] }) {
  const label = STATE_LABELS[observation.state] ?? '未知';
  const tone = observation.state === 'healthy' ? 'text-verified' : observation.state === 'unavailable' ? 'text-risk' : 'text-uncertainty';
  return (
    <article className="rounded-lg border border-line bg-surface p-3" aria-label={observation.label}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="font-medium">{observation.label}</h3>
        <span className={`badge border-line bg-panel ${tone}`}>{label}</span>
      </div>
      <dl className="mt-2 grid gap-x-4 gap-y-1 text-xs sm:grid-cols-2">
        <div><dt className="inline text-muted">来源：</dt><dd className="inline">{observation.source}</dd></div>
        <div><dt className="inline text-muted">观测时间：</dt><dd className="inline">{observation.observed_at ? fmtTime(observation.observed_at) : '未提供'}</dd></div>
        <div className="sm:col-span-2"><dt className="inline text-muted">范围：</dt><dd className="inline">{observation.scope}</dd></div>
      </dl>
      <p className="mt-2 text-xs text-muted">恢复/限制：{observation.recovery_hint}</p>
    </article>
  );
}

export function SystemHealthStrip({ data }: { data: SystemStatusData }) {
  return (
    <section className="card section-stack" aria-labelledby="system-observations-title">
      <div>
        <h2 id="system-observations-title" className="font-semibold">独立运行观测</h2>
        <p className="mt-1 text-sm text-muted">每行只描述一个来源和范围；REST 请求成功不等于整栈健康。</p>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {data.observations.length > 0 ? data.observations.map((observation) => (
          <ObservationCard key={observation.id} observation={observation} />
        )) : <p className="text-sm text-muted">暂无独立观测。</p>}
      </div>
      {data.supervisor_state ? (
        <article className="rounded-lg border border-uncertainty bg-uncertainty-soft p-3" aria-label="supervisor last observation">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-medium">Supervisor last observation</h3>
            <span className="badge border-line bg-panel text-uncertainty">{STATE_LABELS[data.supervisor_state.state] ?? '未知'}</span>
          </div>
          <p className="mt-1 text-sm text-muted">这是保存的历史观测，不证明当前进程 ownership 或 readiness。</p>
          <p className="mt-1 text-xs text-muted">保存时间：{data.supervisor_state.observed_at ? fmtTime(data.supervisor_state.observed_at) : '未提供'} · {data.supervisor_state.recovery_hint}</p>
          {data.supervisor_state.services.length > 0 ? (
            <ul className="mt-2 flex flex-wrap gap-2 text-xs">
              {data.supervisor_state.services.map((service) => <li key={service.service} className="badge border-line bg-panel">{service.service}: {service.healthy ? '历史标记 healthy' : '历史标记 unavailable'}</li>)}
            </ul>
          ) : null}
        </article>
      ) : null}
    </section>
  );
}
