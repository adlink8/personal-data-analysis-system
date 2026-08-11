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

function SettingsRow({ title, description, children }: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <div className="settings-row">
      <div>
        <strong>{title}</strong>
        <p>{description}</p>
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
      <header className="settings-topbar">
        <button className="back-button" type="button" aria-label="返回对话" onClick={onBack}>
          <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M12.5 4.5 7 10l5.5 5.5" /></svg>
          <span>返回对话</span>
        </button>
        <div className="bridge-state"><span className="live-dot" /> DesktopBridge 已连接</div>
      </header>

      <div className="settings-shell">
        <SettingsSidebar activeSection={activeSection} onSelect={setActiveSection} />

        <div className="settings-content">
          <div className="settings-title">
            <div>
              <h1>设置</h1>
              <p>保持对话优先，其他能力只在需要时出现。</p>
            </div>
            <span>本地 Harness</span>
          </div>

          <div className="settings-preview-note" role="note">
            原型预览：设置只保存在当前页面，不写入真实 DesktopBridge。
          </div>

          <section className="settings-section" id="general">
            <div className="settings-section-heading"><span>01</span><div><h2>常规</h2><p>启动与对话工作台的基本行为。</p></div></div>
            <SettingsRow title="启动时打开" description="默认回到上次中断的对话。">
              <select aria-label="启动时打开" value={launchTarget} onChange={(event) => setLaunchTarget(event.target.value)}>
                <option value="last">上次对话</option><option value="new">新对话</option>
              </select>
            </SettingsRow>
            <SettingsRow title="随系统启动" description="启动后安静地驻留在系统托盘。">
              <Toggle label="随系统启动" checked={openAtStartup} onChange={setOpenAtStartup} />
            </SettingsRow>
            <SettingsRow title="外观" description="与 Codex 桌面端保持一致的低对比暗色界面。">
              <span className="settings-value">深色 · 紧凑</span>
            </SettingsRow>
          </section>

          <section className="settings-section" id="interface">
            <div className="settings-section-heading"><span>02</span><div><h2>界面与窗口</h2><p>选择工作台形式，再按你的屏幕和使用习惯微调。</p></div></div>
            <fieldset className="window-form-picker">
              <legend>窗口形式</legend>
              <label className={windowForm === "standard" ? "selected" : ""}>
                <input type="radio" name="window-form" value="standard" aria-label="标准工作台" checked={windowForm === "standard"} onChange={(event) => setWindowForm(event.target.value)} />
                <span className="window-preview window-preview-standard" aria-hidden="true"><i /><b /><em /></span>
                <strong>标准工作台</strong><small>完整对话和可按需打开的抽屉</small>
              </label>
              <label className={windowForm === "compact" ? "selected" : ""}>
                <input type="radio" name="window-form" value="compact" aria-label="紧凑对话" checked={windowForm === "compact"} onChange={(event) => setWindowForm(event.target.value)} />
                <span className="window-preview window-preview-compact" aria-hidden="true"><i /><b /><em /></span>
                <strong>紧凑对话</strong><small>窄屏、低干扰，快速问答与查看结果</small>
              </label>
              <label className={windowForm === "custom" ? "selected" : ""}>
                <input type="radio" name="window-form" value="custom" aria-label="自定义窗口" checked={windowForm === "custom"} onChange={(event) => setWindowForm(event.target.value)} />
                <span className="window-preview window-preview-custom" aria-hidden="true"><i /><b /><em /></span>
                <strong>自定义窗口</strong><small>自定义宽高、位置与置顶方式</small>
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

            <SettingsRow title="左侧栏" description="保持图标栏，或在大屏上常驻显示名称。">
              <select aria-label="左侧栏形式" value={railMode} onChange={(event) => setRailMode(event.target.value)}><option value="icons">仅图标</option><option value="expanded">图标与名称</option><option value="hidden">自动隐藏</option></select>
            </SettingsRow>
            <SettingsRow title="对话区域宽度" description="仅改变消息和输入框宽度，不改变字号。">
              <select aria-label="对话区域宽度" value={conversationWidth} onChange={(event) => setConversationWidth(event.target.value)}><option value="focused">专注 · 680 px</option><option value="comfortable">舒适 · 790 px</option><option value="wide">宽幅 · 960 px</option></select>
            </SettingsRow>
            <SettingsRow title="窗口始终置顶" description="适合把 Harness 作为辅助对话窗口放在当前工作区上方。">
              <Toggle label="窗口始终置顶" checked={alwaysOnTop} onChange={setAlwaysOnTop} />
            </SettingsRow>
            <SettingsRow title="记住窗口状态" description="下次启动时恢复尺寸、位置和最大化状态。">
              <Toggle label="记住窗口状态" checked={rememberWindow} onChange={setRememberWindow} />
            </SettingsRow>
          </section>

          <section className="settings-section" id="customize">
            <div className="settings-section-heading"><span>03</span><div><h2>代码定制</h2><p>用 CSS、Theme JSON 或隔离 HTML 定制界面，先校验和预览，再保存为本地主题。</p></div></div>
            <CustomUiEditor />
          </section>

          <section className="settings-section" id="models">
            <div className="settings-section-heading"><span>04</span><div><h2>模型接入</h2><p>管理模型提供商、API 协议与能力声明，供 Pi Kernel 受控路由。</p></div></div>
            <ModelProvidersSettings />
          </section>

          <section className="settings-section" id="runtime">
            <div className="settings-section-heading"><span>05</span><div><h2>模型与运行时</h2><p>Pi Kernel 和 Provider 的路由摘要。</p></div></div>
            <SettingsRow title="路由模式" description="由 Harness 根据对话、Skill 与工具需求选择模型。">
              <select aria-label="路由模式" value={routingMode} onChange={(event) => setRoutingMode(event.target.value)}>
                <option value="auto">自动路由</option><option value="fixed">固定模型</option>
              </select>
            </SettingsRow>
            <SettingsRow title="当前模型" description="对话引擎使用 Pi coding-agent API 的受控会话。">
              <span className="settings-value">GPT-5.6 · Terra</span>
            </SettingsRow>
            <SettingsRow title="Pi Kernel" description="本机运行时状态；高级端口配置默认收起。">
              <span className="status-pill"><span className="live-dot" /> 已就绪</span>
            </SettingsRow>
          </section>

          <section className="settings-section" id="privacy">
            <div className="settings-section-heading"><span>06</span><div><h2>对话与隐私</h2><p>AgentsView 只读聚合与本地证据边界。</p></div></div>
            <SettingsRow title="AgentsView 新鲜度检查" description="后台检查是否有新对话，不自动打开历史抽屉。">
              <Toggle label="AgentsView 新鲜度检查" checked={agentsViewRefresh} onChange={setAgentsViewRefresh} />
            </SettingsRow>
            <SettingsRow title="SQLite 访问" description="AI 只能通过 evidence.sqlite_query Tool 读取 allowlisted 查询。">
              <span className="settings-value">只读 · 有回执</span>
            </SettingsRow>
            <SettingsRow title="界面日志" description="仅记录事件类型和时间，不保存正文、SQL 或凭据。">
              <span className="settings-value">Metadata only</span>
            </SettingsRow>
          </section>

          <section className="settings-section" id="proactive">
            <div className="settings-section-heading"><span>07</span><div><h2>主动提醒</h2><p>有新结果时给出轻量入口，不打断对话。</p></div></div>
            <SettingsRow title="AI 主动提醒" description="检测到新回执、候选反思或同步缺口时显示一条入口。">
              <Toggle label="AI 主动提醒" checked={proactiveHints} onChange={setProactiveHints} />
            </SettingsRow>
            <SettingsRow title="自动打开抽屉" description="默认关闭；历史、Tool 证据与候选审核由你决定何时展开。">
              <Toggle label="自动打开抽屉" checked={autoOpenDrawer} onChange={setAutoOpenDrawer} />
            </SettingsRow>
          </section>

          <section className="settings-section settings-about" id="about">
            <div className="settings-section-heading"><span>08</span><div><h2>关于</h2><p>桌面 Harness 原型的运行边界。</p></div></div>
            <div className="about-grid"><span>原型版本</span><strong>Phase 61 · UI Spike C</strong><span>界面通道</span><strong>named DesktopBridge</strong><span>数据权威</span><strong>Python domain + governed tools</strong></div>
          </section>
        </div>
      </div>
    </main>
  );
}
