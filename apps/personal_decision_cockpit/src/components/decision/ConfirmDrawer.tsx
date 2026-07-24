import { useEffect, useRef, useState } from 'react';
import type { OrchestrationPreview } from '../../api/orchestration';
import { shortId } from '../authority/SnapshotChip';
import { IconAlertTriangle, IconShield, IconX } from '../icons';

/**
 * 确认抽屉（spec §7.3 / §5.3）：每一次写入前的 exact preview + 显式确认。
 * 八要素：操作名称、exact preview（JSON 只读、等宽、可折叠/展开）、将新增的 Event 说明、
 * "不会执行的动作"固定提示、preview_checksum、idempotency_key（重试同键）、
 * 风险提示、具体文案的确认按钮（禁止"继续/确定"）。
 * preview JSON 只渲染展示，不打印到控制台（spec §15.4）。
 */

export interface ConfirmDrawerProps {
  open: boolean;
  /** 1. 操作名称（如 记录决策 / 创建决策会话） */
  title: string;
  /** 2. exact preview（服务端返回原样，绝不修改） */
  preview: OrchestrationPreview | null;
  /** 3. 将新增的 Event 说明 */
  eventDescription: string;
  /** 7. 风险提示（领域/操作特定），缺省用通用提示 */
  riskHint?: string;
  /** 8. 确认按钮具体文案（如 确认写入"接受方案"） */
  confirmLabel: string;
  /** 6. 幂等键：由调用方生成并保持同一次尝试内不变 */
  idempotencyKey: string;
  /** 确认执行中（禁用按钮防重复提交） */
  busy?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

/** "不会执行的动作"固定提示（spec §5.3 / §13） */
const NON_ACTIONS: ReadonlyArray<string> = [
  '不会自动执行任何外部动作',
  '不会 promote 任何建议或知识单元',
  '不会修改任何 SSOT（知识库 / 个人状态 / 外部快照）',
  '本步骤仅向编排事件链追加一条带幂等键的事件',
];

export function ConfirmDrawer({
  open,
  title,
  preview,
  eventDescription,
  riskHint,
  confirmLabel,
  idempotencyKey,
  busy = false,
  onConfirm,
  onClose,
}: ConfirmDrawerProps) {
  const [previewExpanded, setPreviewExpanded] = useState(false);
  const panelRef = useRef<HTMLElement>(null);
  const wasOpenRef = useRef(false);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  // Esc 关闭抽屉 + 简单焦点圈（Tab 不逃逸出抽屉，不引库）；打开时重置折叠状态
  useEffect(() => {
    if (!open) return;
    setPreviewExpanded(false);
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
        return;
      }
      if (event.key === 'Tab') {
        const panel = panelRef.current;
        if (!panel) return;
        const focusable = panel.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        );
        if (focusable.length === 0) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        const active = document.activeElement;
        if (event.shiftKey && (active === first || !panel.contains(active))) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && (active === last || !panel.contains(active))) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  // 仅在 打开/关闭 状态翻转时移焦：打开时焦点进抽屉并记住触发源，关闭时还原
  // （不依赖 onClose 身份，避免父组件重渲染把焦点反复拽回）
  useEffect(() => {
    if (open && !wasOpenRef.current) {
      restoreFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
      panelRef.current?.querySelector<HTMLElement>('button, [href], input, select, textarea')?.focus();
    } else if (!open && wasOpenRef.current) {
      const target = restoreFocusRef.current;
      if (target?.isConnected) target.focus();
      restoreFocusRef.current = null;
    }
    wasOpenRef.current = open;
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50" role="dialog" aria-modal="true" aria-label={`确认写入：${title}`}>
      {/* 遮罩：点击关闭（未写入任何内容） */}
      <button
        type="button"
        aria-label="关闭确认抽屉"
        className="absolute inset-0 h-full w-full cursor-default overlay-backdrop"
        onClick={onClose}
      />
      <aside ref={panelRef} className="absolute inset-y-0 right-0 flex w-full max-w-md flex-col border-l border-line bg-panel shadow-xl">
        <header className="flex items-start justify-between gap-3 border-b border-line p-4">
          <div>
            <p className="text-xs text-muted">写入确认（exact preview）</p>
            <h2 className="mt-0.5 text-lg font-semibold">{title}</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="rounded-md border border-line p-1.5 text-muted transition-colors hover:bg-surface focus:outline-none focus:ring-2 focus:ring-primary"
          >
            <IconX />
          </button>
        </header>

        <div className="section-stack flex-1 overflow-y-auto p-4">
          {/* 2. exact preview：JSON 只读视图，等宽，折叠/展开 */}
          <section className="rounded-lg border border-line bg-surface">
            <button
              type="button"
              onClick={() => setPreviewExpanded((value) => !value)}
              aria-expanded={previewExpanded}
              className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm font-medium transition-colors hover:bg-panel focus:outline-none focus:ring-2 focus:ring-primary"
            >
              exact preview（JSON，只读）
              <span className="text-xs text-muted">{previewExpanded ? '折叠' : '展开'}</span>
            </button>
            {previewExpanded ? (
              <pre className="max-h-72 overflow-auto border-t border-line p-3 font-mono text-xs break-all whitespace-pre-wrap">
                {preview ? JSON.stringify(preview, null, 2) : '（无 preview）'}
              </pre>
            ) : null}
          </section>

          {/* 3. 将新增的 Event 说明 */}
          <section className="rounded-lg border border-line bg-surface p-3">
            <h3 className="text-sm font-medium">将新增的 Event</h3>
            <p className="mt-1 text-sm text-muted">{eventDescription}</p>
            {preview ? (
              <p className="mt-1 text-sm text-muted">
                operation <span className="font-mono">{preview.operation}</span> · 预期序号{' '}
                <span className="font-mono">{preview.expected_sequence + 1}</span>
              </p>
            ) : null}
          </section>

          {/* 4. "不会执行的动作"固定提示 */}
          <section className="rounded-lg border border-line bg-surface p-3" aria-label="不会执行的动作">
            <h3 className="flex items-center gap-1.5 text-sm font-medium">
              <IconShield className="h-4 w-4 shrink-0 text-verified" />
              不会执行的动作
            </h3>
            <ul className="mt-1 list-disc pl-5 text-sm text-muted">
              {NON_ACTIONS.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </section>

          {/* 5 + 6. checksum 与幂等键 */}
          <section className="rounded-lg border border-line bg-surface p-3 text-sm">
            <dl className="space-y-2">
              <div>
                <dt className="text-muted">preview_checksum</dt>
                <dd className="mt-0.5 font-mono text-xs break-all" title={preview?.preview_checksum}>
                  {preview ? shortId(preview.preview_checksum, 24) : '—'}
                </dd>
              </div>
              <div>
                <dt className="text-muted">idempotency_key（网络重试使用同一键，不会产生重复写入）</dt>
                <dd className="mt-0.5 font-mono text-xs break-all" title={idempotencyKey}>
                  {idempotencyKey}
                </dd>
              </div>
            </dl>
          </section>

          {/* 7. 风险提示 */}
          <section className="rounded-lg border border-uncertainty bg-uncertainty-soft p-3" aria-label="风险提示">
            <p className="flex items-start gap-1.5 text-sm text-uncertainty">
              <IconAlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{riskHint ?? '写入后事件不可删除（append-only）；后续阶段可通过新事件修正，但历史永远保留。'}</span>
            </p>
          </section>
        </div>

        {/* 8. 确认按钮：文案必须具体，禁止"继续/确定" */}
        <footer className="flex items-center gap-2 border-t border-line p-4">
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy || !preview}
            className="flex-1 rounded-md bg-primary px-3 py-2 text-sm font-medium text-white transition-colors hover:opacity-90 focus:outline-none focus:ring-2 focus:ring-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? '正在写入…' : confirmLabel}
          </button>
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="rounded-md border border-line px-3 py-2 text-sm text-muted transition-colors hover:bg-surface focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
          >
            取消
          </button>
        </footer>
      </aside>
    </div>
  );
}
