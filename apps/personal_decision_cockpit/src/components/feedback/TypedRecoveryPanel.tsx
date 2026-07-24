import { IconAlertTriangle, IconCheckCircle, IconRefresh, IconXCircle } from '../icons';

/**
 * 分类恢复面板（spec §8 TypedRecoveryPanel / §12 状态模型）：
 * 按 error.code 分类渲染恢复路径；retryable 时给"重试"；
 * replayed=true 显示 Replay 状态"已返回原事件，未重复写入"。
 * 输入只含规范化错误字段（code/category/message/retryable/recovery_actions），不含 payload。
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

  const note = codeSpecificNote(error.code);
  const showRetry = error.retryable && Boolean(onRetry);

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
            {error.retryable ? (
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
