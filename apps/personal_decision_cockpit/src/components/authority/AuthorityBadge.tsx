// Authority 来源徽标（spec §8）：五色 + 文字，颜色不是唯一提示。

const AUTHORITY_META = {
  personal: { label: '个人状态', color: 'var(--color-primary)', bg: 'var(--color-primary-soft)' },
  external: { label: '外部环境', color: 'var(--color-external)', bg: 'var(--color-external-soft)' },
  analysis: { label: '决策分析', color: 'var(--color-llm-candidate)', bg: 'var(--color-llm-candidate-soft)' },
  pilot: { label: '项目试点', color: 'var(--color-uncertainty)', bg: 'var(--color-uncertainty-soft)' },
  calibration: { label: '推荐校准', color: 'var(--color-verified)', bg: 'var(--color-verified-soft)' },
} as const;

export type AuthorityKind = keyof typeof AUTHORITY_META;

export function AuthorityBadge({ authority }: { authority: AuthorityKind }) {
  const meta = AUTHORITY_META[authority];
  return (
    <span
      className="badge"
      style={{ color: meta.color, backgroundColor: meta.bg, borderColor: meta.color }}
    >
      {meta.label}
    </span>
  );
}
