import { Link } from 'react-router-dom';
import type { ApiError } from '../../api/client';
import { useDecisionQueue } from '../../api/hooks';
import type { DecisionCard, DecisionQueueEnvelope, DecisionStageKey } from '../../api/schemas';
import { DECISION_STAGE_KEYS } from '../../api/schemas';
import { shortId } from '../../components/authority/SnapshotChip';
import {
  ActionStateBadge,
  ConfirmationStateBadge,
  ExpiryText,
} from '../../components/decision/stateBadges';
import { StatePanel } from '../../components/feedback/StatePanel';
import {
  IconAlertTriangle,
  IconArchive,
  IconCheckCircle,
  IconChevronRight,
  IconClock,
  IconInfo,
  IconListOrdered,
} from '../../components/icons';
import { fmtConfidence, fmtNumber, fmtTime } from '../../utils/format';

/**
 * 决策中心列表页（spec §7.3）：六组看板。
 * 需要关注 / 等待确认 / 执行中 / 等待结果 / 已完成 / 已关闭（延迟·拒绝·撤销）；
 * 桌面 2×3 网格、移动端单列；分组与计数由后端投影给出，前端不重算。
 * loading / empty / partial / error 全走 StatePanel。
 */

type IconComponent = typeof IconInfo;

interface StageMeta {
  key: DecisionStageKey;
  label: string;
  description: string;
  textClass: string;
  Icon: IconComponent;
}

const STAGE_META: Record<DecisionStageKey, StageMeta> = {
  needs_attention: {
    key: 'needs_attention',
    label: '需要关注',
    description: '已过有效期、72h 内到期或状态无法识别',
    textClass: 'text-risk',
    Icon: IconAlertTriangle,
  },
  awaiting_confirmation: {
    key: 'awaiting_confirmation',
    label: '等待确认',
    description: '建议已提出，等待你接受 / 拒绝 / 延迟',
    textClass: 'text-uncertainty',
    Icon: IconClock,
  },
  in_progress: {
    key: 'in_progress',
    label: '执行中',
    description: '已接受或行动已开始',
    textClass: 'text-primary',
    Icon: IconChevronRight,
  },
  awaiting_outcome: {
    key: 'awaiting_outcome',
    label: '等待结果',
    description: '行动已完成，尚未记录 Outcome',
    textClass: 'text-uncertainty',
    Icon: IconClock,
  },
  completed: {
    key: 'completed',
    label: '已完成',
    description: '已有结果记录，反馈闭环完成',
    textClass: 'text-verified',
    Icon: IconCheckCircle,
  },
  closed: {
    key: 'closed',
    label: '已关闭',
    description: '已延迟 / 已拒绝 / 已撤销 / 未执行',
    textClass: 'text-muted',
    Icon: IconArchive,
  },
};

/* ---------------- Decision Card ---------------- */

function DecisionCardView({ card }: { card: DecisionCard }) {
  const rid = card.recommendation_id ?? '';
  if (!rid) {
    // 无 ID 的卡片不可导航，但不崩（宽松渲染）
    return (
      <li className="rounded-lg border border-line bg-surface p-3 text-sm text-muted">
        一条建议缺少 recommendation_id，无法打开工作区。
      </li>
    );
  }
  return (
    <li>
      <Link
        to={`/decisions/${encodeURIComponent(rid)}`}
        className="block rounded-lg border border-line bg-surface p-3 transition-colors hover:border-primary focus:outline-none focus:ring-2 focus:ring-primary"
        aria-label={`打开决策工作区 ${rid}`}
      >
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm font-medium" title={`完整 ID：${rid}`}>
            {shortId(rid)}
          </span>
          <span className="badge border-line bg-panel text-muted">{card.domain ?? '未提供'}</span>
          <span className="badge border-candidate bg-candidate-soft text-candidate">
            {card.recommendation_kind ?? '未提供'}
          </span>
          {card.horizon ? <span className="badge border-line bg-panel text-muted">{card.horizon}</span> : null}
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <ConfirmationStateBadge state={card.confirmation_state} />
          <ActionStateBadge state={card.action_state} />
        </div>
        <p className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
          <span>置信度 {fmtConfidence(card.confidence)}</span>
          <span className="inline-flex items-center gap-1">
            <IconListOrdered className="h-3.5 w-3.5" />
            序号 <span className="font-mono">{fmtNumber(card.current_sequence)}</span>
          </span>
          <ExpiryText expiresAt={card.expires_at} />
        </p>
      </Link>
    </li>
  );
}

/* ---------------- 看板列 ---------------- */

function StageColumn({ meta, cards }: { meta: StageMeta; cards: DecisionCard[] }) {
  const Icon = meta.Icon;
  return (
    <section className="card flex h-full flex-col" aria-labelledby={`stage-${meta.key}-title`}>
      <div className="flex flex-wrap items-center gap-2">
        <h2 id={`stage-${meta.key}-title`} className={`flex items-center gap-1.5 font-semibold ${meta.textClass}`}>
          <Icon className="h-4 w-4" />
          {meta.label}
        </h2>
        <span className="badge border-line bg-panel text-muted">{cards.length} 条</span>
      </div>
      <p className="mt-0.5 text-xs text-muted">{meta.description}</p>
      {cards.length === 0 ? (
        <p className="mt-3 text-sm text-muted">无</p>
      ) : (
        <ul className="section-stack mt-3">
          {cards.map((card, index) => (
            <DecisionCardView key={card.recommendation_id ?? `card-${index}`} card={card} />
          ))}
        </ul>
      )}
    </section>
  );
}

/* ---------------- 页面 ---------------- */

function errorAuthorities(envelope: DecisionQueueEnvelope): string[] {
  return Object.entries(envelope.authorities)
    .filter(([, value]) => value === 'error')
    .map(([name]) => name);
}

export function DecisionCenterPage() {
  const query = useDecisionQueue();

  if (query.isPending) {
    return (
      <div className="section-stack" aria-label="决策中心加载中">
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
        title="决策中心加载失败"
        errorMessage={err.message}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const envelope = query.data;
  const { data } = envelope;
  const total = data.total_available ?? 0;

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
          <h1 className="text-lg font-semibold">决策中心</h1>
          <span className="badge border-line bg-panel text-muted">
            共 {fmtNumber(data.total_available)} 条建议
          </span>
        </div>
        <p className="mt-2 text-sm text-muted">
          六组看板按确认与行动状态分组；点击卡片进入决策工作区。分组与计数由只读投影给出。
        </p>
        <p className="mt-1 text-xs text-muted">投影生成于 {fmtTime(envelope.generated_at)}（每分钟自动刷新）</p>
      </header>

      {envelope.partial && total === 0 ? (
        // decision Authority 失败：data 退化为全零看板，按 partial 降级而非假空
        <StatePanel
          variant="partial"
          title="决策队列暂不可用"
          unavailableAuthorities={errorAuthorities(envelope)}
          description="决策 Authority 本次未返回数据，其余页面不受影响。"
        />
      ) : total === 0 ? (
        <StatePanel
          variant="empty"
          title="当前没有待决策事项"
          description="决策队列为空：没有需要确认、执行或跟踪的建议。"
          nextStep="可从顶栏「新建决策」发起一个 Guarded 决策会话，或先在日常对话中积累个人事实。"
        />
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {DECISION_STAGE_KEYS.map((key) => (
            <StageColumn key={key} meta={STAGE_META[key]} cards={data.stages[key] ?? []} />
          ))}
        </div>
      )}
    </div>
  );
}
