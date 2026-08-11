import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "../App";

describe("selected C composition", () => {
  it("opens directly to conversation and keeps secondary surfaces closed", () => {
    render(<App />);
    expect(screen.getAllByText("Agent 桌面 UI 复用方案")[0]).toBeVisible();
    expect(screen.getByLabelText("发送消息")).toBeVisible();
    expect(screen.getByLabelText("AgentsView 会话历史")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByLabelText("Tool、SQLite 与候选审核")).toHaveAttribute("aria-hidden", "true");
  });

  it("opens history and evidence as drawers instead of permanent pages", () => {
    render(<App />);
    fireEvent.click(screen.getByLabelText("所有会话"));
    expect(screen.getByLabelText("AgentsView 会话历史")).toHaveClass("open");
    fireEvent.click(screen.getByLabelText("关闭历史"));
    fireEvent.click(screen.getByLabelText("Tool 与证据"));
    expect(screen.getByLabelText("Tool、SQLite 与候选审核")).toHaveClass("open");
  });

  it("supports a keyboard command palette without adding a navigation page", () => {
    render(<App />);
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(screen.getByRole("dialog", { name: "命令面板" })).toBeVisible();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "命令面板" })).not.toBeInTheDocument();
  });

  it("opens settings from the bottom rail and returns to the conversation", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "设置" }));

    expect(screen.getByRole("heading", { name: "设置", level: 1 })).toBeVisible();
    expect(screen.getByRole("heading", { name: "常规" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "模型与运行时" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "对话与隐私" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "主动提醒" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "返回对话" }));
    expect(screen.getByLabelText("发送消息")).toBeVisible();
  });

  it("keeps settings controls local to the visual spike", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "设置" }));

    const proactiveToggle = screen.getByRole("switch", { name: "AI 主动提醒" });
    expect(proactiveToggle).toHaveAttribute("aria-checked", "true");
    fireEvent.click(proactiveToggle);
    expect(proactiveToggle).toHaveAttribute("aria-checked", "false");
    expect(screen.getByText("原型预览：设置只保存在当前页面，不写入真实 DesktopBridge。")).toBeVisible();
  });

  it("reveals custom window controls only for the custom window form", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "设置" }));

    expect(screen.getByRole("heading", { name: "界面与窗口" })).toBeVisible();
    expect(screen.queryByLabelText("窗口宽度")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: "自定义窗口" }));
    const width = screen.getByLabelText("窗口宽度");
    const height = screen.getByLabelText("窗口高度");
    expect(width).toHaveValue(1180);
    expect(height).toHaveValue(760);

    fireEvent.change(width, { target: { value: "1280" } });
    expect(width).toHaveValue(1280);
    expect(screen.getByRole("switch", { name: "窗口始终置顶" })).toHaveAttribute("aria-checked", "false");
  });

  it("lets the user edit interface code and apply it only to an isolated preview", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "设置" }));

    expect(screen.getByRole("heading", { name: "代码定制" })).toBeVisible();
    const editor = screen.getByRole("textbox", { name: "界面代码编辑器" });
    expect((editor as HTMLTextAreaElement).value).toContain("--harness-accent");

    fireEvent.change(editor, { target: { value: ":root { --harness-accent: #9cb8ff; }" } });
    fireEvent.click(screen.getByRole("button", { name: "应用到隔离预览" }));
    expect(screen.getByText("预览已更新 · 未写入应用")).toBeVisible();
    expect(screen.getByText("JavaScript / TypeScript 不在主 Renderer 中执行。")).toBeVisible();
  });

  it("rejects network-loading or script syntax before the custom code preview", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "设置" }));
    const editor = screen.getByRole("textbox", { name: "界面代码编辑器" });

    fireEvent.change(editor, { target: { value: "@import url('https://example.com/theme.css');" } });
    fireEvent.click(screen.getByRole("button", { name: "应用到隔离预览" }));
    expect(screen.getByText("检测到网络资源或脚本语法，隔离预览已拒绝。")).toBeVisible();
  });

  it("groups settings like ZCode and exposes model provider configuration", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "设置" }));

    expect(screen.getByText("基础设置")).toBeVisible();
    expect(screen.getByText("Agent 能力")).toBeVisible();
    expect(screen.getByText("系统")).toBeVisible();
    expect(screen.getByRole("heading", { name: "模型接入" })).toBeVisible();
    expect(screen.getByRole("button", { name: "OpenAI" })).toBeVisible();
    expect(screen.getByLabelText("API Key")).toHaveAttribute("type", "password");
  });

  it("supports adding and testing a custom model provider in the spike", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "设置" }));
    fireEvent.click(screen.getByRole("button", { name: "添加自定义提供商" }));

    const name = screen.getByLabelText("供应商名称");
    fireEvent.change(name, { target: { value: "本地 Ollama" } });
    expect(name).toHaveValue("本地 Ollama");
    fireEvent.click(screen.getByRole("button", { name: "测试连接" }));
    expect(screen.getByText("原型检查完成 · 未发送网络请求")).toBeVisible();
  });
});
