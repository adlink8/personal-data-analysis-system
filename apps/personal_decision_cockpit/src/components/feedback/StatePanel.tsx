import { IconAlertTriangle, IconInfo, IconRefresh, IconXCircle } from '../icons';

/**
 * 统一状态面板（spec §12）：loading skeleton / empty / partial / error。
 * 颜色必须配文字 + 图标；error 使用 role="alert"；禁止空白页和静默失败。
 */
export interface StatePanelProps {
  variant: 'loading' | 'empty' | 'partial' | 'error';
  /** 面板标题，各态有默认文案 */
  title?: string;
  /** 补充说明（empty：为什么为空） */
  description?: string;
  /** 下一步建议（empty） */
  nextStep?: string;
  /** partial：不可用的 Authority 名称列表 */
  unavailableAuthorities?: string[];
  /** error：规范化错误信息（不含 payload） */
  errorMessage?: string;
  /** error：提供后出现“重试”按钮 */
  onRetry?: () => void;
}

export function StatePanel({
  variant,
  title,
  description,
  nextStep,
  unavailableAuthorities = [],
  errorMessage,
  onRetry,
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
