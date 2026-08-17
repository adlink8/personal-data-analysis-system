import { useMemo, useState, type CSSProperties } from "react";

type EditorLanguage = "css" | "tokens" | "html";
type UiRegion = "global" | "sidebar" | "topbar" | "messages" | "composer" | "drawer" | "settings";

const languageLabels: Record<EditorLanguage, string> = {
  css: "CSS",
  tokens: "Theme JSON",
  html: "HTML",
};

const regionLabels: Record<UiRegion, string> = {
  global: "全局",
  sidebar: "左侧栏",
  topbar: "顶栏",
  messages: "消息区",
  composer: "输入框",
  drawer: "抽屉与弹窗",
  settings: "设置页",
};

const regions = Object.keys(regionLabels) as UiRegion[];

const cssTemplates: Record<UiRegion, string> = {
  global: `:root {
  --harness-accent: #8fa8c2;
  --harness-radius: 12px;
  --harness-density: compact;
}`,
  sidebar: `.codex-sidebar {
  background: rgba(28, 39, 46, 0.86);
  backdrop-filter: blur(18px);
}`,
  topbar: `.topbar {
  height: 50px;
  border-bottom: 1px solid #303030;
}`,
  messages: `.thread-viewport {
  max-width: 820px;
}

.message-assistant {
  line-height: 1.7;
}`,
  composer: `.composer {
  border-radius: 14px;
  background: #202427;
}`,
  drawer: `.drawer,
.command-palette {
  border-color: #353b40;
  backdrop-filter: blur(20px);
}`,
  settings: `.settings-page {
  background: #181818;
}

.settings-row {
  min-height: 56px;
}`,
};

const tokenTemplates: Record<UiRegion, string> = Object.fromEntries(
  regions.map((region) => [region, JSON.stringify({ region, accent: "#8fa8c2", radius: 12 }, null, 2)]),
) as Record<UiRegion, string>;

const htmlTemplates: Record<UiRegion, string> = Object.fromEntries(
  regions.map((region) => [region, `<section data-harness-region="${region}">\n  <slot></slot>\n</section>`]),
) as Record<UiRegion, string>;

const templates: Record<EditorLanguage, Record<UiRegion, string>> = {
  css: cssTemplates,
  tokens: tokenTemplates,
  html: htmlTemplates,
};

type RegionDrafts = Record<EditorLanguage, Record<UiRegion, string>>;

function createDrafts(): RegionDrafts {
  return {
    css: { ...cssTemplates },
    tokens: { ...tokenTemplates },
    html: { ...htmlTemplates },
  };
}

function validateCode(language: EditorLanguage, code: string): string | null {
  if (code.length > 20_000) return "代码超过 20 KB。";
  if (/@import|url\s*\(|<script|on\w+\s*=|javascript:/i.test(code)) return "检测到网络资源或脚本语法。";
  if (language === "tokens") {
    try { JSON.parse(code); } catch { return "Theme JSON 格式无效。"; }
  }
  return null;
}

function previewAccent(language: EditorLanguage, code: string): string {
  const value = language === "tokens"
    ? (() => { try { return JSON.parse(code).accent; } catch { return undefined; } })()
    : code.match(/--harness-accent\s*:\s*(#[0-9a-f]{3,8})/i)?.[1];
  return typeof value === "string" && /^#[0-9a-f]{3,8}$/i.test(value) ? value : "#8fa8c2";
}

export function CustomUiEditor() {
  const [language, setLanguage] = useState<EditorLanguage>("css");
  const [region, setRegion] = useState<UiRegion>("global");
  const [drafts, setDrafts] = useState<RegionDrafts>(createDrafts);
  const [appliedDrafts, setAppliedDrafts] = useState<RegionDrafts>(createDrafts);
  const [status, setStatus] = useState("尚未应用更改");
  const code = drafts[language][region];
  const accent = useMemo(
    () => previewAccent(language, appliedDrafts[language][region]),
    [appliedDrafts, language, region],
  );

  const updateCode = (nextCode: string) => {
    setDrafts((current) => ({
      ...current,
      [language]: { ...current[language], [region]: nextCode },
    }));
    setStatus("有未应用的更改");
  };

  const validate = () => {
    setStatus(validateCode(language, code) ?? "校验通过");
  };

  const applyPreview = () => {
    const error = validateCode(language, code);
    if (error) { setStatus(error); return; }
    setAppliedDrafts((current) => ({
      ...current,
      [language]: { ...current[language], [region]: code },
    }));
    setStatus("预览已更新");
  };

  const restoreTemplate = () => {
    updateCode(templates[language][region]);
    setStatus("已恢复模板");
  };

  return (
    <div className="custom-ui-editor">
      <div className="custom-editor-toolbar">
        <div className="language-tabs" role="tablist" aria-label="界面代码语言">
          {(Object.keys(languageLabels) as EditorLanguage[]).map((item) => (
            <button key={item} type="button" role="tab" aria-selected={language === item} onClick={() => setLanguage(item)}>{languageLabels[item]}</button>
          ))}
        </div>
      </div>

      <div className="region-tabs" role="tablist" aria-label="界面区域">
        {regions.map((item) => (
          <button key={item} type="button" role="tab" aria-selected={region === item} onClick={() => setRegion(item)}>{regionLabels[item]}</button>
        ))}
      </div>

      <div className="editor-preview-grid">
        <div className="code-editor-shell">
          <div className="code-editor-title"><span>{regionLabels[region]} · {languageLabels[language]}</span><small>{region}.{language === "tokens" ? "json" : language}</small></div>
          <textarea aria-label="界面代码编辑器" value={code} onChange={(event) => updateCode(event.target.value)} spellCheck={false} />
        </div>

        <div className="isolated-preview" aria-label="隔离界面预览">
          <div className="preview-title"><span>预览</span></div>
          <div className={`preview-window preview-region-${region}`} style={{ "--preview-accent": accent } as CSSProperties}>
            <div className="preview-rail"><i /><i /><i /></div>
            <div className="preview-thread">
              <small>Harness</small>
              <div className="preview-message" />
              <div className="preview-composer"><span>输入消息…</span><b>↑</b></div>
            </div>
          </div>
          <div className="preview-scope"><span style={{ background: accent }} />{regionLabels[region]}</div>
        </div>
      </div>

      <div className="custom-editor-actions">
        <div className="editor-status" aria-live="polite"><span />{status}</div>
        <button type="button" className="quiet" onClick={restoreTemplate}>恢复模板</button>
        <button type="button" className="quiet" onClick={validate}>校验代码</button>
        <button type="button" className="primary" aria-label="应用到隔离预览" onClick={applyPreview}>应用到预览</button>
      </div>
    </div>
  );
}
