import { useState } from 'react';
import type { ApiError } from '../../api/client';
import { useProactiveControlStatus, useProactiveSummary } from '../../api/hooks';
import type { ProactiveSummaryCard, ProactiveSummaryEnvelope } from '../../api/schemas';
import { StatePanel } from '../../components/feedback/StatePanel';
import { ProactiveCard } from '../../components/proactive/ProactiveCard';
import { IconAlertTriangle, IconChevronRight } from '../../components/icons';
import { fmtNumber, fmtTime, fmtUnknown } from '../../utils/format';

/**
 * 主动提醒页（spec §7.6）：eligible 候选分组视图。
 * 需要现在处理（groups.now）/ 可延后（groups.deferrable）；
 * 已抑制与冷却中 / 历史为诚实空态（不列入 eligible inbox），可按 candidate_id
 * 调 /proactive/controls/status 逐条查看控制状态。
 * metrics 区渲染噪声预算等真实字段（键值表格）；notes 渲染为说明条。
 * 写入限制：REST 未暴露 proactive 写路由，卡片上的 Snooze/Suppress/限定 Scope/Restore
 * 一律 disabled 并注明去向，本页不新增任何写入路径。
 */

function errorAuthorities(envelope: ProactiveSummaryEnvelope): string[] {
  return Object.entries(envelope.authorities)
    .filter(([, value]) => value === 'error')
    .map(([name]) => name);
}

/* ---------------- 候选分组 ---------------- */

function CandidateGroup({
  id,
  title,
  description,
  cards,
}: {
  id: string;
  title: string;
  description: string;
  cards: ProactiveSummaryCard[];
}) {
  return (
    <section aria-labelledby={`proactive-group-${id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <h2 id={`proactive-group-${id}`} className="font-semibold">
          {title}
        </h2>
        <span className="badge border-line bg-panel text-muted">{cards.length} 条</span>
      </div>
      <p className="mt-0.5 text-sm text-muted">{description}</p>
      {cards.length === 0 ? (
        <p className="card mt-2 text-sm text-muted">无</p>
      ) : (
        <div className="section-stack mt-2">
          {cards.map((card, index) => (
            <ProactiveCard key={card.candidate_id ?? `card-${index}`} card={card} />
          ))}
        </div>
      )}
    </section>
  );
}

/* ---------------- 控制状态查询（已抑制与冷却中） ---------------- */

function ControlStatusLookup() {
  const [input, setInput] = useState('');
  const [submitted, setSubmitted] = useState<string | null>(null);
  const query = useProactiveControlStatus(submitted);
  const entries = query.data ? Object.entries(query.data) : [];

  return (
    <div className="mt-3">
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          const value = input.trim();
          if (value) setSubmitted(value);
        }}
      >
        <input
          type="text"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          aria-label="candidate_id"
          placeholder="输入 candidate_id（cand_…）"
          className="flex-1 rounded-md border border-line bg-panel px-2 py-1.5 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        />
        <button
          type="submit"
          className="inline-flex items-center gap-1 rounded-md border border-line px-3 py-1.5 text-sm text-ink transition-colors hover:bg-surface focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <IconChevronRight className="h-4 w-4" />
          查询控制状态
        </button>
      </form>

      {submitted ? (
        query.isPending ? (
          <p className="mt-2 text-sm text-muted">查询中…</p>
        ) : query.isError ? (
          <div className="mt-2">
            <StatePanel
              variant="error"
              title="控制状态查询失败"
              errorMessage={(query.error as ApiError).message}
              onRetry={() => void query.refetch()}
            />
          </div>
        ) : entries.length === 0 ? (
          <p className="mt-2 text-sm text-muted">未提供</p>
        ) : (
          <dl className="mt-2 grid gap-x-6 gap-y-1 rounded-lg border border-line bg-surface p-3 text-sm sm:grid-cols-2">
            {entries.map(([key, value]) => (
              <div key={key} className="break-words">
                <dt className="inline font-mono text-xs text-muted">{key}：</dt>
                <dd className="inline" title={fmtUnknown(value, 500)}>
                  {fmtUnknown(value)}
                </dd>
              </div>
            ))}
          </dl>
        )
      ) : null}
    </div>
  );
}

/* ---------------- 页面 ---------------- */

export function ProactivePage() {
  const query = useProactiveSummary();

  if (query.isPending) {
    return (
      <div className="section-stack" aria-label="主动提醒加载中">
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
        title="主动提醒加载失败"
        errorMessage={err.message}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const envelope = query.data;
  const { data } = envelope;
  const groups = data.groups;

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

      <header className="card">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-lg font-semibold">主动提醒</h1>
          <span className="badge border-line bg-panel text-muted">共 {fmtNumber(data.total_available)} 条候选</span>
        </div>
        <p className="mt-2 text-sm text-muted">
          仅展示达到阈值且当前 eligible 的候选；已抑制与冷却中的候选不列入本投影，可按候选查询控制状态。
        </p>
        <p className="mt-1 text-xs text-muted">投影生成于 {fmtTime(envelope.generated_at)}（每分钟自动刷新）</p>
      </header>

      {data.notes.length > 0 ? (
        <div className="card border-line" role="note" aria-label="投影说明">
          <ul className="list-disc pl-5 text-sm text-muted">
            {data.notes.map((note, i) => (
              <li key={i}>{note}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {!groups ? (
        // proactive Authority 部分失败：groups 节为 null，按节降级而非假空
        <StatePanel
          variant="partial"
          title="主动提醒分组暂不可用"
          unavailableAuthorities={errorAuthorities(envelope)}
          description="proactive Authority 本次未返回分组数据，其余区域不受影响。"
        />
      ) : (
        <>
          <CandidateGroup
            id="now"
            title="需要现在处理"
            description="重要性与紧迫性达到阈值的候选。"
            cards={groups.now}
          />
          <CandidateGroup
            id="deferrable"
            title="可延后"
            description="当前 eligible 但可稍后处理的候选。"
            cards={groups.deferrable}
          />
        </>
      )}

      <section className="card" aria-labelledby="proactive-suppressed-title">
        <h2 id="proactive-suppressed-title" className="font-semibold">
          已抑制与冷却中
        </h2>
        <p className="mt-1 text-sm text-muted">
          该状态不列入 eligible inbox，本投影不返回其列表；可按候选查询控制状态。
        </p>
        <ControlStatusLookup />
      </section>

      <section className="card" aria-labelledby="proactive-history-title">
        <h2 id="proactive-history-title" className="font-semibold">
          历史
        </h2>
        <p className="mt-1 text-sm text-muted">
          历史候选不在 eligible inbox 投影中返回；本投影仅面向当前 eligible 候选，不提供历史视图。
        </p>
      </section>

      {data.metrics ? (
        <section className="card" aria-labelledby="proactive-metrics-title">
          <h2 id="proactive-metrics-title" className="font-semibold">
            指标
          </h2>
          <p className="mt-0.5 text-sm text-muted">噪声预算等运行指标（后端原样字段）。</p>
          {Object.keys(data.metrics).length === 0 ? (
            <p className="mt-2 text-sm text-muted">未提供</p>
          ) : (
            <dl className="mt-3 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
              {Object.entries(data.metrics).map(([key, value]) => (
                <div key={key} className="break-words">
                  <dt className="inline font-mono text-xs text-muted">{key}：</dt>
                  <dd className="inline" title={fmtUnknown(value, 500)}>
                    {fmtUnknown(value)}
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </section>
      ) : null}
    </div>
  );
}
