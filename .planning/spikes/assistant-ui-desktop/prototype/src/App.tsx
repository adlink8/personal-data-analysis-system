import {
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  type DataMessagePartProps,
  type TextMessagePartProps,
} from "@assistant-ui/react";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  HarnessRuntimeProvider,
  type AdapterEvent,
  type HarnessRuntimeMessage,
  type SafeCandidate,
  type SafeEvidenceReceipt,
} from "./harness-adapter";
import { createFakeHarnessBridge } from "./fake-harness";
import { SettingsView } from "./SettingsView";

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
      <span className="tool-pulse" aria-hidden="true" />
      <span>
        <strong>已使用受限能力</strong>
        <small>{data.queryId} · {data.rowCount} 行 · {data.durationMs ?? "—"} ms</small>
      </span>
      <span className="tool-open">查看回执</span>
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
          <div className="composer-context"><span>数据分析</span><span>Pi · 自动路由</span></div>
          <ComposerPrimitive.Send className="send-button" aria-label="发送">↑</ComposerPrimitive.Send>
        </div>
      </ComposerPrimitive.Root>
      <div className="composer-note">Enter 发送 · Shift+Enter 换行 · 只通过 named DesktopBridge</div>
    </div>
  );
}

function RailButton({ label, active, badge, onClick, children }: {
  label: string;
  active?: boolean;
  badge?: number;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button className={`rail-button${active ? " active" : ""}`} type="button" aria-label={label} title={label} onClick={onClick}>
      <span aria-hidden="true">{children}</span>
      {badge ? <span className="badge">{badge}</span> : null}
    </button>
  );
}

function HistoryDrawer({ open, onClose, bridge }: { open: boolean; onClose: () => void; bridge: ReturnType<typeof createFakeHarnessBridge> }) {
  const [filter, setFilter] = useState("");
  const visible = bridge.recentConversations.filter((item) => item.title.toLowerCase().includes(filter.toLowerCase()));
  return (
    <aside className={`drawer drawer-left${open ? " open" : ""}`} aria-hidden={!open} aria-label="AgentsView 会话历史">
      <header className="drawer-header"><div><strong>所有会话</strong><small>AgentsView 只读聚合</small></div><button onClick={onClose} aria-label="关闭历史">×</button></header>
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
      <div className="drawer-foot">历史投影不是执行权威 · 当前 fixture 仅用于 Spike</div>
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
      <header className="drawer-header"><div><strong>受控能力</strong><small>Tool · SQLite · Candidate</small></div><button onClick={onClose} aria-label="关闭证据">×</button></header>
      <div className="drawer-content">
        <section className="inspector-section">
          <div className="section-kicker">TOOL RECEIPT</div>
          {receipts.length === 0 ? <p className="empty-copy">尚无 Tool 回执。发送一条消息后，只显示 checksum 验证通过的 allowlisted 结果。</p> : receipts.map((receipt) => (
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
          <div className="section-kicker">REVIEW INBOX</div>
          {candidate ? (
            <div className="candidate-card">
              <span className="candidate-state">待你审核</span><h3>{candidate.title}</h3><p>{candidate.summary}</p>
              <div className="candidate-actions"><button>接受</button><button>编辑</button><button className="quiet">忽略</button></div>
              <small>此 Spike 不执行审核写入；正式版仍调用 reviewCandidate。</small>
            </div>
          ) : <p className="empty-copy">没有待审核 Candidate。AI 只提示入口，不自动打开本面板。</p>}
        </section>
        <section className="inspector-section audit-section">
          <div className="section-kicker">ADAPTER EVENTS · METADATA ONLY</div>
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
        <input autoFocus placeholder="输入命令或搜索…" aria-label="命令搜索" />
        <button onClick={openHistory}><span>打开所有会话</span><kbd>Ctrl H</kbd></button>
        <button onClick={openEvidence}><span>查看 Tool 与证据</span><kbd>Ctrl E</kbd></button>
        <button onClick={openSettings}><span>打开设置</span><kbd>Ctrl ,</kbd></button>
        <button onClick={onClose}><span>回到当前对话</span><kbd>Esc</kbd></button>
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
        <div className="app-shell">
          <nav className="rail" aria-label="主导航">
            <div className="brand-mark" title="Harness">H</div>
            <RailButton label="当前对话" active={panel === null} onClick={() => setPanel(null)}>◇</RailButton>
            <RailButton label="所有会话" active={panel === "history"} onClick={() => setPanel(panel === "history" ? null : "history")}>≡</RailButton>
            <RailButton label="Tool 与证据" active={panel === "evidence"} badge={receipts.length + (candidate ? 1 : 0)} onClick={() => { setPanel(panel === "evidence" ? null : "evidence"); setHint(false); }}>⌘</RailButton>
            <div className="rail-spacer" />
            <RailButton label="命令面板" active={panel === "command"} onClick={() => setPanel("command")}>K</RailButton>
            <RailButton label="设置" active={panel === "settings"} onClick={() => setPanel("settings")}>
              <svg className="rail-icon" viewBox="0 0 20 20" aria-hidden="true"><path d="M8.2 2.5h3.6l.5 2a6.2 6.2 0 0 1 1.2.7l2-.6 1.8 3.1-1.5 1.4a6 6 0 0 1 0 1.8l1.5 1.4-1.8 3.1-2-.6a6.2 6.2 0 0 1-1.2.7l-.5 2H8.2l-.5-2a6.2 6.2 0 0 1-1.2-.7l-2 .6-1.8-3.1 1.5-1.4a6 6 0 0 1 0-1.8L2.7 7.7l1.8-3.1 2 .6a6.2 6.2 0 0 1 1.2-.7l.5-2Z" /><circle cx="10" cy="10" r="2.4" /></svg>
            </RailButton>
          </nav>

          {panel === "settings" ? <SettingsView onBack={() => setPanel(null)} /> : <main className="workspace">
            <header className="topbar">
              <div className="thread-heading"><strong>Agent 桌面 UI 复用方案</strong><small><span className="live-dot" /> 数据分析 · 本地 Harness</small></div>
              <div className="top-actions"><button onClick={() => setPanel("history")}>历史</button><button onClick={() => setPanel("evidence")}>证据</button><button className="command-button" onClick={() => setPanel("command")}>⌘ K</button></div>
            </header>
            <ThreadPrimitive.Root className="thread-root">
              <ThreadPrimitive.Viewport className="thread-viewport">
                <ThreadPrimitive.Messages components={{ UserMessage, AssistantMessage }} />
                <div className="thread-bottom-space" />
              </ThreadPrimitive.Viewport>
              <Composer />
            </ThreadPrimitive.Root>
          </main>}

          <HistoryDrawer open={panel === "history"} onClose={() => setPanel(null)} bridge={bridge} />
          <EvidenceDrawer open={panel === "evidence"} onClose={() => setPanel(null)} receipts={receipts} candidate={candidate} events={events} />
          <CommandPalette open={panel === "command"} onClose={() => setPanel(null)} openHistory={() => setPanel("history")} openEvidence={() => setPanel("evidence")} openSettings={() => setPanel("settings")} />
          {(panel === "history" || panel === "evidence") ? <button className="drawer-scrim" aria-label="关闭抽屉" onClick={() => setPanel(null)} /> : null}
          {hint ? <button className="ai-hint" onClick={() => { setPanel("evidence"); setHint(false); }}><span>受控查询已完成</span><strong>查看 1 个回执与 1 个建议 →</strong></button> : null}
        </div>
      </EvidenceActionContext.Provider>
    </HarnessRuntimeProvider>
  );
}
