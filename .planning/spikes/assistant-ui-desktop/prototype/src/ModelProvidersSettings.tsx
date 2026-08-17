import { useState } from "react";

type ProviderId = "openai" | "anthropic" | "gemini" | "compatible" | "custom";

const presets: Record<Exclude<ProviderId, "custom">, { name: string; baseUrl: string; format: string; model: string; capabilities: string[] }> = {
  openai: { name: "OpenAI", baseUrl: "https://api.openai.com/v1", format: "responses", model: "gpt-5.6", capabilities: ["对话", "Tool 调用", "推理", "视觉"] },
  anthropic: { name: "Anthropic", baseUrl: "https://api.anthropic.com", format: "anthropic", model: "claude-sonnet", capabilities: ["对话", "Tool 调用", "推理", "视觉"] },
  gemini: { name: "Google Gemini", baseUrl: "https://generativelanguage.googleapis.com", format: "gemini", model: "gemini-pro", capabilities: ["对话", "Tool 调用", "视觉"] },
  compatible: { name: "OpenAI-compatible", baseUrl: "http://127.0.0.1:11434/v1", format: "chat", model: "local-model", capabilities: ["对话", "Tool 调用"] },
};

const providerOrder: Exclude<ProviderId, "custom">[] = ["openai", "anthropic", "gemini", "compatible"];
const allCapabilities = ["对话", "Tool 调用", "推理", "视觉"];

export function ModelProvidersSettings() {
  const [selected, setSelected] = useState<ProviderId>("openai");
  const [name, setName] = useState(presets.openai.name);
  const [baseUrl, setBaseUrl] = useState(presets.openai.baseUrl);
  const [apiKey, setApiKey] = useState("");
  const [format, setFormat] = useState(presets.openai.format);
  const [model, setModel] = useState(presets.openai.model);
  const [capabilities, setCapabilities] = useState(presets.openai.capabilities);
  const [status, setStatus] = useState("尚未测试连接");

  const selectProvider = (id: Exclude<ProviderId, "custom">) => {
    const provider = presets[id];
    setSelected(id); setName(provider.name); setBaseUrl(provider.baseUrl); setFormat(provider.format); setModel(provider.model); setCapabilities(provider.capabilities); setApiKey(""); setStatus("尚未测试连接");
  };

  const addCustom = () => {
    setSelected("custom"); setName(""); setBaseUrl(""); setFormat("responses"); setModel(""); setCapabilities(["对话"]); setApiKey(""); setStatus("尚未测试连接");
  };

  const toggleCapability = (capability: string) => setCapabilities((current) => current.includes(capability) ? current.filter((item) => item !== capability) : [...current, capability]);

  return (
    <div className="model-provider-panel">
      <aside className="provider-list" aria-label="模型提供商">
        <div className="provider-list-heading"><strong>已配置提供商</strong></div>
        {providerOrder.map((id) => (
          <button type="button" className={selected === id ? "selected" : ""} aria-label={presets[id].name} onClick={() => selectProvider(id)} key={id}>
            <span className="provider-cube" aria-hidden="true" /><span><strong>{presets[id].name}</strong></span><i aria-label="已配置" />
          </button>
        ))}
        <button type="button" className={`add-provider${selected === "custom" ? " selected" : ""}`} aria-label="添加自定义提供商" onClick={addCustom}><span>+</span> 添加自定义提供商</button>
      </aside>

      <div className="provider-form">
        <div className="provider-form-heading"><div><h3>{selected === "custom" ? "添加模型提供商" : `配置 ${name}`}</h3></div><span className="provider-draft">原型</span></div>
        <div className="provider-fields">
          <label><span>供应商名称</span><input aria-label="供应商名称" value={name} onChange={(event) => setName(event.target.value)} placeholder="例如：本地 Ollama" /></label>
          <label><span>Base URL</span><input aria-label="Base URL" value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} placeholder="https://api.example.com/v1" /></label>
          <label><span>API Key</span><input aria-label="API Key" type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} autoComplete="off" /></label>
          <div className="provider-field-pair">
            <label><span>API 协议</span><select aria-label="API 协议" value={format} onChange={(event) => setFormat(event.target.value)}><option value="responses">Responses API</option><option value="chat">Chat Completions</option><option value="anthropic">Anthropic Messages</option><option value="gemini">Gemini GenerateContent</option></select></label>
            <label><span>默认模型</span><input aria-label="默认模型" value={model} onChange={(event) => setModel(event.target.value)} placeholder="model-id" /></label>
          </div>
          <fieldset className="capability-picker"><legend>声明能力</legend><div>{allCapabilities.map((capability) => <label key={capability}><input type="checkbox" checked={capabilities.includes(capability)} onChange={() => toggleCapability(capability)} /><span>{capability}</span></label>)}</div></fieldset>
        </div>
        <div className="provider-actions"><div className="provider-status" aria-live="polite"><span />{status}</div><button type="button" className="provider-test" aria-label="测试连接" onClick={() => setStatus("原型检查完成 · 未发送网络请求")}>测试连接</button><button type="button" className="provider-save">保存配置</button></div>
      </div>
    </div>
  );
}
