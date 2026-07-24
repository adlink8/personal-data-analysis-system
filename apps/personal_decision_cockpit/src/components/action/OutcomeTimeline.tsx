import type { ActionTimelineStage } from '../../api/schemas';
import { ACTION_TIMELINE_STAGES } from '../../api/schemas';
import { fmtNumber } from '../../utils/format';
import { shortId } from '../authority/SnapshotChip';
import { IconCheckCircle } from '../icons';

/**
 * OutcomeTimeline（spec §7.4 / §8）：六节点纵向时间线
 * 建议 → 决策 → 行动开始 → 行动完成 → 结果 → 效果评估。
 * 按固定阶段顺序渲染（后端契约六键恒在；缺某键按未达成 + 字段"未提供"宽松降级）：
 * 节点显示阶段中文名、present 状态（达成=绿色勾"已达成"/未达=灰点"未达成"，颜色配文字）、
 * event_id 短码、sequence、checksum 短码（等宽，完整值放 title）；节点间竖向连线。
 */

const STAGE_LABELS: Record<string, string> = {
  recommendation: '建议',
  decision: '决策',
  action_start: '行动开始',
  action_complete: '行动完成',
  outcome: '结果',
  effectiveness: '效果评估',
};

function StageNode({ entry, stageKey, isLast }: { entry: ActionTimelineStage | null; stageKey: string; isLast: boolean }) {
  const present = entry?.present === true;
  return (
    <li className="relative flex gap-3 pb-4 last:pb-0">
      {/* 节点间竖向连线 */}
      {!isLast ? <span aria-hidden className="absolute left-[11px] top-6 bottom-0 w-px bg-line" /> : null}
      <span
        className={`relative z-10 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border ${
          present ? 'border-verified bg-verified-soft text-verified' : 'border-line bg-panel text-muted'
        }`}
      >
        {present ? (
          <IconCheckCircle className="h-4 w-4" />
        ) : (
          <span aria-hidden className="h-2 w-2 rounded-full bg-line" />
        )}
      </span>
      <div className="min-w-0 flex-1">
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <span className="font-medium">{STAGE_LABELS[stageKey] ?? stageKey}</span>
          <span className={present ? 'text-verified' : 'text-muted'}>{present ? '已达成' : '未达成'}</span>
        </p>
        <dl className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-muted">
          <div className="break-all">
            <dt className="inline">event_id：</dt>
            <dd className="inline font-mono" title={entry?.event_id ?? undefined}>
              {entry?.event_id ? shortId(entry.event_id, 20) : '未提供'}
            </dd>
          </div>
          <div>
            <dt className="inline">sequence：</dt>
            <dd className="inline font-mono">
              {entry?.sequence === null || entry?.sequence === undefined ? '未提供' : fmtNumber(entry.sequence)}
            </dd>
          </div>
          <div className="break-all">
            <dt className="inline">checksum：</dt>
            <dd className="inline font-mono" title={entry?.checksum ?? undefined}>
              {entry?.checksum ? shortId(entry.checksum, 16) : '未提供'}
            </dd>
          </div>
        </dl>
      </div>
    </li>
  );
}

export function OutcomeTimeline({ stages }: { stages: ActionTimelineStage[] }) {
  return (
    <ol aria-label="行动结果时间线">
      {ACTION_TIMELINE_STAGES.map((stageKey, index) => (
        <StageNode
          key={stageKey}
          stageKey={stageKey}
          entry={stages.find((stage) => stage.stage === stageKey) ?? null}
          isLast={index === ACTION_TIMELINE_STAGES.length - 1}
        />
      ))}
    </ol>
  );
}
