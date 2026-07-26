// Authority 来源徽标（spec §8/§9.2）：五色 + 文字 + 图标，颜色不是唯一提示。
import {
  IconCheckCircle,
  IconClock,
  IconEye,
  IconInfo,
  IconSparkles,
} from '../icons';

const AUTHORITY_META = {
  personal: { label: '个人状态', color: 'var(--color-primary)', bg: 'var(--color-primary-soft)', Icon: IconEye },
  external: { label: '外部环境', color: 'var(--color-external)', bg: 'var(--color-external-soft)', Icon: IconInfo },
  analysis: {
    label: '决策分析',
    color: 'var(--color-llm-candidate)',
    bg: 'var(--color-llm-candidate-soft)',
    Icon: IconSparkles,
  },
  pilot: { label: '项目试点', color: 'var(--color-uncertainty)', bg: 'var(--color-uncertainty-soft)', Icon: IconClock },
  calibration: {
    label: '推荐校准',
    color: 'var(--color-verified)',
    bg: 'var(--color-verified-soft)',
    Icon: IconCheckCircle,
  },
} as const;

export type AuthorityKind = keyof typeof AUTHORITY_META;

export function AuthorityBadge({ authority }: { authority: AuthorityKind }) {
  const meta = AUTHORITY_META[authority];
  const Icon = meta.Icon;
  return (
    <span
      className="badge"
      style={{ color: meta.color, backgroundColor: meta.bg, borderColor: meta.color }}
    >
      <Icon className="h-3.5 w-3.5" />
      {meta.label}
    </span>
  );
}
