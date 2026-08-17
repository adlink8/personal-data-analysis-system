type SettingsSidebarProps = {
  activeSection: string;
  onSelect: (section: string) => void;
};

type NavItem = { id: string; label: string; icon: "sliders" | "layout" | "code" | "models" | "shield" | "spark" | "runtime" | "info" };

const groups: { label: string; items: NavItem[] }[] = [
  { label: "基础设置", items: [
    { id: "general", label: "常规", icon: "sliders" },
    { id: "interface", label: "界面与窗口", icon: "layout" },
    { id: "customize", label: "代码定制", icon: "code" },
    { id: "models", label: "模型接入", icon: "models" },
  ] },
  { label: "Agent 能力", items: [
    { id: "privacy", label: "对话与隐私", icon: "shield" },
    { id: "proactive", label: "主动提醒", icon: "spark" },
  ] },
  { label: "系统", items: [
    { id: "runtime", label: "Pi 运行时", icon: "runtime" },
    { id: "about", label: "关于", icon: "info" },
  ] },
];

function NavIcon({ name }: { name: NavItem["icon"] }) {
  const paths = {
    sliders: <><path d="M4 5h12M4 10h12M4 15h12" /><circle cx="8" cy="5" r="1.4" /><circle cx="13" cy="10" r="1.4" /><circle cx="7" cy="15" r="1.4" /></>,
    layout: <><rect x="3" y="3.5" width="14" height="13" rx="2" /><path d="M7 4v12M8 8h8" /></>,
    code: <><path d="m7.5 6-4 4 4 4M12.5 6l4 4-4 4M11 4l-2 12" /></>,
    models: <><rect x="3" y="4" width="14" height="5" rx="1.5" /><rect x="3" y="11" width="14" height="5" rx="1.5" /><path d="M6 6.5h.01M6 13.5h.01" /></>,
    shield: <><path d="M10 2.8 16 5v4.5c0 3.4-2.1 6.3-6 7.8-3.9-1.5-6-4.4-6-7.8V5l6-2.2Z" /><path d="m7.4 10 1.7 1.7 3.7-3.9" /></>,
    spark: <><path d="m10 2 1.2 4.1L15 8l-3.8 1.9L10 14l-1.2-4.1L5 8l3.8-1.9L10 2Z" /><path d="m15.5 13 .5 1.5 1.5.5-1.5.5-.5 1.5-.5-1.5-1.5-.5 1.5-.5.5-1.5Z" /></>,
    runtime: <><rect x="5" y="5" width="10" height="10" rx="2" /><path d="M8 2v3M12 2v3M8 15v3M12 15v3M2 8h3M15 8h3M2 12h3M15 12h3" /></>,
    info: <><circle cx="10" cy="10" r="7" /><path d="M10 9v5M10 6h.01" /></>,
  };
  return <svg className="settings-nav-icon" viewBox="0 0 20 20" aria-hidden="true">{paths[name]}</svg>;
}

export function SettingsSidebar({ activeSection, onSelect }: SettingsSidebarProps) {
  return (
    <nav className="settings-index" aria-label="设置分类">
      <strong className="settings-index-title">设置</strong>
      {groups.map((group) => (
        <div className="settings-nav-group" key={group.label}>
          <span>{group.label}</span>
          {group.items.map((item) => (
            <a className={activeSection === item.id ? "active" : ""} href={`#${item.id}`} onClick={() => onSelect(item.id)} key={item.id}>
              <NavIcon name={item.icon} /><span>{item.label}</span>
            </a>
          ))}
        </div>
      ))}
    </nav>
  );
}
