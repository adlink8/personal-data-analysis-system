# Pi 真实模型全流程测评记录（2026-08-11）

## 环境
- Provider: opencode.ai/zen/go/v1（openai-compatible），deepseek-v4-flash
- 思考关闭：thinking:{type:disabled} + enable_thinking:false（实测生效，output_tokens 3031→5）
- timeout_ms: 120s（thinking 模型需长超时，已配置化）

## 结果

### 真实模型调用（Python 决策分析引擎）
- structured_analysis → succeeded，返回真实 claims + recommendation
- 费用 0.006 元，tokens 164/3031

### Pi skill 全流程（11 个）
- 编排层（skill 引擎 → kernel → bridge → Python gateway → lease 校验）：全部工作
- 数据层：**只读工具返回 synthetic 占位**（生产 gateway 无 read_handler 注入）
- warehouse 类工具缺运行参数（authority_id 等）→ 失败
- evidence.sqlite_query：修复 lease 注入后过 manifest_drift，但缺 session_id → database_unknown

### 结论（Phase 55-57 实施后，2026-08-12）
44 工具真实数据接入完成：read_handler 分发 + warehouse metadata 真实化。
synthetic 消除，skill 全流程工具返回真实数据：
- daily_brief/research/decision.support/system.diagnosis/warehouse.health 全部 completed
- knowledge.search 返回真实 unit（cu|ccea34da...）
- warehouse.inspect 返回 175842 records / 216 failed
- 模型真实消费：decision.support 调 deepseek-v4-flash（39/29 tokens）

## 修复提交
- transport: 思考关闭双 flag
- kernel: evidence.sqlite_query lease 参数自动注入
- routes: openai-compatible 识别为真实 provider
- persistent-config: 明文 api_key + timeout_ms 配置化
