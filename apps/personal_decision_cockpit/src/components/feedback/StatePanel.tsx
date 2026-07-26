import { IconAlertTriangle, IconArrowLeftRight, IconClock, IconInfo, IconRefresh, IconXCircle } from '../icons';

/**
 * 统一状态面板（spec §12）：loading / empty / partial / error / offline / stale / conflict
 * 七态。empty、partial、stale、offline、conflict 是彼此独立的用户可见状态（Phase 37 D-37-03）：
 * 绝不能把"整个同源 API 不可达"（offline）、"authority 部分失败"（partial）和
 * "查询本身失败"（error）混成同一种提示，也不能把 stale/conflict 记录状态伪装成普通成功。
 * 颜色必须配文字 + 图标；error/offline 使用 role="alert"；禁止空白页和静默失败。
 */
export interface StatePanelProps {
  variant: 'loading' | 'empty' | 'partial' | 'error' | 'offline' | 'stale' | 'conflict';
  /** 面板标题，各态有默认文案 */
  title?: string;
  /** 补充说明（empty：为什么为空；offline：只读缓存范围说明；stale/conflict：附加说明） */
  description?: string;
  /** 下一步建议（empty） */
  nextStep?: string;
  /** partial：不可用的 Authority 名称列表 */
  unavailableAuthorities?: string[];
  /** error/offline：规范化错误信息（不含 payload） */
  errorMessage?: string;
  /** error/offline：提供后出现“重试”按钮 */
  onRetry?: () => void;
  /** stale：服务端给出的数据时间展示文本（调用方已用 fmtTime 格式化，组件不推断新鲜度） */
  asOfText?: string;
  /** conflict：冲突条目简述列表（不自动选择一边，只陈述冲突项） */
  conflictItems?: string[];
}

export function StatePanel({
  variant,
  title,
  description,
  nextStep,
  unavailableAuthorities = [],
  errorMessage,
  onRetry,
  asOfText,
  conflictItems = [],
}: StatePanelProps) {
  if (variant === 'loading') {
    return (
      <div className="card" aria-busy="true" aria-label="加载中">
        <div className="animate-pulse space-y-3">
          <div className="h-4 w-1/3 rounded bg-line" />
          <div className="h-3 w-2/3 rounded bg-line" />
          <div className="h-3 w-1/2 rounded bg-line" />
        </div>
      </div>
    );
  }

  if (variant === 'error') {
    return (
      <div className="card border-risk bg-risk-soft" role="alert">
        <div className="flex items-start gap-3">
          <IconXCircle className="mt-0.5 h-5 w-5 shrink-0 text-risk" />
          <div className="min-w-0 flex-1">
            <p className="font-medium text-risk">{title ?? '加载失败'}</p>
            {errorMessage ? <p className="mt-1 text-sm text-muted">{errorMessage}</p> : null}
            {onRetry ? (
              <button
                type="button"
                onClick={onRetry}
                className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-risk px-3 py-1.5 text-sm text-risk transition-colors hover:bg-risk-soft focus:outline-none focus:ring-2 focus:ring-risk"
              >
                <IconRefresh className="h-4 w-4" />
                重试
              </button>
            ) : null}
          </div>
        </div>
      </div>
    );
  }

  if (variant === 'offline') {
    // 整个同源 API 不可达（如 network_error）：与"单条查询失败"（error）区分开，
    // 明确说明当前无法确认任何权威的最新状态，但不代表数据已被清空（spec §12 Offline 行）。
    return (
      <div className="card border-risk bg-risk-soft" role="alert">
        <div className="flex items-start gap-3">
          <IconAlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-risk" />
          <div className="min-w-0 flex-1">
            <p className="font-medium text-risk">{title ?? '服务当前不可达'}</p>
            {errorMessage ? <p className="mt-1 text-sm text-muted">{errorMessage}</p> : null}
            <p className="mt-1 text-sm text-muted">
              {description ?? '本地服务未响应，当前无法确认任何权威的最新状态；这不代表数据已被清空。'}
            </p>
            {onRetry ? (
              <button
                type="button"
                onClick={onRetry}
                className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-risk px-3 py-1.5 text-sm text-risk transition-colors hover:bg-risk-soft focus:outline-none focus:ring-2 focus:ring-risk"
              >
                <IconRefresh className="h-4 w-4" />
                重试
              </button>
            ) : null}
          </div>
        </div>
      </div>
    );
  }

  if (variant === 'stale') {
    // 记录/快照偏旧：显示更新时间和重新同步入口，而非静默展示旧数据为"当前"（spec §12 Stale 行）
    return (
      <div className="card border-uncertainty bg-uncertainty-soft" role="status">
        <div className="flex items-start gap-3">
          <IconClock className="mt-0.5 h-5 w-5 shrink-0 text-uncertainty" />
          <div className="min-w-0 flex-1">
            <p className="font-medium text-uncertainty">{title ?? '数据已偏旧'}</p>
            {asOfText ? <p className="mt-1 text-sm text-muted">数据时间：{asOfText}</p> : null}
            <p className="mt-1 text-sm text-muted">{description ?? '如需最新结果，请手动刷新或重新同步。'}</p>
            {onRetry ? (
              <button
                type="button"
                onClick={onRetry}
                className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-uncertainty px-3 py-1.5 text-sm text-uncertainty transition-colors hover:bg-uncertainty-soft focus:outline-none focus:ring-2 focus:ring-uncertainty"
              >
                <IconRefresh className="h-4 w-4" />
                重新同步
              </button>
            ) : null}
          </div>
        </div>
      </div>
    );
  }

  if (variant === 'conflict') {
    // 冲突记录：只陈述冲突，不自动选择一边（spec §12 Conflict 行）
    return (
      <div className="card border-risk bg-risk-soft" role="status">
        <div className="flex items-start gap-3">
          <IconArrowLeftRight className="mt-0.5 h-5 w-5 shrink-0 text-risk" />
          <div className="min-w-0 flex-1">
            <p className="font-medium text-risk">{title ?? '存在冲突记录'}</p>
            {conflictItems.length > 0 ? (
              <ul className="mt-2 list-disc pl-5 text-sm text-muted">
                {conflictItems.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : null}
            <p className="mt-2 text-sm text-muted">{description ?? '系统不会自动选择一边，请人工核对后再决定。'}</p>
          </div>
        </div>
      </div>
    );
  }

  if (variant === 'partial') {
    return (
      <div className="card border-uncertainty bg-uncertainty-soft">
        <div className="flex items-start gap-3">
          <IconAlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-uncertainty" />
          <div className="min-w-0 flex-1">
            <p className="font-medium text-uncertainty">{title ?? '部分数据暂不可用'}</p>
            {unavailableAuthorities.length > 0 ? (
              <div className="mt-2">
                <p className="text-sm text-muted">以下 Authority 暂不可用：</p>
                <ul className="mt-1 list-disc pl-5 text-sm text-muted">
                  {unavailableAuthorities.map((name) => (
                    <li key={name}>{name}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {description ? <p className="mt-1 text-sm text-muted">{description}</p> : null}
          </div>
        </div>
      </div>
    );
  }

  // empty
  return (
    <div className="card border-line">
      <div className="flex items-start gap-3">
        <IconInfo className="mt-0.5 h-5 w-5 shrink-0 text-muted" />
        <div className="min-w-0 flex-1">
          <p className="font-medium text-ink">{title ?? '暂无数据'}</p>
          {description ? <p className="mt-1 text-sm text-muted">{description}</p> : null}
          {nextStep ? <p className="mt-1 text-sm text-muted">下一步：{nextStep}</p> : null}
        </div>
      </div>
    </div>
  );
}
