import { useState, type ReactNode } from "react";
import { CustomUiEditor } from "./CustomUiEditor";
import { ModelProvidersSettings } from "./ModelProvidersSettings";
import { SettingsSidebar } from "./SettingsSidebar";

type SettingsViewProps = {
  onBack: () => void;
};

type ToggleProps = {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
};

function Toggle({ label, checked, onChange }: ToggleProps) {
  return (
    <button
      className="settings-switch"
      type="button"
      role="switch"
      aria-label={label}
      aria-checked={checked}
      onClick={() => onChange(!checked)}
    >
      <span aria-hidden="true" />
    </button>
  );
}

function SettingsRow({ title, children }: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="settings-row">
      <div>
        <strong>{title}</strong>
      </div>
      <div className="settings-control">{children}</div>
    </div>
  );
}

export function SettingsView({ onBack }: SettingsViewProps) {
  const [openAtStartup, setOpenAtStartup] = useState(true);
  const [agentsViewRefresh, setAgentsViewRefresh] = useState(true);
  const [proactiveHints, setProactiveHints] = useState(true);
  const [autoOpenDrawer, setAutoOpenDrawer] = useState(false);
  const [launchTarget, setLaunchTarget] = useState("last");
  const [routingMode, setRoutingMode] = useState("auto");
  const [windowForm, setWindowForm] = useState("standard");
  const [windowWidth, setWindowWidth] = useState(1180);
  const [windowHeight, setWindowHeight] = useState(760);
  const [windowPosition, setWindowPosition] = useState("center");
  const [railMode, setRailMode] = useState("icons");
  const [conversationWidth, setConversationWidth] = useState("comfortable");
  const [alwaysOnTop, setAlwaysOnTop] = useState(false);
  const [rememberWindow, setRememberWindow] = useState(true);
  const [activeSection, setActiveSection] = useState("general");

  return (
    <main className="settings-workspace">
      <div className="settings-shell">
        <aside className="settings-side">
          <div className="settings-side-head">
            <span className="brand-mark">H</span>
            <strong>Harness</strong>
          </div>
          <button className="back-button" type="button" aria-label="返回对话" onClick={onBack}>
            <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M12.5 4.5 7 10l5.5 5.5" /></svg>
            <span>返回对话</span>
          </button>
          <SettingsSidebar activeSection={activeSection} onSelect={setActiveSection} />
        </aside>

        <section className="settings-page">
          <header className="settings-topbar">
            <strong>设置</strong>
          </header>
          <div className="settings-content">
          {activeSection === "general" ? <section className="settings-section" id="general">
            <SettingsRow title="启动时打开">
              <select aria-label="启动时打开" value={launchTarget} onChange={(event) => setLaunchTarget(event.target.value)}>
                <option value="last">上次对话</option><option value="new">新对话</option>
              </select>
            </SettingsRow>
            <SettingsRow title="随系统启动">
              <Toggle label="随系统启动" checked={openAtStartup} onChange={setOpenAtStartup} />
            </SettingsRow>
            <SettingsRow title="外观">
              <span className="settings-value">深色 · 紧凑</span>
            </SettingsRow>
          </section> : null}

          {activeSection === "interface" ? <section className="settings-section" id="interface">
            <fieldset className="window-form-picker">
              <legend>窗口形式</legend>
              <label className={windowForm === "standard" ? "selected" : ""}>
                <input type="radio" name="window-form" value="standard" aria-label="标准工作台" checked={windowForm === "standard"} onChange={(event) => setWindowForm(event.target.value)} />
                <span className="window-preview window-preview-standard" aria-hidden="true"><i /><b /><em /></span>
                <strong>标准工作台</strong>
              </label>
              <label className={windowForm === "compact" ? "selected" : ""}>
                <input type="radio" name="window-form" value="compact" aria-label="紧凑对话" checked={windowForm === "compact"} onChange={(event) => setWindowForm(event.target.value)} />
                <span className="window-preview window-preview-compact" aria-hidden="true"><i /><b /><em /></span>
                <strong>紧凑对话</strong>
              </label>
              <label className={windowForm === "custom" ? "selected" : ""}>
                <input type="radio" name="window-form" value="custom" aria-label="自定义窗口" checked={windowForm === "custom"} onChange={(event) => setWindowForm(event.target.value)} />
                <span className="window-preview window-preview-custom" aria-hidden="true"><i /><b /><em /></span>
                <strong>自定义窗口</strong>
              </label>
            </fieldset>

            {windowForm === "custom" ? (
              <div className="custom-window-panel" aria-label="自定义窗口参数">
                <label><span>宽度</span><span className="dimension-input"><input aria-label="窗口宽度" type="number" min="720" max="3840" value={windowWidth} onChange={(event) => setWindowWidth(Number(event.target.value))} /><small>px</small></span></label>
                <span className="dimension-separator">×</span>
                <label><span>高度</span><span className="dimension-input"><input aria-label="窗口高度" type="number" min="560" max="2160" value={windowHeight} onChange={(event) => setWindowHeight(Number(event.target.value))} /><small>px</small></span></label>
                <label className="position-control"><span>启动位置</span><select aria-label="启动位置" value={windowPosition} onChange={(event) => setWindowPosition(event.target.value)}><option value="center">屏幕中央</option><option value="remember">上次位置</option><option value="right">右侧工作区</option></select></label>
              </div>
            ) : null}

            <SettingsRow title="左侧栏">
              <select aria-label="左侧栏形式" value={railMode} onChange={(event) => setRailMode(event.target.value)}><option value="icons">仅图标</option><option value="expanded">图标与名称</option><option value="hidden">自动隐藏</option></select>
            </SettingsRow>
            <SettingsRow title="对话区域宽度">
              <select aria-label="对话区域宽度" value={conversationWidth} onChange={(event) => setConversationWidth(event.target.value)}><option value="focused">专注 · 680 px</option><option value="comfortable">舒适 · 790 px</option><option value="wide">宽幅 · 960 px</option></select>
            </SettingsRow>
            <SettingsRow title="窗口始终置顶">
              <Toggle label="窗口始终置顶" checked={alwaysOnTop} onChange={setAlwaysOnTop} />
            </SettingsRow>
            <SettingsRow title="记住窗口状态">
              <Toggle label="记住窗口状态" checked={rememberWindow} onChange={setRememberWindow} />
            </SettingsRow>
          </section> : null}

          {activeSection === "customize" ? <section className="settings-section" id="customize">
            <CustomUiEditor />
          </section> : null}

          {activeSection === "models" ? <section className="settings-section" id="models">
            <ModelProvidersSettings />
          </section> : null}

          {activeSection === "runtime" ? <section className="settings-section" id="runtime">
            <SettingsRow title="路由模式">
              <select aria-label="路由模式" value={routingMode} onChange={(event) => setRoutingMode(event.target.value)}>
                <option value="auto">自动路由</option><option value="fixed">固定模型</option>
              </select>
            </SettingsRow>
            <SettingsRow title="当前模型">
              <span className="settings-value">GPT-5.6 · Terra</span>
            </SettingsRow>
            <SettingsRow title="Pi Kernel">
              <span className="status-pill"><span className="live-dot" /> 已就绪</span>
            </SettingsRow>
          </section> : null}

          {activeSection === "privacy" ? <section className="settings-section" id="privacy">
            <SettingsRow title="AgentsView 新鲜度检查">
              <Toggle label="AgentsView 新鲜度检查" checked={agentsViewRefresh} onChange={setAgentsViewRefresh} />
            </SettingsRow>
          </section> : null}

          {activeSection === "proactive" ? <section className="settings-section" id="proactive">
            <SettingsRow title="AI 主动提醒">
              <Toggle label="AI 主动提醒" checked={proactiveHints} onChange={setProactiveHints} />
            </SettingsRow>
            <SettingsRow title="自动打开抽屉">
              <Toggle label="自动打开抽屉" checked={autoOpenDrawer} onChange={setAutoOpenDrawer} />
            </SettingsRow>
          </section> : null}

          {activeSection === "about" ? <section className="settings-section settings-about" id="about">
            <div className="about-grid"><span>原型版本</span><strong>Phase 61 · UI Spike C</strong><span>界面通道</span><strong>named DesktopBridge</strong><span>数据权威</span><strong>Python domain + governed tools</strong></div>
          </section> : null}
          </div>
        </section>
      </div>
    </main>
  );
}
