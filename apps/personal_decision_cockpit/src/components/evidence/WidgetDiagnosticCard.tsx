import { useEffect, useState } from 'react';
import { IconAlertTriangle, IconClock, IconRefresh } from '../icons';

/**
 * 遗留 MCP Widget 的诊断容器（Phase 37 Plan 03 Task 3，D-37-06）：把 Data Browser /
 * Memory Graph / Relation Review 收口为明确的、受限的诊断/历史集成，而不是当前
 * Personal State 权威。三条防线：
 * 1. Widget URL 只能来自本文件写死的 ALLOWED_WIDGET_ORIGIN（不接受任意来源拼接）；
 * 2. iframe 使用最小 sandbox（仅 allow-scripts，不含 allow-same-origin / 允许顶层导航 /
 *    弹窗 / 下载 / 表单）与 referrerPolicy="no-referrer"；
 * 3. Widget 不可用（同源 system status 判定 MCP 端口未监听，或加载超时）时始终渲染
 *    非空的 recovery card（状态 + 限制 + 重试 / 新窗口诊断链接），iframe 正常 load
 *    也只是清除"尚未确认加载"提示，绝不被当作 authoritative success。
 */

/** Widget 允许的唯一来源：与旧 EvidencePage 硬编码的 MCP 服务地址一致，不接受动态覆盖 */
const ALLOWED_WIDGET_ORIGIN = 'http://127.0.0.1:8789';

/** 组装 Widget URL 并校验落在允许 origin 内；校验失败返回 null（防御性 allowlist，即使当前是编译期常量） */
function widgetUrl(file: string): string | null {
  const url = `${ALLOWED_WIDGET_ORIGIN}/widgets/${file}`;
  return url.startsWith(`${ALLOWED_WIDGET_ORIGIN}/`) ? url : null;
}

export interface WidgetDiagnosticCardProps {
  /** Widget 文件名（如 data-browser-widget.html） */
  file: string;
  title: string;
  description: string;
  /** 明确标注为历史/诊断而非当前 Personal State SSOT 时提供（如 Memory Graph） */
  historicalNote?: string | null;
  /** 同源 system status 判定的 MCP 服务可达性；null = 未知（system status 本身不可用/仍在加载），不视为已确认不可达 */
  mcpAvailable: boolean | null;
  /** 受控加载超时（毫秒）：默认 4000，测试可传入更短值 */
  loadTimeoutMs?: number;
}

export function WidgetDiagnosticCard({
  file,
  title,
  description,
  historicalNote,
  mcpAvailable,
  loadTimeoutMs = 4000,
}: WidgetDiagnosticCardProps) {
  const [loaded, setLoaded] = useState(false);
  const [timedOut, setTimedOut] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const url = widgetUrl(file);
  const knownUnavailable = mcpAvailable === false || url === null;

  // 受控超时：已知不可达时不再等待；否则每次"重试"重新计时
  useEffect(() => {
    if (knownUnavailable) return;
    setLoaded(false);
    setTimedOut(false);
    const timer = window.setTimeout(() => setTimedOut(true), loadTimeoutMs);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt, knownUnavailable, loadTimeoutMs]);

  return (
    <section className="card flex flex-col gap-2" aria-labelledby={`widget-${file}`}>
      <div className="flex items-start justify-between gap-2">
        <h3 id={`widget-${file}`} className="font-medium">
          {title}
        </h3>
        {url ? (
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="shrink-0 text-sm text-primary hover:underline focus:outline-none focus:ring-2 focus:ring-primary"
          >
            在新窗口打开
          </a>
        ) : null}
      </div>
      <p className="text-sm text-muted">{description}</p>
      {historicalNote ? (
        <p className="rounded-md border border-uncertainty bg-uncertainty-soft px-2 py-1.5 text-xs text-uncertainty">
          {historicalNote}
        </p>
      ) : null}

      {knownUnavailable ? (
        <div className="rounded-lg border border-risk bg-risk-soft p-3" role="status">
          <p className="flex items-start gap-1.5 text-sm font-medium text-risk">
            <IconAlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            诊断集成当前不可达
          </p>
          <p className="mt-1 text-sm text-muted">
            {url === null
              ? 'Widget 来源不在允许的 origin 范围内，已阻止加载。'
              : 'MCP 服务（127.0.0.1:8789）当前未运行或未确认可达；本区域不会显示为空白成功，也不代表历史数据已丢失。'}
          </p>
          {url ? (
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setAttempt((n) => n + 1)}
                className="inline-flex items-center gap-1.5 rounded-md border border-risk px-3 py-1.5 text-xs text-risk transition-colors hover:bg-risk-soft focus:outline-none focus:ring-2 focus:ring-risk"
              >
                <IconRefresh className="h-3.5 w-3.5" />
                重试
              </button>
              <a
                href={url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center text-xs text-primary hover:underline focus:outline-none focus:ring-2 focus:ring-primary"
              >
                在新窗口打开确认
              </a>
            </div>
          ) : null}
        </div>
      ) : (
        <>
          <iframe
            key={attempt}
            src={url}
            title={`${title}（诊断/历史集成，非当前 Personal State 权威）`}
            loading="lazy"
            sandbox="allow-scripts"
            referrerPolicy="no-referrer"
            onLoad={() => setLoaded(true)}
            className="h-96 w-full rounded-md border border-line bg-white"
          />
          {!loaded && timedOut ? (
            <p role="status" className="flex items-start gap-1.5 text-xs text-uncertainty">
              <IconClock className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              尚未确认加载：若长时间空白，请确认 MCP 服务已启动，或点击"在新窗口打开"核实；这不代表当前权威数据异常。
            </p>
          ) : null}
        </>
      )}
    </section>
  );
}
