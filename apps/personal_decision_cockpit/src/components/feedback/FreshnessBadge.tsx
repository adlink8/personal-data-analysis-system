import { IconAlertTriangle, IconCheckCircle, IconClock, IconInfo } from '../icons';
import { fmtTime } from '../../utils/format';

/**
 * 数据新鲜度徽标（spec §8，Phase 37 D-37 教训修正）：只呈现服务端派生的 level/reason，
 * 不再用浏览器 <24h/<7d 阈值臆造行动相关的新鲜度判定（RESEARCH.md 架构模式 2）。
 *
 * `level` 词表与 external_delta.get 的 `fact.freshness.level`（`_FRESHNESS_LEVELS`）一致：
 * unknown / valid / expiring_soon / expired。当前只有 External fact 这条读路径由服务端
 * 显式计算并暴露该字段；Personal snapshot 的 as_of、External snapshot 的 generated_at
 * 等场景服务端未提供对应 level，调用方应省略 `level`（组件回退为 unknown/"未分级"，
 * 只展示原始时间戳，不据此臆造"新鲜"或"过期"）。
 */

export type FreshnessLevel = 'unknown' | 'valid' | 'expiring_soon' | 'expired';

const LEVEL_META: Record<
  FreshnessLevel,
  { label: string; textClass: string; Icon: typeof IconInfo }
> = {
  valid: { label: '新鲜', textClass: 'text-verified', Icon: IconCheckCircle },
  expiring_soon: { label: '即将过期', textClass: 'text-uncertainty', Icon: IconClock },
  expired: { label: '已过期', textClass: 'text-risk', Icon: IconAlertTriangle },
  unknown: { label: '未分级', textClass: 'text-muted', Icon: IconInfo },
};

export interface FreshnessBadgeProps {
  /** 服务端派生的新鲜度分级（如 fact.freshness.level）；未提供时不臆造判定 */
  level?: FreshnessLevel | null;
  /** 服务端给出的分级理由（如 fact.freshness.reason）；无则不展示额外说明 */
  reason?: string | null;
  /** 展示用时间戳：仅格式化显示，不作为计算 level 的输入 */
  asOf?: string | null;
}

export function FreshnessBadge({ level, reason, asOf }: FreshnessBadgeProps) {
  const resolvedLevel: FreshnessLevel = level ?? 'unknown';
  const { label, textClass, Icon } = LEVEL_META[resolvedLevel];
  const timeText = asOf ? fmtTime(asOf) : '无时间戳';
  const titleText = reason ? `${label}：${reason}` : `数据时间 ${timeText}`;
  return (
    <span className={`badge border-line bg-panel ${textClass}`} title={titleText}>
      <Icon className="h-3.5 w-3.5" />
      <span>{label}</span>
      <span className="text-muted">{timeText}</span>
    </span>
  );
}
