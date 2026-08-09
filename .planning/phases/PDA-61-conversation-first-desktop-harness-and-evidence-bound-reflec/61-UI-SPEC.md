---
phase: 61
slug: conversation-first-desktop-harness-and-evidence-bound-reflection-loop
status: approved
shadcn_initialized: false
preset: none
created: 2026-08-09
approved: 2026-08-09
---

# Phase 61 — UI Design Contract

> 面向本地 Electron Walking Skeleton 的视觉与交互合同。对话是唯一的首屏；Cockpit 不是视觉参考，也不在本阶段替换或删除。

---

## Contract Sources and Boundaries

| Source | Binding decision used |
|---|---|
| `61-CONTEXT.md` D-04..D-08 | Electron Web 壳、最后一段对话直达、Codex 式紧凑导航、按需深层能力、默认收起的 Tool 细节 |
| `61-CONTEXT.md` D-14..D-17 | AgentView 聚合、新鲜度双水位、受限只读 SQLite 与可钻取 receipt |
| `61-CONTEXT.md` D-18..D-25 | 确定性反思触发、Evidence/Candidate/Projection 分层、行内审核、冲突与反馈边界 |
| `sketches/001` winner A | 固定双栏：左侧项目/会话导航，中央稳定对话区 |
| `sketches/002` winner A | 受限 SQLite 查询作为助手消息旁的行内结果卡 |
| `sketches/003` winner C | 个人模型按时间演变、情境和转折点呈现，不作人格总分 |
| `sketches/004` winner A | 启动简报是可继续的首条对话，而非仪表盘 |
| `sketches/005` winner A | 深层审核按来源批次组织，风险、证据和冲突显式可见 |
| `sketches/006` winner A | 当前项目内的统一搜索/提问入口；洞察只进入审核队列 |

本合同只覆盖 HARNESS-01..08 的一个纵向路径。不得在 renderer 中显示原始个人正文、凭据、任意 SQL、完整内部 trace，或把模型生成文本表达为已写入事实。

---

## Design System

| Property | Value |
|---|---|
| Tool | none — 尚无 Phase 61 组件库或 `components.json`；不初始化或引入第三方 registry |
| Preset | not applicable |
| Component library | none specified；实现使用原生可访问语义与项目已有 Web 技术 |
| Icon library | 未指定；所有控制使用同一套 24×24 SVG 图标并保留可见文字标签或 `aria-label`，不得以 emoji 充当控制图标 |
| Font | `Segoe UI, Microsoft YaHei UI, system-ui, sans-serif`；查询与 receipt 使用 `Cascadia Code, SFMono-Regular, Consolas, monospace` |
| Theme | 默认深色。浅色模式必须保持同一语义层级与对比度，不得改变状态含义；本阶段的像素基准是已提交草图的深色 token |

### Surface tokens

| Token | Dark value | Required usage |
|---|---:|---|
| `bg` | `#181818` | 60% 主内容背景、对话画布、代码/SQL 背景 |
| `surface` | `#1A2228` | 30% 侧栏、顶栏、普通卡片和导航 |
| `surface-raised` | `#242424` | composer、抽屉、弹窗、展开的 receipt |
| `selected` / `border` | `#2D3237` | 当前导航、选中行、分隔线、输入框边界 |
| `text` | `#F1F1F1` | 正文与可操作主文本 |
| `text-muted` | `#A2A7AC` | 时间、来源、范围、限制、辅助说明 |
| `primary` | `#E8E8E8` | 主按钮和键盘焦点环；深色文字 `#181818` |
| `success` | `#72C98F` | 仅“已完成/在线/只读查询成功”，不得用作一般 CTA |
| `danger` | `#EF9389` | 仅错误、拒绝与真正破坏性动作 |

---

## Spacing Scale

Declared values (all multiples of 4):

| Token | Value | Usage |
|---|---:|---|
| xs | 4px | 行内 badge、图标与标签间距 |
| sm | 8px | 紧凑按钮、消息元数据、卡片内操作 |
| md | 16px | 默认控件与卡片内边距、侧栏条目 |
| lg | 24px | 顶栏左右内边距、抽屉内边距、区块间距 |
| xl | 32px | 对话正文水平内边距、主内容区间距 |
| 2xl | 48px | 首屏/主区块顶部留白 |
| 3xl | 64px | 仅用于空态或大区段的垂直呼吸区 |

Exceptions: 232px 固定展开侧栏；344px 证据检查器；结果/上下文抽屉宽度最大 392px；图标按钮和所有可点击的紧凑控件最小命中区域 36×36px。桌面主布局在 >=1024px 使用双栏；901–1023px 保留侧栏、按需抽屉覆盖主区；<=900px 隐藏常驻检查器；<=640px 将导航变为可打开抽屉，绝不让 composer 或关键确认被遮挡。

---

## Typography

只使用以下四个字号与两种字重；等宽元数据可沿用相同字号。

| Role | Size | Weight | Line Height |
|---|---:|---:|---:|
| Metadata / Label | 12px | 400 | 1.5 |
| Body | 14px | 400 | 1.5 |
| Section heading | 17px | 600 | 1.2 |
| Conversation display heading | 28px | 600 | 1.2 |

时间、receipt ID、查询 checksum、来源和 freshness 使用 12px 等宽字；不以字重或颜色单独表达风险，必须同时给出明确文字标签。

---

## Color

| Role | Value | Usage |
|---|---|---|
| Dominant (60%) | `#181818` | 对话背景、中央阅读面、SQL code 区 |
| Secondary (30%) | `#1A2228` / `#242424` | 侧栏、顶栏、普通卡片、composer、抽屉、modal |
| Accent (10%) | `#E8E8E8` | 仅主 CTA、当前键盘 focus ring、被明确选中的主操作 |
| Success semantic | `#72C98F` | 只读查询成功、已连接、已完成；必须配文字状态 |
| Destructive | `#EF9389` | 查询/系统错误、明确拒绝或将来真实破坏性动作；Phase 61 无删除型 CTA |

Accent reserved for: composer 的“发送消息”、确认后提交的“接受候选”、当前键盘 focus ring，以及单一选中的主操作。普通导航、筛选、展开 SQL、查看证据、取消、忽略、延后均使用 secondary/outline 样式。

---

## Information Architecture and Layout

1. 启动即恢复最后一段对话；无“首页仪表盘”过渡。若没有历史会话，中央区域显示新会话空态并自动聚焦输入框。
2. 左侧 232px 导航从上到下固定为：`新建对话`、`最近对话`、`项目` scopes；底部为 `个人模型` 与 `系统`。最近会话显示标题、项目和最后活动时间；项目只显示名称与简短同步/待处理状态。
3. 中央为 760–820px 最大阅读宽度的对话线程。顶部只显示当前项目 scope、会话标题和双水位状态；底部固定 composer，内容底部必须预留至少 132px，避免被 composer 覆盖。
4. `今日简报`、`收件箱`、`探索`、`反思`、`个人模型` 是按需入口，不在会话旁常驻成多张仪表盘。右侧证据抽屉、命令面板和确认 modal 必须可关闭并回到原对话锚点。
5. 个人模型详情采用“时间演变”视图：按阶段/转折点比较同一推断的历史版本、适用情境、支持与冲突证据、有效时间和 supersession；禁止总分、雷达图或人格定论。

---

## Interaction Contract

### Conversation turn

- 输入框 placeholder：`继续这段对话…`。Enter 发送，Shift+Enter 换行；发送后立即在本地线程中显示用户消息与“正在检索已授权资料”的非权威进度行。
- 每一助手答案结尾固定显示三个可展开但默认紧凑的区块：`依据`、`新鲜度`、`限制`。它们必须说明来源数量/身份、source→AgentView 水位、AgentView→canonical 水位或 backlog，以及结论不覆盖的资料范围。
- Skill/Tool 执行默认折叠为“已使用受限能力”行：显示 Skill 名称（或“未选择 Skill”）、只读/副作用等级、结果状态和 receipt 数量；不显示模型思维过程、私有正文、credential 或未授权参数。
- 用户可从答案或 command palette 打开 `查看 receipt`。展开后仅显示：操作名、授权 scope、数据库/来源 identity、freshness/version binding、query checksum、行数/字节/时长、truncation、结果状态与 receipt ID。`复制 receipt ID` 可以复制 identifier，不能复制敏感 body。
- 取消执行时，当前行显示 `已取消：没有写入，也没有保留部分结果。`；恢复时显示原任务状态、恢复入口和“不确定结果需 reconcile”的提示。不得把取消显示为成功。

### Governed SQLite evidence card

- 只读查询在触发它的助手消息下方显示行内卡（Sketch 002A），默认不展开 SQL。卡头恒为 `SQLite · 只读查询`，并含文字状态，不能只用绿色圆点。
- 卡片第一行必须显示 `查询范围`、`耗时`、`返回`；第二行提供 `展开 SQL`、`查看 N 条证据`、`查看 receipt`。SQL 展开区只可显示已执行且已脱敏的 allowlisted statement；禁止自由编辑器、运行按钮或任意 schema 浏览。
- 同一张卡中必须同时展示：数据库/source identity、query checksum、最新同步时间、source→AgentView 与 AgentView→canonical freshness/backlog、truncation（如有）和“只代表已授权、已索引范围”的限制。
- 空结果：`当前授权范围没有匹配记录；查询范围未扩大。`。拒绝：`查询未执行：{安全原因}。请改为在已授权范围内提问。`。服务错误：`证据索引暂不可用；没有执行写入。请重试或查看系统状态。`。三种状态均保留 receipt/错误 code，但不回显 SQL body 或私有数据。

### Reflection Candidate and personal-model projection

- 确定性 conversation-delta 产生 Candidate 后，在关联对话中插入行内 `待审核候选` 卡。卡必须显示：推断状态、置信度、时间范围、项目/情境、支持证据数、冲突数、来源 event/receipt，以及 `AI 生成的候选，尚未成为事实`。
- 卡片固定动作顺序：`查看候选证据`、`编辑候选`、`接受候选`、`忽略候选`。`查看候选证据` 打开右侧抽屉并并列显示支持与冲突证据；来源缺失时明确显示“不能用推断补全”。
- `编辑候选` 打开 modal/drawer，保留只读的 `AI 原稿` 与可编辑审核版本并存。提交按钮为 `接受审核版本`；保存前展示将进入现有 Candidate/canonical path 的内容摘要、证据数量和 projection 影响。
- `接受候选` 与 `接受审核版本` 都必须经过明确确认 modal：标题 `接受候选？`，正文 `这会把审核版本送入现有受控 Candidate/canonical 流程，并更新派生个人模型投影；不会把 AI 原稿直接写成事实。` 按钮 `确认接受候选` / `返回候选修改`。成功后卡片变为 `已送交受控流程`，显示 receipt 和 projection version；不声称已完成 promotion。
- `忽略候选` 记录 feedback 且不删除 Evidence、Candidate 或审计 history；toast 为 `已忽略候选；原始证据和审核记录仍可追溯。`，提供本会话内 `撤销忽略候选`。`延后候选`（深层收件箱中可用）保持来源批次、风险和排序。
- 高影响或存在冲突的 Candidate 禁止批量接受。必须逐项打开具焦点圈定的冲突处理 modal，选项严格固定为：`keep_existing`（`保留旧结论`，后果：保持既有受控结论不变，仅保留本次审核与证据）、`replace_existing`（`用新结论取代`，后果：仅经受控审核路径将审核版本作为后续派生投影的候选，不直接写成事实）、`coexist_by_context`（`按情境共存`，后果：保留两个有来源的情境化结论，不宣称单一通用结论）、`defer_judgment`（`暂不判断`，后果：不更新派生投影，保留证据与审核反馈待后续处理）。未知或缺失值必须拒绝；Esc 关闭 modal 并把焦点还给触发控件。
- 后续会话引用 Projection 时，在答案旁显示 `派生个人模型` 标签、version、置信度、有效时间、freshness、支持/冲突 evidence 数和“可被纠正”入口；不得称作个人事实或稳定人格标签。

### Proactive and deep views

- 只渲染确定性触发的事项，并以 `静默 badge → 行内卡 → 抽屉 → 需要确认才 modal` 的层级升级。`静默 badge` 位于对话线程中被静默的主动事项原本应出现的锚点，并显示 `静默至 {HH:MM}`；它不改变用户手动消息的顺序，也不得自动打开 modal。
- 从左侧底部 `系统` 入口打开 `主动提醒` 设置 drawer；command palette 同时提供 `管理主动提醒`。该 drawer 固定暴露两类粒度控制：逐类启用/停用（`同步`、`简报`、`反思候选`）与逐项目/全局范围选择；每类控制旁显示当前状态和作用范围。`静默时段` 使用开始/结束时间控件，并在保存后将当前状态回显为 `静默至 {HH:MM}`。
- 同一 evidence cluster 只生成一张主动行内卡。卡片 metadata 显示 `已合并 {N} 条同簇证据`；`查看合并证据` 在右侧抽屉中列出每条已合并 evidence 的来源、时间和 receipt，并保留支持/冲突关系。抽屉不得将去重隐藏为单一、无来源的结论。
- 收件箱按来源批次（sync、简报、问答等）分组；当前批次优先，高影响与冲突保留显眼文字标识，历史低优先级积压不与其混排。
- 探索使用一个输入框；问题形式自动标为 `证据型问答`，否则为 `关键词检索`。默认范围是当前项目；切到全局前显示 scope 变化。模型离线时关键词检索仍可用，证据型问答明确暂停。

---

## State, Feedback, and Accessibility

| State | Required UI behavior |
|---|---|
| Loading | 就地 skeleton/文字进度；说明当前是受限读取或受控提交，允许取消，不伪造结果 |
| No conversation | 标题 `从一段对话开始。`；正文 `选择项目后提出问题；系统只会使用已授权且可追溯的资料。`；CTA `发送第一条消息` |
| No evidence | `没有可引用的证据。` + `当前 scope 未找到已授权且已索引的记录；不会扩大查询范围。` |
| Stale / backlog | 顶栏和相关答案都显示两段 freshness、最后同步时间与 backlog；不可用“已就绪”掩盖 stale |
| SQLite rejected | 行内 `查询未执行` card，原因和可恢复建议；不显示敏感语句内容 |
| Candidate empty | `当前没有待审核候选。` + `新的确定性事件产生候选后，会连同证据和时间范围出现在这里。` |
| Error | `操作未完成：{safe summary}。没有发生未授权变更。` + `重试操作` 或 `查看系统状态` |

- 所有交互以键盘可达，Tab 顺序与视觉顺序一致；提供跳到对话主区的 skip link。`Esc` 依次关闭 command palette、drawer、modal，且焦点回到触发控件。
- 可见 focus ring 固定为 2px `#E8E8E8`、2px offset；hover/focus 动画仅变色/透明度/阴影，150–200ms，不改变布局。
- 消息发送、状态更新和错误分别使用 `aria-live="polite"` 与 `role="alert"`；modal 使用焦点圈定和明确标题/描述。颜色永远不是唯一状态载体。
- 遵从 `prefers-reduced-motion`：关闭自动渐入、打字和抽屉滑动动画，状态仍立即可感知。
- 所有用户可见 copy、receipt 和错误都不得包含个人正文、凭据、原始查询参数中的敏感值或模型隐藏 reasoning。

---

## Copywriting Contract

| Element | Copy |
|---|---|
| Primary CTA | 发送消息 |
| Composer placeholder | 继续这段对话… |
| Capability disclosure | 仅使用已授权资料；结果会标注依据、新鲜度与限制。 |
| Empty state heading | 从一段对话开始。 |
| Empty state body | 选择项目后提出问题；系统只会使用已授权且可追溯的资料。 |
| Evidence empty state | 当前授权范围没有匹配记录；查询范围未扩大。 |
| Error state | 操作未完成：{safe summary}。没有发生未授权变更。请重试或查看系统状态。 |
| Candidate disclosure | AI 生成的候选，尚未成为事实。 |
| Candidate accept confirmation | 这会把审核版本送入现有受控 Candidate/canonical 流程，并更新派生个人模型投影；不会把 AI 原稿直接写成事实。 |
| Non-destructive confirmation | 忽略候选：已忽略候选；原始证据和审核记录仍可追溯。 |
| Destructive confirmation | Phase 61 没有删除型用户动作；忽略、拒绝和延后均保留 append-only 审计记录，不能使用 destructive 样式冒充删除。 |

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|---|---|---|
| shadcn official | none | not applicable — `components.json` absent and no initialization decision |
| third-party | none | not applicable — no third-party registry or block is permitted by this contract |

---

## Checker Sign-Off

- [ ] Dimension 1 Copywriting: PASS
- [ ] Dimension 2 Visuals: PASS
- [ ] Dimension 3 Color: PASS
- [ ] Dimension 4 Typography: PASS
- [ ] Dimension 5 Spacing: PASS
- [ ] Dimension 6 Registry Safety: PASS

**Approval:** pending
