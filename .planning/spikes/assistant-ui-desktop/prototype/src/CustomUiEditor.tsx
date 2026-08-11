import { useMemo, useState, type CSSProperties } from "react";

type EditorLanguage = "css" | "tokens" | "html";

const templates: Record<EditorLanguage, string> = {
  css: `:root {
  --harness-accent: #8fa8c2;
  --harness-chat-width: 820px;
  --harness-radius: 12px;
}

.message-assistant {
  line-height: 1.7;
}`,
  tokens: `{
  "accent": "#8fa8c2",
  "chatWidth": 820,
  "radius": 12,
  "density": "compact"
}`,
  html: `<section class="harness-custom-panel">
  <header>My workspace</header>
  <slot name="conversation"></slot>
</section>`,
};

const languageLabels: Record<EditorLanguage, string> = {
  css: "CSS",
  tokens: "Theme JSON",
  html: "HTML · 隔离沙箱",
};

function validateCode(language: EditorLanguage, code: string): string | null {
  if (code.length > 20_000) return "代码超过 20 KB 的单个主题限制。";
  if (/@import|url\s*\(|<script|on\w+\s*=|javascript:/i.test(code)) return "检测到网络资源或脚本语法，隔离预览已拒绝。";
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
  const [code, setCode] = useState(templates.css);
  const [appliedCode, setAppliedCode] = useState(templates.css);
  const [scope, setScope] = useState("workspace");
  const [status, setStatus] = useState("尚未应用更改");
  const accent = useMemo(() => previewAccent(language, appliedCode), [language, appliedCode]);

  const changeLanguage = (next: EditorLanguage) => {
    setLanguage(next);
    setCode(templates[next]);
    setAppliedCode(templates[next]);
    setStatus("已切换模板 · 尚未写入应用");
  };

  const validate = () => {
    const error = validateCode(language, code);
    setStatus(error ?? "校验通过 · 可安全进入隔离预览");
  };

  const applyPreview = () => {
    const error = validateCode(language, code);
    if (error) { setStatus(error); return; }
    setAppliedCode(code);
    setStatus("预览已更新 · 未写入应用");
  };

  return (
    <div className="custom-ui-editor">
      <div className="custom-editor-toolbar">
        <div className="language-tabs" role="tablist" aria-label="界面代码语言">
          {(Object.keys(languageLabels) as EditorLanguage[]).map((item) => (
            <button key={item} type="button" role="tab" aria-selected={language === item} onClick={() => changeLanguage(item)}>{languageLabels[item]}</button>
          ))}
        </div>
        <label>
          <span>应用范围</span>
          <select aria-label="自定义样式范围" value={scope} onChange={(event) => setScope(event.target.value)}>
            <option value="workspace">对话工作台</option>
            <option value="conversation">仅消息区域</option>
            <option value="composer">仅输入框</option>
          </select>
        </label>
      </div>

      <div className="editor-preview-grid">
        <div className="code-editor-shell">
          <div className="code-editor-title"><span>{languageLabels[language]}</span><small>theme.local.{language === "tokens" ? "json" : language}</small></div>
          <textarea aria-label="界面代码编辑器" value={code} onChange={(event) => { setCode(event.target.value); setStatus("有未预览的更改"); }} spellCheck={false} />
        </div>

        <div className="isolated-preview" aria-label="隔离界面预览">
          <div className="preview-title"><span>隔离预览</span><small>sandbox · no bridge</small></div>
          <div className="preview-window" style={{ "--preview-accent": accent } as CSSProperties}>
            <div className="preview-rail"><i /><i /><i /></div>
            <div className="preview-thread">
              <small>Harness</small>
              <p>界面代码只在这个预览边界内生效。</p>
              <div className="preview-composer"><span>输入消息…</span><b>↑</b></div>
            </div>
          </div>
          <div className="preview-scope"><span style={{ background: accent }} />{scope === "workspace" ? "对话工作台" : scope === "conversation" ? "仅消息区域" : "仅输入框"}</div>
        </div>
      </div>

      <div className="custom-editor-actions">
        <div className="editor-status" aria-live="polite"><span />{status}</div>
        <button type="button" className="quiet" onClick={() => { setCode(templates[language]); setStatus("已恢复当前语言模板"); }}>恢复模板</button>
        <button type="button" className="quiet" onClick={validate}>校验代码</button>
        <button type="button" className="primary" aria-label="应用到隔离预览" onClick={applyPreview}>应用到预览</button>
      </div>

      <div className="custom-code-boundary">
        <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M10 2.5 16 5v4.4c0 3.5-2.1 6.5-6 8.1-3.9-1.6-6-4.6-6-8.1V5l6-2.5Z" /><path d="m7.5 10 1.6 1.6 3.5-3.7" /></svg>
        <div><strong>JavaScript / TypeScript 不在主 Renderer 中执行。</strong><p>CSS 经过规则校验；HTML 只进入无脚本、无 DesktopBridge 的 sandbox iframe。完整组件需使用签名插件契约。</p></div>
      </div>
    </div>
  );
}
