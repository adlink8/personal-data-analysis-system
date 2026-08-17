import {
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  type DataMessagePartProps,
  type TextMessagePartProps,
} from "@assistant-ui/react";
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import {
  HarnessRuntimeProvider,
  type AdapterEvent,
  type HarnessRuntimeMessage,
  type SafeCandidate,
  type SafeEvidenceReceipt,
} from "./harness-adapter";
import { createFakeHarnessBridge } from "./fake-harness";
import { SettingsView } from "./SettingsView";
import { CodexSidebar } from "./CodexSidebar";

type Panel = "history" | "evidence" | "command" | "settings" | null;

const EvidenceActionContext = createContext<() => void>(() => undefined);

const initialMessages: HarnessRuntimeMessage[] = [
  {
    id: "message_user_001",
    role: "user",
    text: "把散落在 Codex、ZCode 和其他 Agent 里的思考集合起来，但默认界面不要变成仪表盘。",
    createdAt: "2026-08-10T02:10:00.000Z",
  },
  {
    id: "message_assistant_001",
    role: "assistant",
    text: "可以。默认保持 Codex 式对话工作台；历史、Tool 证据和候选审核只在你主动调用，或我检测到确有新结果时显示入口，不会自动打开抽屉。",
    createdAt: "2026-08-10T02:10:14.000Z",
    status: "complete",
  },
];

function TextPart({ text }: TextMessagePartProps) {
  return <p className="message-text">{text}</p>;
}

function ToolReceiptPart({ data }: DataMessagePartProps<SafeEvidenceReceipt>) {
  const openEvidence = useContext(EvidenceActionContext);
  return (
    <button className="tool-inline" type="button" onClick={openEvidence} aria-label="打开 Tool 与 SQLite 回执">
      <span className="tool-icon" aria-hidden="true"><svg viewBox="0 0 20 20"><path d="M5 4.5h10v11H5zM7.5 8h5M7.5 11h3" /></svg></span>
      <span>
        <strong>SQLite 查询完成</strong>
        <small>{data.queryId} · {data.rowCount} 行 · {data.durationMs ?? "—"} ms</small>
      </span>
      <svg className="tool-chevron" viewBox="0 0 20 20" aria-hidden="true"><path d="m8 5 5 5-5 5" /></svg>
    </button>
  );
}

function UserMessage() {
  return (
    <MessagePrimitive.Root className="message message-user">
      <div className="user-bubble"><MessagePrimitive.Parts components={{ Text: TextPart }} /></div>
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="message message-assistant">
      <div className="assistant-avatar" aria-hidden="true">H</div>
      <div className="assistant-body">
        <div className="message-author">Harness</div>
        <MessagePrimitive.Parts
          components={{
            Text: TextPart,
            data: { by_name: { "tool-receipt": ToolReceiptPart } },
          }}
        />
      </div>
    </MessagePrimitive.Root>
  );
}

function Composer() {
  return (
    <div className="composer-dock">
      <ComposerPrimitive.Root className="composer">
        <ComposerPrimitive.Input
          className="composer-input"
          aria-label="发送消息"
          placeholder="向 Harness 提问，或让它检查会话与证据…"
          submitMode="enter"
        />
        <div className="composer-footer">
          <div className="composer-context"><button type="button" aria-label="添加附件">+</button><span className="access-badge">只读证据</span></div>
          <div className="composer-actions"><span>Terra · 自动</span><button type="button" aria-label="语音输入" className="mic-button"><svg viewBox="0 0 20 20" aria-hidden="true"><rect x="7" y="3" width="6" height="9" rx="3" /><path d="M4.8 9.8a5.2 5.2 0 0 0 10.4 0M10 15v2" /></svg></button><ComposerPrimitive.Send className="send-button" aria-label="发送">↑</ComposerPrimitive.Send></div>
        </div>
      </ComposerPrimitive.Root>
      <div className="composer-note">Enter 发送 · Shift+Enter 换行 · 只通过 named DesktopBridge</div>
    </div>
  );
}

function HistoryDrawer({ open, onClose, bridge }: { open: boolean; onClose: () => void; bridge: ReturnType<typeof createFakeHarnessBridge> }) {
  const [filter, setFilter] = useState("");
  const visible = bridge.recentConversations.filter((item) => item.title.toLowerCase().includes(filter.toLowerCase()));
  return (
    <aside className={`drawer drawer-left${open ? " open" : ""}`} aria-hidden={!open} aria-label="AgentsView 会话历史">
      <header className="drawer-header"><strong>所有会话</strong><button onClick={onClose} aria-label="关闭历史"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m5 5 10 10M15 5 5 15" /></svg></button></header>
      <div className="drawer-search"><input value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="搜索 Codex、ZCode…" /></div>
      <div className="session-list">
        {visible.map((item, index) => (
          <button
            className={`session-item${index === 0 ? " selected" : ""}`}
            key={item.conversationId}
            onClick={async () => { await bridge.selectConversation({ conversationId: item.conversationId }); onClose(); }}
          >
            <span><strong>{item.title}</strong><small>数据分析 · {item.source}</small></span><time>{item.updatedLabel}</time>
          </button>
        ))}
      </div>
    </aside>
  );
}

function EvidenceDrawer({ open, onClose, receipts, candidate, events }: {
  open: boolean;
  onClose: () => void;
  receipts: readonly SafeEvidenceReceipt[];
  candidate: SafeCandidate | null;
  events: readonly AdapterEvent[];
}) {
  return (
    <aside className={`drawer drawer-right${open ? " open" : ""}`} aria-hidden={!open} aria-label="Tool、SQLite 与候选审核">
      <header className="drawer-header"><strong>Tool 与证据</strong><button onClick={onClose} aria-label="关闭证据"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m5 5 10 10M15 5 5 15" /></svg></button></header>
      <div className="drawer-content">
        <section className="inspector-section">
          <div className="section-kicker">查询回执</div>
          {receipts.length === 0 ? <p className="empty-copy">暂无回执</p> : receipts.map((receipt) => (
            <div className="receipt-card" key={receipt.receiptId}>
              <div className="receipt-title"><span className="status-dot" /><strong>SQLite · 只读查询</strong><span>{receipt.status}</span></div>
              <dl>
                <div><dt>Query</dt><dd>{receipt.queryId}</dd></div>
                <div><dt>Rows</dt><dd>{receipt.rowCount}</dd></div>
                <div><dt>Duration</dt><dd>{receipt.durationMs ?? "—"} ms</dd></div>
              </dl>
              <details><summary>受控 statement 与结果</summary><code>{receipt.statementDisplay}</code><pre>{JSON.stringify(receipt.rows, null, 2)}</pre></details>
              <div className="checksum">sha256 · {receipt.queryChecksum.slice(0, 12)}…</div>
            </div>
          ))}
        </section>
        <section className="inspector-section">
          <div className="section-kicker">候选审核</div>
          {candidate ? (
            <div className="candidate-card">
              <span className="candidate-state">待你审核</span><h3>{candidate.title}</h3><p>{candidate.summary}</p>
              <div className="candidate-actions"><button>接受</button><button>编辑</button><button className="quiet">忽略</button></div>
            </div>
          ) : <p className="empty-copy">暂无候选</p>}
        </section>
        <section className="inspector-section audit-section">
          <div className="section-kicker">事件</div>
          {events.slice(-6).map((event, index) => <div className="audit-row" key={`${event.at}-${index}`}><span>{event.type}</span><time>{event.at.slice(11, 19)}</time></div>)}
        </section>
      </div>
    </aside>
  );
}

function CommandPalette({ open, onClose, openHistory, openEvidence, openSettings }: { open: boolean; onClose: () => void; openHistory: () => void; openEvidence: () => void; openSettings: () => void }) {
  if (!open) return null;
  return (
    <div className="palette-backdrop" role="presentation" onMouseDown={onClose}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="命令面板" onMouseDown={(event) => event.stopPropagation()}>
        <div className="palette-search"><svg viewBox="0 0 20 20" aria-hidden="true"><circle cx="8.5" cy="8.5" r="4.8" /><path d="m12 12 4 4" /></svg><input autoFocus placeholder="搜索命令…" aria-label="命令搜索" /></div>
        <div className="palette-list">
          <button onClick={openHistory}><span><i aria-hidden="true">H</i>所有会话</span><kbd>Ctrl H</kbd></button>
          <button onClick={openEvidence}><span><i aria-hidden="true">E</i>Tool 与证据</span><kbd>Ctrl E</kbd></button>
          <button onClick={openSettings}><span><i aria-hidden="true">S</i>设置</span><kbd>Ctrl ,</kbd></button>
          <button onClick={onClose}><span><i aria-hidden="true">↵</i>返回对话</span><kbd>Esc</kbd></button>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const bridge = useMemo(() => createFakeHarnessBridge(), []);
  const [panel, setPanel] = useState<Panel>(null);
  const [receipts, setReceipts] = useState<readonly SafeEvidenceReceipt[]>([]);
  const [candidate, setCandidate] = useState<SafeCandidate | null>(null);
  const [events, setEvents] = useState<AdapterEvent[]>([]);
  const [hint, setHint] = useState(false);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setPanel("command"); }
      if (event.key === "Escape") setPanel(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const receiveReceipts = (next: readonly SafeEvidenceReceipt[]) => {
    setReceipts(next);
    if (next.length > 0) setHint(true);
  };

  return (
    <HarnessRuntimeProvider
      bridge={bridge}
      conversationId="conversation_ui_spike"
      projectScopeId="project_scope_data_analysis"
      initialMessages={initialMessages}
      onReceipts={receiveReceipts}
      onCandidate={setCandidate}
      onAdapterEvent={(event) => setEvents((current) => [...current, event])}
    >
      <EvidenceActionContext.Provider value={() => { setPanel("evidence"); setHint(false); }}>
        {panel === "settings" ? <SettingsView onBack={() => setPanel(null)} /> : <div className={`app-shell${panel === "history" || panel === "evidence" ? " context-open" : ""}`}>
          <CodexSidebar bridge={bridge} panel={panel} evidenceCount={receipts.length + (candidate ? 1 : 0)} onPanel={(next) => { setPanel(next); if (next === "evidence") setHint(false); }} />

          <main className="workspace">
            <header className="topbar">
              <div className="thread-heading"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 5.5h5l1.6 2H17v7.2a1.8 1.8 0 0 1-1.8 1.8H4.8A1.8 1.8 0 0 1 3 14.7V5.5Z" /></svg><strong>Agent 桌面 UI 复用方案</strong><button type="button" aria-label="对话菜单">…</button></div>
              <div className="top-actions"><button aria-label="切换历史侧栏" onClick={() => setPanel(panel === "history" ? null : "history")}>历史</button><button aria-label="切换证据侧栏" onClick={() => setPanel(panel === "evidence" ? null : "evidence")}>证据</button><button className="command-button" onClick={() => setPanel("command")}>⌘ K</button></div>
            </header>
            <ThreadPrimitive.Root className="thread-root">
              <ThreadPrimitive.Viewport className="thread-viewport">
                <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage }} />
                <div className="thread-bottom-space" />
              </ThreadPrimitive.Viewport>
              <Composer />
            </ThreadPrimitive.Root>
          </main>

          <HistoryDrawer open={panel === "history"} onClose={() => setPanel(null)} bridge={bridge} />
          <EvidenceDrawer open={panel === "evidence"} onClose={() => setPanel(null)} receipts={receipts} candidate={candidate} events={events} />
          <CommandPalette open={panel === "command"} onClose={() => setPanel(null)} openHistory={() => setPanel("history")} openEvidence={() => setPanel("evidence")} openSettings={() => setPanel("settings")} />
          {hint ? <button className="ai-hint" aria-live="polite" aria-label="查询完成，查看证据" onClick={() => { setPanel("evidence"); setHint(false); }}><span className="ai-hint-icon" aria-hidden="true">✓</span><span className="ai-hint-copy"><strong>查询完成</strong><small>查看证据</small></span><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m8 5 5 5-5 5" /></svg></button> : null}
        </div>}
      </EvidenceActionContext.Provider>
    </HarnessRuntimeProvider>
  );
}
