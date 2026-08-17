import type { SpikeHarnessBridge } from "./fake-harness";

type SidebarPanel = "history" | "evidence" | "command" | "settings" | null;

type CodexSidebarProps = {
  bridge: SpikeHarnessBridge;
  panel: SidebarPanel;
  evidenceCount: number;
  onPanel: (panel: SidebarPanel) => void;
};

type IconName = "plus" | "clock" | "evidence" | "folder" | "search" | "bell" | "command" | "settings" | "help";

function SidebarIcon({ name }: { name: IconName }) {
  const paths = {
    plus: <path d="M10 4v12M4 10h12" />,
    clock: <><circle cx="10" cy="10" r="7" /><path d="M10 6v4l3 2" /></>,
    evidence: <><circle cx="10" cy="10" r="7" /><path d="M7 10.2 9.2 12 13 7.8" /></>,
    folder: <path d="M3 5.5h5l1.6 2H17v7.2a1.8 1.8 0 0 1-1.8 1.8H4.8A1.8 1.8 0 0 1 3 14.7V5.5Z" />,
    search: <><circle cx="8.5" cy="8.5" r="4.8" /><path d="m12 12 4 4" /></>,
    bell: <><path d="M5.2 13.5h9.6l-1.2-1.8V8a3.6 3.6 0 1 0-7.2 0v3.7l-1.2 1.8Z" /><path d="M8.5 15.5a1.7 1.7 0 0 0 3 0" /></>,
    command: <><path d="M7 6H5.5a2 2 0 1 1 2-2V16a2 2 0 1 1-2-2H14.5a2 2 0 1 1-2 2V4a2 2 0 1 1 2 2H7Z" /></>,
    settings: <><path d="M8.2 2.5h3.6l.5 2a6.2 6.2 0 0 1 1.2.7l2-.6 1.8 3.1-1.5 1.4a6 6 0 0 1 0 1.8l1.5 1.4-1.8 3.1-2-.6a6.2 6.2 0 0 1-1.2.7l-.5 2H8.2l-.5-2a6.2 6.2 0 0 1-1.2-.7l-2 .6-1.8-3.1 1.5-1.4a6 6 0 0 1 0-1.8L2.7 7.7l1.8-3.1 2 .6a6.2 6.2 0 0 1 1.2-.7l.5-2Z" /><circle cx="10" cy="10" r="2.4" /></>,
    help: <><circle cx="10" cy="10" r="7" /><path d="M8.3 7.5A2 2 0 0 1 10.2 6c1.2 0 2.2.7 2.2 1.9 0 1.6-2.4 1.7-2.4 3.4M10 14h.01" /></>,
  };
  return <svg className="sidebar-icon" viewBox="0 0 20 20" aria-hidden="true">{paths[name]}</svg>;
}

export function CodexSidebar({ bridge, panel, evidenceCount, onPanel }: CodexSidebarProps) {
  return (
    <nav className="codex-sidebar" aria-label="项目与会话">
      <div className="sidebar-brand-row">
        <button className="sidebar-brand" type="button"><span className="brand-mark">H</span><strong>Harness</strong><span aria-hidden="true">⌄</span></button>
        <div><button type="button" aria-label="搜索"><SidebarIcon name="search" /></button><button type="button" aria-label="通知"><SidebarIcon name="bell" /></button></div>
      </div>

      <div className="sidebar-primary">
        <button type="button" aria-label="新对话" onClick={async () => { await bridge.newConversation({ projectScopeId: "project_scope_data_analysis" }); onPanel(null); }}><SidebarIcon name="plus" /><span>新对话</span></button>
        <button type="button" aria-label="所有会话" className={panel === "history" ? "active" : ""} onClick={() => onPanel(panel === "history" ? null : "history")}><SidebarIcon name="clock" /><span>所有会话</span></button>
        <button type="button" aria-label="Tool 与证据" className={panel === "evidence" ? "active" : ""} onClick={() => onPanel(panel === "evidence" ? null : "evidence")}><SidebarIcon name="evidence" /><span>Tool 与证据</span>{evidenceCount > 0 ? <b>{evidenceCount}</b> : null}</button>
      </div>

      <div className="sidebar-scroll">
        <div className="sidebar-section-label">项目</div>
        <button className="project-row" type="button"><SidebarIcon name="folder" /><strong>数据分析</strong><span>…</span></button>
        <div className="project-conversations">
          {bridge.recentConversations.map((item, index) => (
            <button className={index === 0 && panel === null ? "selected" : ""} type="button" key={item.conversationId} onClick={async () => { await bridge.selectConversation({ conversationId: item.conversationId }); onPanel(null); }}>
              <span>{item.title}</span><small>{item.updatedLabel}</small>
            </button>
          ))}
        </div>

        <div className="sidebar-section-label recent-label">快捷入口</div>
        <button className="sidebar-plain-row" type="button" onClick={() => onPanel("evidence")}><span>候选审核</span></button>
        <button className="sidebar-plain-row" type="button"><span>个人多维模型</span></button>
        <button className="sidebar-plain-row" type="button"><span>今日简报</span></button>
      </div>

      <div className="sidebar-bottom">
        <button type="button" aria-label="命令面板" onClick={() => onPanel("command")}><SidebarIcon name="command" /><span>命令面板</span><kbd>Ctrl K</kbd></button>
        <div className="sidebar-profile"><span>L</span><strong>Liberty</strong><button type="button" aria-label="帮助"><SidebarIcon name="help" /></button><button type="button" aria-label="设置" onClick={() => onPanel("settings")}><SidebarIcon name="settings" /></button></div>
      </div>
    </nav>
  );
}
