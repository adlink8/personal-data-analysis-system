# 数据治理

> **一句话：** 数据治理告诉你哪些文件能提交、哪些不能、放在哪里、能保留多久、怎么删除。

---

## 一、文件放哪里：9 个区域

```ascii
版本控制区（git track，安全）         私有数据区（git ignore，小心）
┌────────┐ ┌────────┐ ┌──────────┐   ┌──────────┐ ┌──────────┐
│  src   │ │  docs  │ │governance│   │   data   │ │   var    │
│  源码  │ │  文档  │ │ 治理策略  │   │ 个人数据  │ │ DB/日志  │
│  R2    │ │  R1    │ │  R2      │   │  R4      │ │  R4      │
└────────┘ └────────┘ └──────────┘   └──────────┘ └──────────┘
```

**判断原则：** 只要是个人数据（对话记录、Google 活动、数据库文件、运行日志），一定在 `data/` 或 `var/` 或 `archive/` 里，git ignore，R4 隐私，不能提交、不能打包、不能公开。

## 二、隐私等级：R1 到 R4

| 等级 | 内容举例 | 能提交 git？ | 能公开？ | 能审计内容？ |
|------|---------|-------------|---------|------------|
| **R1** | 公开文档、测试夹具 | ✅ track | ✅ | ✅ |
| **R2** | 源码、策略文件、规划 | ✅ track | ❌ 仅聚合 | 仅元数据 |
| **R3** | 嵌入向量、评测输出 | ❌ ignore | ❌ 仅聚合 | ❌ 禁止 |
| **R4** | 原始证据、对话库、DB 文件 | ❌ ignore | ❌ 禁止 | ❌ 禁止 |

**特别注意：** WAL、SHM、journal、backup 文件继承父文件的隐私等级。未知分类默认 R4 + fail-closed。

## 三、制品分层：D → S → R → A

每一条数据制品在系统中的角色：

| 层 | 含义 | 例子 | 证据来源 | 能否重建 |
|----|------|------|---------|---------|
| **D** | 规范化权威数据 | `d.canonical_conversation`（对话库） | 来自原始数据 | 版本化 |
| **S** | 从 D 推断的语义 | `s.knowledge_unit`（知识单元 Q&A） | 来自 D | 受控更新 |
| **R** | 可重建的检索索引 | `r.knowledge_index`（Chroma 向量） | 来自 S | ✅ 可重建 |
| **A** | 分析/评测输出 | `a.personal_change`（状态分析 run） | 来自 S/R | ❌ 不可变 |

**关键规则：** A 可以依赖下面所有层，D 只能依赖 D。违反这个依赖方向在 `preflight --ci` 会报错。

## 四、保留策略：东西能留多久

| 策略 | 适用范围 | 保留多久 | 怎么删 |
|------|---------|---------|--------|
| `source-controlled` | 源码/测试/文档/策略 | 仓库历史永存 | 走 git |
| `raw-private` | `data/` 原始数据 | 你说了算 | 你确认 + lineage tombstone |
| `mutable-private-store` | `var/` DB/运行时 | 活跃期 + 备份窗口 | 确认下游已处理后删除 |
| `derived-artifact` | 生成的/向量/reports | 最新 + release 证据 | 证明可重建后才能删 |
| `runtime-cache` | 缓存 | 用完就删 | 进程锁检查后删 |
| `archive-quarantine` | `archive/` 隔离区 | 直到审查通过 | 仅 cohort 批准 |

**删除一条数据的完整流程：**

```
raw → normalized → canonical → candidate → vector → report → backup → archive

每一步需要记录：
  request_id + 谁删的 + 范围 + 预览 + 批准 + journal + 事后检查 + 回滚方案
```

## 五、依赖规则：模块能引用谁

```
core (地基)          ← 只能引用自己
  ↑
infrastructure       ← 可以引用 core
  ↑
domain (规则/常量)    ← 可以引用 core + infrastructure
  ↑
application (构建)    ← 可以引用下面全部
  ↑
evaluation (评测)     ← 可以引用下面全部
  ↑
services (外部服务)   ← 可以引用下面全部
  ↑
governance (控制面)   ← 只能引用自己
```

**典型违规：** `core/llm.py` 导入了 `application/sync.py` → preflight 报 P1。

## 六、自动合规检查

```powershell
python -m personal_knowledge.governance.preflight --ci
```

这命令查 4 件事：

| 检查 | 怎么查 | 发现问题会怎样 |
|------|--------|-------------|
| 架构边界 | AST 扫描各文件的 import，和 `architecture.yaml` 对比 | P1 违规，必须修 |
| 密钥泄露 | 在安全目录扫描 `sk-*`、`AIza*`、`-----BEGIN PRIVATE KEY-----` | P0 紧急，立刻修 |
| 依赖一致性 | `requirements.txt` vs `constraints.txt` 对比 | P2 警告 |
| 制品注册表 | `artifact_layers.yaml` 格式/必填字段/依赖方向 | P1 违规 |

## 七、服务快照

每次 promote 知识索引时，创建一个不可变快照，绑定 10 项服务角色：

```
serving_snapshot_events 表：
  每次 activate/rollback 记录事件

快照验证每个角色需要：
  ✓ 制品注册表有版本记录
  ✓ Chroma 条数 + checksum 匹配
  ✓ eval gate PASS
  ✓ 水印顺序正确
  ✓ 证据可正常解析
```

## 八、外部数据源治理

只有两类外部来源被允许摄入，且只存元数据和结构化事实：

| 来源 | 许可证 | 用途 |
|------|--------|------|
| Python 版本信息 | PSF License | 记录项目使用的 Python 版本 |
| Node.js 版本信息 | MIT | 记录 Node.js 版本 |

不允许摄入：文章正文、网页内容、个人数据。
