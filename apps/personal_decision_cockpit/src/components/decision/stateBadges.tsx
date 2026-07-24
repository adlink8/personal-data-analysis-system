// 决策双状态徽标与到期强调（spec §7.3）：
// confirmation_state / action_state 真实词汇来自 decision state_machine；
// 颜色一律配文字 + 图标，非纯色（spec §9.2）。
import {
  IconAlertTriangle,
  IconArchive,
  IconCheckCircle,
  IconChevronRight,
  IconClock,
  IconInfo,
  IconXCircle,
} from '../icons';
import { fmtTime } from '../../utils/format';

type IconComponent = typeof IconInfo;

interface StateMeta {
  label: string;
  badgeClass: string;
  Icon: IconComponent;
}

/** confirmation_state ∈ proposed / accepted / rejected / deferred / revoked */
const CONFIRMATION_META: Record<string, StateMeta> = {
  proposed: { label: '待确认', badgeClass: 'border-uncertainty bg-uncertainty-soft text-uncertainty', Icon: IconClock },
  accepted: { label: '已接受', badgeClass: 'border-verified bg-verified-soft text-verified', Icon: IconCheckCircle },
  rejected: { label: '已拒绝', badgeClass: 'border-risk bg-risk-soft text-risk', Icon: IconXCircle },
  deferred: { label: '已延迟', badgeClass: 'border-line bg-panel text-muted', Icon: IconClock },
  revoked: { label: '已撤销', badgeClass: 'border-line bg-panel text-muted', Icon: IconArchive },
};

/** action_state ∈ null / planned / started / completed / abandoned / not_taken */
const ACTION_META: Record<string, StateMeta> = {
  planned: { label: '已计划', badgeClass: 'border-primary bg-primary-soft text-primary', Icon: IconInfo },
  started: { label: '执行中', badgeClass: 'border-primary bg-primary-soft text-primary', Icon: IconChevronRight },
  completed: { label: '行动已完成', badgeClass: 'border-verified bg-verified-soft text-verified', Icon: IconCheckCircle },
  abandoned: { label: '已放弃', badgeClass: 'border-line bg-panel text-muted', Icon: IconArchive },
  not_taken: { label: '未执行', badgeClass: 'border-line bg-panel text-muted', Icon: IconArchive },
};

export function ConfirmationStateBadge({ state }: { state: string | null | undefined }) {
  const key = state ?? '';
  const meta = CONFIRMATION_META[key] ?? {
    label: key || '未提供',
    badgeClass: 'border-line bg-panel text-muted',
    Icon: IconInfo,
  };
  const Icon = meta.Icon;
  return (
    <span className={`badge ${meta.badgeClass}`} title={`确认状态：${meta.label}`}>
      <Icon className="h-3.5 w-3.5" />
      {meta.label}
    </span>
  );
}

export function ActionStateBadge({ state }: { state: string | null | undefined }) {
  if (!state) {
    return (
      <span className="badge border-line bg-panel text-muted" title="行动状态：未开始行动">
        <IconInfo className="h-3.5 w-3.5" />
        未开始行动
      </span>
    );
  }
  const meta = ACTION_META[state] ?? { label: state, badgeClass: 'border-line bg-panel text-muted', Icon: IconInfo };
  const Icon = meta.Icon;
  return (
    <span className={`badge ${meta.badgeClass}`} title={`行动状态：${meta.label}`}>
      <Icon className="h-3.5 w-3.5" />
      {meta.label}
    </span>
  );
}

/* ---------------- 到期强调 ---------------- */

export type ExpiryLevel = 'unknown' | 'expired' | 'soon' | 'normal';

/** 与后端 needs_attention 判定同窗口：已过 / 无法解析 / 72h 内到期 → amber 强调 */
export function expiryLevel(expiresAt: string | null | undefined, now: number = Date.now()): ExpiryLevel {
  if (!expiresAt) return 'unknown';
  const ts = Date.parse(expiresAt);
  if (Number.isNaN(ts)) return 'unknown';
  if (ts <= now) return 'expired';
  if (ts - now <= 72 * 3_600_000) return 'soon';
  return 'normal';
}

const EXPIRY_META: Record<ExpiryLevel, { label: string; textClass: string; emphasize: boolean }> = {
  unknown: { label: '到期时间未知', textClass: 'text-uncertainty', emphasize: true },
  expired: { label: '已过期', textClass: 'text-uncertainty', emphasize: true },
  soon: { label: '临近到期', textClass: 'text-uncertainty', emphasize: true },
  normal: { label: '', textClass: 'text-muted', emphasize: false },
};

/** expires_at 展示：临近/已过/未知用 amber 强调并附文字标注 */
export function ExpiryText({ expiresAt }: { expiresAt: string | null | undefined }) {
  const level = expiryLevel(expiresAt);
  const meta = EXPIRY_META[level];
  return (
    <span className={`inline-flex items-center gap-1 ${meta.textClass}`}>
      {meta.emphasize ? <IconAlertTriangle className="h-3.5 w-3.5 shrink-0" /> : <IconClock className="h-3.5 w-3.5 shrink-0" />}
      {meta.emphasize ? <span className="font-medium">{meta.label}</span> : null}
      <span>{expiresAt ? fmtTime(expiresAt) : '未提供'}</span>
    </span>
  );
}
