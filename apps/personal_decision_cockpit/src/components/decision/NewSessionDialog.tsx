import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { IconX } from '../icons';
import { NewSessionFlow } from './NewSessionFlow';

/**
 * "新建决策会话"对话框（顶栏入口，spec §6.3）：
 * 模态包裹 NewSessionFlow；confirm 成功后跳转会话推进视图 /sessions/<id>。
 * Esc 关闭 + 简单焦点圈（Tab 不逃逸），打开时焦点移入、关闭时还原（不引库）。
 */

export interface NewSessionDialogProps {
  open: boolean;
  onClose: () => void;
}

export function NewSessionDialog({ open, onClose }: NewSessionDialogProps) {
  const navigate = useNavigate();
  const panelRef = useRef<HTMLDivElement>(null);
  const wasOpenRef = useRef(false);
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
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

  // 仅在 打开/关闭 状态翻转时移焦：打开时焦点进对话框并记住触发源，关闭时还原
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
    <div className="fixed inset-0 z-40" role="dialog" aria-modal="true" aria-label="新建决策会话">
      <button
        type="button"
        aria-label="关闭对话框"
        className="absolute inset-0 h-full w-full cursor-default overlay-backdrop"
        onClick={onClose}
      />
      <div ref={panelRef} className="absolute inset-x-4 top-16 mx-auto max-w-lg">
        <div className="card max-h-[80vh] overflow-y-auto">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold">新建决策会话</h2>
              <p className="mt-0.5 text-sm text-muted">Guarded Orchestration：prepare → exact preview → 显式 confirm</p>
            </div>
            <button
              type="button"
              onClick={onClose}
              aria-label="关闭"
              className="rounded-md border border-line p-1.5 text-muted transition-colors hover:bg-surface focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <IconX />
            </button>
          </div>
          <div className="mt-4">
            <NewSessionFlow
              onCreated={(sessionId) => {
                onClose();
                void navigate(`/sessions/${encodeURIComponent(sessionId)}`);
              }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
