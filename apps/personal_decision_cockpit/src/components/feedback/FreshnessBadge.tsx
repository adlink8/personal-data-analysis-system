import { IconAlertTriangle, IconCheckCircle, IconInfo } from '../icons';
import { fmtTime } from '../../utils/format';

// 数据新鲜度徽标：current / stale / expired / unknown 四态（spec §8），图标 + 文字。

export type FreshnessLevel = 'current' | 'stale' | 'expired' | 'unknown';

/** 由 as_of 计算新鲜度档位：<24h 新鲜，<7d 偏旧，其余已过期 */
export function computeFreshness(asOf: string | null, now: number = Date.now()): FreshnessLevel {
  if (!asOf) return 'unknown';
  const ts = Date.parse(asOf);
  if (Number.isNaN(ts)) return 'unknown';
  const ageHours = (now - ts) / 3_600_000;
  if (ageHours < 24) return 'current';
  if (ageHours < 24 * 7) return 'stale';
  return 'expired';
}

const LEVEL_META: Record<
  FreshnessLevel,
  { label: string; textClass: string; Icon: typeof IconInfo }
> = {
  current: { label: '新鲜', textClass: 'text-verified', Icon: IconCheckCircle },
  stale: { label: '偏旧', textClass: 'text-uncertainty', Icon: IconAlertTriangle },
  expired: { label: '已过期', textClass: 'text-risk', Icon: IconAlertTriangle },
  unknown: { label: '未知', textClass: 'text-muted', Icon: IconInfo },
};

export function FreshnessBadge({ asOf }: { asOf: string | null }) {
  const level = computeFreshness(asOf);
  const { label, textClass, Icon } = LEVEL_META[level];
  const timeText = asOf ? fmtTime(asOf) : '无时间戳';
  return (
    <span
      className={`badge border-line bg-panel ${textClass}`}
      title={`数据更新于 ${timeText}`}
    >
      <Icon className="h-3.5 w-3.5" />
      <span>{label}</span>
      <span className="text-muted">{timeText}</span>
    </span>
  );
}
