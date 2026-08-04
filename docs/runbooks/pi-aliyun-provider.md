# Pi 阿里云百炼 Provider 接入

当前 Pi 默认使用 `replay`，不会产生网络请求或费用。阿里云百炼通过 OpenAI-compatible Chat Completions 接入，真实模式必须显式开启，并先完成 Phase 53 的 baseline/UAT。

## 持久化配置（Windows）

不要把 Key 写入代码。使用 Windows DPAPI 将 Key 绑定到当前 Windows 用户/机器，Pi 启动时临时解密到内存：

```powershell
pwsh -File .\tools\supported\configure_pi_aliyun.ps1 -ProjectRoot (Get-Location).Path -CostCeiling 0.10
```

脚本会持久化：

- 非敏感配置：`var/config/pi-provider.json`
- DPAPI 加密 Key：`var/secrets/dashscope.api.dpapi.txt`

两者都在 `var/` 下，不会进入 Git。当前 Windows 用户或机器变化后，DPAPI secret 不能被其他账户直接解密，需要重新配置。

## 本地配置

PowerShell 示例：

```powershell
$env:PI_PROVIDER_MODE = "aliyun"
$env:PI_PROVIDER_BASE_URL = "https://ws-5z3x3ey9xg0x32ya.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
$env:PI_PROVIDER_MODEL = "deepseek-v4-flash-0731"
$env:PI_PROVIDER_COST_CEILING = "0"
$env:DASHSCOPE_API_KEY = "<set-locally-never-commit>"
```

`DASHSCOPE_API_KEY` 不得写入源码、日志、提交或聊天记录。`PI_PROVIDER_COST_CEILING` 应在真实 baseline 前替换为已批准的单次成本上限；`0` 只表示当前未配置付费激活预算，不应作为 primary 授权值。持久化配置优先于环境变量，但环境变量仍可用于临时覆盖。

## 调用边界

- transport 使用 `POST {BASE_URL}/chat/completions`，请求使用 `Bearer DASHSCOPE_API_KEY`。
- `deepseek-v4-flash-0731` 当前不支持原生结构化输出；Pi 对该模型使用“仅返回 JSON 对象”的系统约束并在 receipt 边界校验 JSON。
- 北京地域当前官方原价为输入 1 元/百万 Token、输出 2 元/百万 Token；实际优惠和账单以百炼控制台为准。
- API 返回的 `choices[0].message.content` 必须是 JSON 对象，才会转换成 Pi receipt。
- 请求身份绑定 `task_id/session_id/idempotency_key`；`outcome_unknown` 不自动重试。
- 未设置 `PI_PROVIDER_MODE=aliyun` 时，路由保持 `replay/replay-v1`。
- 真实调用前仍需完成真实 cohort、成本/调用上限、签名浏览器 UAT、shadow/canary 和显式 primary 确认；任何失败只允许降级回 `legacy`。
