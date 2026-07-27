import { canRetrySamePreview } from '../../api/orchestration';
import { IconAlertTriangle, IconCheckCircle, IconRefresh, IconXCircle } from '../icons';

/**
 * 分类恢复面板（spec §8 TypedRecoveryPanel / §12 状态模型，Phase 38-03 收口）：
 * 按 error.code/category 分类渲染恢复路径；replayed=true 显示 Replay 状态
 * "已返回原事件，未重复写入"。
 * 输入只含规范化错误字段（code/category/message/retryable/recovery_actions），不含 payload。
 *
 * 重试 CTA 的 fail-closed 边界（T-38-09 自动重试防线，组件层兜底）：
 * 服务端 `retryable=true` 只表示"类别整体非致命"，不代表原样重发同一 preview + 幂等键安全。
 * 即便调用方误传了 onRetry，本组件也只在 `canRetrySamePreview`（recovery_actions 含
 * retry_when_ready 且非 actor_identity_mismatch，目前仅 runtime 类）时渲染"重试"按钮；
 * stale/confirmation/sequence/conflict/integrity/risk/unknown_outcome 一律不出现重试 CTA，
 * 只提供 resume 只读恢复与人工路径。本组件自身不发起任何网络请求。
 */

export interface RecoveryError {
  code: string;
  category: string;
  message: string;
  retryable: boolean;
  recoveryActions: string[];
}

export interface TypedRecoveryPanelProps {
  /** 规范化写入错误；与 replayed 二选一 */
  error?: RecoveryError | null;
  /** Replay 状态（spec §12）：服务端命中幂等键，返回原事件 */
  replayed?: boolean;
  /** retryable 时渲染"重试"按钮（同一 preview + 同一幂等键，安全重放） */
  onRetry?: () => void;
  /** 提供后渲染"恢复会话状态"按钮（GET /agent/session/resume） */
  onResume?: () => void;
  /** 操作名称，用于标题（如 记录决策） */
  operationLabel?: string;
}

/** error.code → 特定恢复说明（已知服务端限制必须给出明确路径） */
function codeSpecificNote(code: string): string | null {
  switch (code) {
    case 'confirmation_secret_unavailable':
      return '服务端未配置编排确认密钥：请在 rag-api 运行环境中设置 PERSONAL_DATA_ORCHESTRATION_SECRET（≥32 字节随机值）并重启服务，然后重新发起 prepare。';
    case 'generation_provider_unavailable':
      return '当前 stock 服务未配置 generation runner，generate 步骤无法执行：需在服务端注入 generation_runner 后才能继续；本会话保持 confirmed 状态，不会中断。';
    case 'idempotency_conflict':
      return '不可重试：同一幂等键对应了不同的请求内容，写入已被拒绝以保护事件链。请恢复会话核对当前状态，更换幂等键并重新 preview。';
    case 'route_operation_mismatch':
      return 'preview 的 operation 与执行路由不一致，请求已被服务端拒绝。请重新生成 preview 后再确认执行。';
    case 'actor_identity_mismatch':
      return '会话绑定的操作者身份哈希与当前页面不一致（前端不持久化身份，页面刷新后会更换）。该会话只能只读查看，无法继续推进；如需推进请新建会话。';
    case 'stale_expected_sequence':
      return '会话已被其他写入推进，expected_sequence 已过期。请恢复会话获取最新 sequence 后重新 preview。';
    case 'session_missing':
      return '会话不存在：请核对 session_id 是否完整（可从写入成功结果中复制）。';
    case 'provider_outcome_unknown':
      return 'Provider 执行结果未知：可能已产生真实副作用，自动重试不安全（可能造成重复调用）。请先恢复会话查看只读状态、检查 provider 预留的执行结果，人工确认后再决定下一步。';
    default:
      return null;
  }
}

/** error.category → 类别级稳定说明（code 未命中专项说明时兜底，保证每类都有明确恢复方向） */
function categorySpecificNote(category: string): string | null {
  switch (category) {
    case 'unknown_outcome':
      return 'Provider 结果未知类：浏览器不会自动重试，也不需要更换幂等键；只允许恢复会话（只读）、检查 provider 预留与人工复核。';
    case 'integrity':
      return '完整性校验失败类：事件链或校验和不一致，禁止任何重试或继续写入。请检查对应 Authority 的完整性并人工复核。';
    case 'risk':
      return '风险边界类：请求超出低风险 project 域许可，服务端已拒绝。请缩小请求范围或人工复核，不要原样重发。';
    case 'confirmation':
      return '确认凭据类：确认已缺失、过期、被消费或与 preview 不匹配。请恢复会话后基于最新状态重新生成 preview 并再次显式确认，不要重发旧请求。';
    case 'sequence':
      return '序列/状态类：expected_sequence 或 transition 与当前状态不符。请恢复会话核对最新 sequence 后重新 preview。';
    case 'stale':
      return '过期类：请求所基于的状态已过时。请恢复会话获取最新状态后重新 preview，不要原样重发旧 preview。';
    case 'conflict':
      return '冲突类：与既有不可变记录冲突，写入已被拒绝以保护事件链。请恢复会话核对状态，人工确认后再决定下一步。';
    default:
      return null;
  }
}

/** recovery_actions 代码 → 中文说明（未知代码原样展示，不隐瞒） */
const RECOVERY_ACTION_LABELS: Record<string, string> = {
  verify_id: '核对记录 ID 是否完整正确',
  list_available: '列出可用记录后重新选择',
  resume_session: '恢复会话，核对当前 state 与 sequence',
  use_original_idempotency_key: '使用原幂等键重试（安全重放）',
  manual_review: '人工核查后再决定下一步',
  prepare_fresh_preview: '基于最新状态重新生成 preview',
  confirm_again: '重新显式确认',
  reduce_scope: '缩小请求范围（仅限低风险 project 域）',
  inspect_authority: '检查对应 Authority 的完整性',
  check_runtime: '检查本地运行态（rag-api / 数据库 / 密钥配置）',
  retry_when_ready: '运行态就绪后重试',
  inspect_provider_reservation: '检查 provider 预留的执行结果',
};

export function TypedRecoveryPanel({ error, replayed, onRetry, onResume, operationLabel }: TypedRecoveryPanelProps) {
  // Replay 不是错误：幂等命中，服务端返回原事件（spec §12 Replay 态）
  if (replayed) {
    return (
      <div className="card border-verified bg-verified-soft" role="status">
        <div className="flex items-start gap-3">
          <IconCheckCircle className="mt-0.5 h-5 w-5 shrink-0 text-verified" />
          <div className="min-w-0 flex-1">
            <p className="font-medium text-verified">已返回原事件，未重复写入</p>
            <p className="mt-1 text-sm text-muted">
              服务端命中相同幂等键，本次请求是安全重放（exact replay），事件链没有新增重复记录。
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (!error) return null;

  const note = codeSpecificNote(error.code) ?? categorySpecificNote(error.category);
  // fail-closed：即便调用方传了 onRetry，也只有 canRetrySamePreview 允许时才渲染重试 CTA
  const showRetry = error.retryable && Boolean(onRetry) && canRetrySamePreview(error);

  return (
    <div className="card border-risk bg-risk-soft" role="alert">
      <div className="flex items-start gap-3">
        <IconXCircle className="mt-0.5 h-5 w-5 shrink-0 text-risk" />
        <div className="min-w-0 flex-1">
          <p className="font-medium text-risk">
            {operationLabel ? `「${operationLabel}」未完成` : '写入未完成'}
          </p>
          <p className="mt-1 flex flex-wrap items-center gap-2 text-xs">
            <span className="badge border-risk bg-panel font-mono text-risk">{error.code}</span>
            <span className="badge border-line bg-panel text-muted">分类：{error.category}</span>
            {canRetrySamePreview(error) ? (
              <span className="badge border-uncertainty bg-uncertainty-soft text-uncertainty">可重试</span>
            ) : (
              <span className="badge border-risk bg-panel text-risk">不可自动重试</span>
            )}
          </p>
          <p className="mt-2 text-sm text-muted">{error.message}</p>

          {note ? (
            <p className="mt-2 flex items-start gap-1.5 text-sm text-uncertainty">
              <IconAlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{note}</span>
            </p>
          ) : null}

          {error.recoveryActions.length > 0 ? (
            <div className="mt-2">
              <p className="text-sm font-medium">建议的恢复路径：</p>
              <ul className="mt-1 list-disc pl-5 text-sm text-muted">
                {error.recoveryActions.map((action) => (
                  <li key={action}>
                    {RECOVERY_ACTION_LABELS[action] ?? action}
                    <span className="ml-1 font-mono text-xs text-muted">({action})</span>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {showRetry || onResume ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {showRetry ? (
                <button
                  type="button"
                  onClick={onRetry}
                  className="inline-flex items-center gap-1.5 rounded-md border border-risk px-3 py-1.5 text-sm text-risk transition-colors hover:bg-risk-soft focus:outline-none focus:ring-2 focus:ring-risk"
                >
                  <IconRefresh className="h-4 w-4" />
                  重试（同一 preview 与幂等键）
                </button>
              ) : null}
              {onResume ? (
                <button
                  type="button"
                  onClick={onResume}
                  className="inline-flex items-center gap-1.5 rounded-md border border-line bg-panel px-3 py-1.5 text-sm text-ink transition-colors hover:bg-surface focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  <IconRefresh className="h-4 w-4" />
                  恢复会话状态
                </button>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
