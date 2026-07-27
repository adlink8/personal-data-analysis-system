import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { ApiError } from '../../api/client';
import { useProactiveCandidateExplain } from '../../api/hooks';
import type { ProactiveSummaryCard } from '../../api/schemas';
import { fmtTime, fmtUnknown } from '../../utils/format';
import { shortId } from '../authority/SnapshotChip';
import { StatePanel } from '../feedback/StatePanel';
import { IconChevronRight, IconEye, IconInfo } from '../icons';

/**
 * ProactiveCard（spec §7.6 / §8）：主动候选卡。
 * 领域 chips、candidate_id 短码、candidate_class/presentation_kind、importance（score/level 尽力解析，
 * 解析不出显原始键值）、reason_codes（触发依据）、valid_from~expires_at、current_control_eligible 与
 * current_control_reason_codes。查看证据调 /proactive/candidate/explain 展开解释与限制。
 *
 * 写入限制（诚实降级）：REST 未暴露 proactive 写路由（POST 仅 /agent/session/* 与 /search/*），
 * Snooze / Suppress / 限定 Scope / Restore 一律 disabled + title/说明，不做假按钮或静默不可点。
 */

const CONTROL_WRITE_HINT = '该写入由 MCP 工具或 pk CLI 提供，REST 未暴露';

/* ---------------- importance 尽力解析 ---------------- */

function ImportanceLine({ importance }: { importance: Record<string, unknown> }) {
  const entries = Object.entries(importance);
  if (entries.length === 0) {
    return (
      <p className="text-sm text-muted">
        重要性 <span>未提供</span>
      </p>
    );
  }
  const score = importance['final_score'];
  const level = importance['level'];
  const renderedKeys = new Set<string>();
  if (typeof level === 'string') renderedKeys.add('level');
  if (typeof score === 'number') renderedKeys.add('final_score');
  const rest = entries.filter(([key]) => !renderedKeys.has(key));
  return (
    <p className="flex flex-wrap items-center gap-2 text-sm">
      <span className="text-muted">重要性</span>
      {renderedKeys.size > 0 ? (
        <span className="badge border-primary bg-primary-soft text-primary">
          {typeof level === 'string' ? level : '未提供'}
          {typeof score === 'number' ? `（final_score ${score.toFixed(2)}）` : ''}
        </span>
      ) : null}
      {rest.map(([key, value]) => (
        <span key={key} className="badge border-line bg-panel font-mono text-xs text-muted" title={fmtUnknown(value, 500)}>
          {key}={fmtUnknown(value, 32)}
        </span>
      ))}
    </p>
  );
}

/* ---------------- 候选解释展开面板（/proactive/candidate/explain） ---------------- */

function ExplainPanel({ candidateId }: { candidateId: string }) {
  const query = useProactiveCandidateExplain(candidateId);
  if (query.isPending) {
    return <p className="text-sm text-muted">正在加载候选解释…</p>;
  }
  if (query.isError) {
    const err = query.error as ApiError;
    return (
      <StatePanel
        variant="error"
        title="候选解释加载失败"
        errorMessage={err.message}
        onRetry={() => void query.refetch()}
      />
    );
  }
  const data = query.data;
  const explanation = data['explanation'];
  const limitations = Array.isArray(data['limitations'])
    ? (data['limitations'] as unknown[]).filter((item): item is string => typeof item === 'string')
    : [];
  const evidenceCount = Array.isArray(data['evidence']) ? (data['evidence'] as unknown[]).length : 0;
  const extraKeys = Object.keys(data).filter((key) => !['explanation', 'limitations', 'evidence'].includes(key));
  return (
    <div className="section-stack rounded-lg border border-line bg-surface p-3" role="region" aria-label="候选证据与解释">
      <div>
        <h3 className="text-sm font-medium">解释</h3>
        {typeof explanation === 'string' && explanation ? (
          <p className="mt-1 text-sm">{explanation}</p>
        ) : typeof explanation === 'object' && explanation !== null ? (
          <dl className="mt-1 grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
            {Object.entries(explanation as Record<string, unknown>).map(([key, value]) => (
              <div key={key} className="break-words">
                <dt className="inline font-mono text-xs text-muted">{key}：</dt>
                <dd className="inline">{fmtUnknown(value)}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="mt-1 text-sm text-muted">未提供</p>
        )}
      </div>
      {evidenceCount > 0 ? <p className="text-sm text-muted">关联证据 {evidenceCount} 条（明细下钻见证据中心）。</p> : null}
      <div>
        <h3 className="text-sm font-medium">限制</h3>
        {limitations.length === 0 ? (
          <p className="mt-1 text-sm text-muted">未提供</p>
        ) : (
          <ul className="mt-1 list-disc pl-5 text-sm text-muted">
            {limitations.map((limitation, i) => (
              <li key={i}>{limitation}</li>
            ))}
          </ul>
        )}
      </div>
      {extraKeys.length > 0 ? (
        <p className="flex flex-wrap gap-1.5">
          {extraKeys.map((key) => (
            <span key={key} className="badge border-line bg-panel font-mono text-xs text-muted" title={fmtUnknown(data[key], 500)}>
              {key}={fmtUnknown(data[key], 32)}
            </span>
          ))}
        </p>
      ) : null}
    </div>
  );
}

/* ---------------- 卡片 ---------------- */

export function ProactiveCard({ card }: { card: ProactiveSummaryCard }) {
  const [showExplain, setShowExplain] = useState(false);
  const cid = card.candidate_id ?? '';
  return (
    <article className="card section-stack" aria-label={cid ? `主动候选 ${cid}` : '主动候选'}>
      <header className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-sm font-medium break-all" title={cid ? `完整 ID：${cid}` : undefined}>
          {cid ? shortId(cid, 20) : '（无 candidate_id）'}
        </span>
        {card.domains.map((domain) => (
          <span key={domain} className="badge border-line bg-panel text-muted">
            {domain}
          </span>
        ))}
        {card.candidate_class ? (
          <span className="badge border-candidate bg-candidate-soft text-candidate">{card.candidate_class}</span>
        ) : null}
        {card.presentation_kind ? (
          <span className="badge border-line bg-panel text-muted">{card.presentation_kind}</span>
        ) : null}
      </header>

      <ImportanceLine importance={card.importance} />

      <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
        <div className="break-words">
          <dt className="inline text-muted">有效窗口：</dt>
          <dd className="inline">
            {card.valid_from ? fmtTime(card.valid_from) : '未提供'}
            {' ~ '}
            {card.expires_at ? fmtTime(card.expires_at) : '未提供'}
          </dd>
        </div>
        <div>
          <dt className="inline text-muted">控制状态：</dt>
          <dd className="inline">
            {card.current_control_eligible === null || card.current_control_eligible === undefined
              ? '未提供'
              : card.current_control_eligible
                ? '可控制'
                : '当前不可控制'}
          </dd>
        </div>
      </dl>

      <div>
        <p className="text-sm text-muted">触发依据（reason_codes）</p>
        {card.reason_codes.length === 0 ? (
          <p className="mt-1 text-sm text-muted">未提供</p>
        ) : (
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {card.reason_codes.map((code) => (
              <li key={code} className="badge border-line bg-panel font-mono text-xs text-muted">
                {code}
              </li>
            ))}
          </ul>
        )}
      </div>

      {card.current_control_reason_codes.length > 0 ? (
        <div>
          <p className="text-sm text-muted">控制状态依据（current_control_reason_codes）</p>
          <ul className="mt-1 flex flex-wrap gap-1.5">
            {card.current_control_reason_codes.map((code) => (
              <li key={code} className="badge border-line bg-panel font-mono text-xs text-muted">
                {code}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div>
        <p className="text-sm text-muted">
          Control history（authority 原始顺序）
          {card.control_as_of ? ` · as-of ${card.control_as_of}` : ''}
        </p>
        {card.control_history.length === 0 ? (
          <p className="mt-1 text-sm text-muted">未提供（不代表没有历史）</p>
        ) : (
          <ol className="mt-1 section-stack rounded-lg border border-line bg-surface p-2 text-xs">
            {card.control_history.map((event, index) => (
              <li key={String(event.event_id ?? index)} className="flex flex-wrap gap-2">
                <span className="font-mono">{String(event.operation ?? 'unknown')}</span>
                <span className="text-muted">{String(event.reason_code ?? 'reason 未提供')}</span>
                <span className="text-muted">sequence {String(event.sequence ?? '未提供')}</span>
              </li>
            ))}
          </ol>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setShowExplain((current) => !current)}
          disabled={!cid}
          aria-expanded={showExplain}
          className="inline-flex items-center gap-1.5 rounded-md border border-line px-3 py-1.5 text-sm text-ink transition-colors hover:bg-surface focus:outline-none focus:ring-2 focus:ring-primary disabled:cursor-not-allowed disabled:opacity-50"
        >
          <IconEye className="h-4 w-4" />
          {showExplain ? '收起证据' : '查看证据'}
        </button>
        <Link
          to="/sessions/new"
          className="inline-flex items-center gap-1.5 rounded-md border border-primary bg-primary-soft px-3 py-1.5 text-sm font-medium text-primary transition-colors hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-primary"
        >
          <IconChevronRight className="h-4 w-4" />
          创建 Decision Case
        </Link>
        {(['Snooze', 'Suppress', '限定 Scope', 'Restore'] as const).map((label) => (
          <button
            key={label}
            type="button"
            disabled
            title={CONTROL_WRITE_HINT}
            className="cursor-not-allowed rounded-md border border-line px-3 py-1.5 text-sm text-muted opacity-50"
          >
            {label}
          </button>
        ))}
      </div>
      <p className="flex items-start gap-1.5 text-xs text-muted">
        <IconInfo className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        Snooze / Suppress / 限定 Scope / Restore 为写操作：{CONTROL_WRITE_HINT}，前端不提供假按钮。
      </p>

      {showExplain && cid ? <ExplainPanel candidateId={cid} /> : null}
    </article>
  );
}
