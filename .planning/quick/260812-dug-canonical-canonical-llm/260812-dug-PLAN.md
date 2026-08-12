---
phase: quick
plan: 260812-dug
type: execute
wave: 1
depends_on: []
files_modified:
  - src/personal_knowledge/application/knowledge/quarantine_manifest.py
  - src/personal_knowledge/application/knowledge/legacy_isolation.py
  - src/personal_knowledge/application/knowledge/isolate_legacy_knowledge.py
  - tests/integration/test_isolate_legacy_knowledge.py
  - archive/quarantine/knowledge_generations/<generation_id>/manifest.json
  - archive/quarantine/knowledge_generations/<generation_id>/personal_system.sqlite
  - var/reports/analysis/ai_context/knowledge_rebuild_prepare_<generation_id>.json
autonomous: false
must_haves:
  truths:
    - 原始 AgentView、canonical/normalized 会话和 Google 源数据保持不变。
    - 全部旧 KU、inventory、run ledger、response cache、lifecycle 和 knowledge index version 从 live SSOT 移出，并保留可校验 SQLite 快照。
    - 旧 Chroma knowledge collections 不删除；服务切换到零条目的独立空白 collection。
    - 任何失败（包括 snapshot authority 已提交但 pointer 投影失败）都恢复 SQLite authority、旧 pointer 和迁移前指纹。
    - 不执行 `pk-ku extract` 或其他付费 LLM 调用；只产生 user/assistant 两轨 prepare 与费用估算。
  artifacts:
    - path: src/personal_knowledge/application/knowledge/quarantine_manifest.py
      provides: quarantine manifest、校验和、SQLite online backup 与受约束 restore
    - path: src/personal_knowledge/application/knowledge/legacy_isolation.py
      provides: KU 派生表隔离事务、空白 Chroma generation、snapshot 切换与 rollback 状态机
    - path: src/personal_knowledge/application/knowledge/isolate_legacy_knowledge.py
      provides: 薄 CLI（plan/apply/rollback）和显式写入确认
    - path: tests/integration/test_isolate_legacy_knowledge.py
      provides: dry-run、保留源、故障注入恢复、manifest 漂移拒绝和显式 rollback 证明
    - path: archive/quarantine/knowledge_generations/<generation_id>/manifest.json
      provides: 真实迁移 before/after、备份 checksum、旧 collection 清单、恢复目标
    - path: var/reports/analysis/ai_context/knowledge_rebuild_prepare_<generation_id>.json
      provides: 两轨重新提取清单、调用量/token/费用估算和付费 checkpoint
  key_links:
    - from: src/personal_knowledge/application/knowledge/isolate_legacy_knowledge.py
      to: src/personal_knowledge/application/knowledge/quarantine_manifest.py
      via: CLI 只编排 plan/apply/rollback，不直接写 SQLite/Chroma
    - from: src/personal_knowledge/application/knowledge/legacy_isolation.py
      to: src/personal_knowledge/application/serving/snapshots.py
      via: prepare/validate/activate；projection_ok=false 必须升级为失败并按 manifest 恢复
    - from: archive/quarantine/knowledge_generations/<generation_id>/manifest.json
      to: archive/quarantine/knowledge_generations/<generation_id>/personal_system.sqlite
      via: manifest 中的 SHA-256、原 active snapshot/pointer 与源表指纹
    - from: var/reports/analysis/ai_context/knowledge_rebuild_prepare_<generation_id>.json
      to: data/canonical/agent/structured/db/agent_conversations.sqlite
      via: user/assistant 两轨 prepare 重新计算，禁止复用旧 ledger/cache
---

<objective>可回滚地隔离全部旧派生知识，切换到不服务旧 KU 的空白 serving generation，并从保留的 canonical 会话生成两轨重建估算；在任何付费 LLM extract 前停止。</objective>

<tasks>

<task type="execute">
<name>Task 1: 以 Red→Green 实现可回滚的知识隔离边界</name>
<files>src/personal_knowledge/application/knowledge/quarantine_manifest.py; src/personal_knowledge/application/knowledge/legacy_isolation.py; src/personal_knowledge/application/knowledge/isolate_legacy_knowledge.py; tests/integration/test_isolate_legacy_knowledge.py</files>
<action>先写失败测试，再实现三个职责清晰的模块。`quarantine_manifest.py` 只负责枚举允许目标、SQLite online backup、SHA-256 manifest、原 pointer/snapshot/源表指纹和受约束 restore；restore 只接受本命令生成、schema 匹配且 checksum 通过的精确 manifest。`legacy_isolation.py` 负责 fail-closed 状态机：验证 schema/FK 和服务停机前置条件，创建零条目 Chroma collection，事务内按 FK 顺序清空全部旧 knowledge 派生表并建立新的 empty generation/index 记录，以当前完整 snapshot 为底仅替换 canonical_knowledge、knowledge_retrieval、knowledge_evaluation，验证后 activate。旧 Chroma collections 只记录、不删除。若任何步骤失败，特别是 `activate_snapshot()` 返回 `ok=true, projection_ok=false`，必须视为迁移失败：从 manifest 恢复 SQLite（含 serving_authority）、恢复旧 pointer、删除仅本次新建的空 collection，并重新验证指纹一致。`isolate_legacy_knowledge.py` 保持薄 CLI，提供默认只读 `plan`、需 `--write --i-know` 的 `apply` 和精确 `--manifest` 的 `rollback`；不得包含裸 SQL 状态机。</action>
<acceptance_criteria>dry-run 零写入；原始/canonical/normalized/Google 表未进入清空 allowlist；成功路径只留下新的空 generation；旧 collection 均保留；所有故障注入路径恢复 snapshot authority、pointer、DB checksum/计数；未知表、未知 FK、manifest 漂移或服务仍在读取时 fail closed。</acceptance_criteria>
<verify>python -m pytest -q tests/integration/test_isolate_legacy_knowledge.py</verify>
<done>集成测试全部通过，隔离边界可回滚且源数据不在任何删除 allowlist。</done>
</task>

<task type="execute">
<name>Task 2: 执行真实隔离并证明 live 系统只服务空白知识代</name>
<files>archive/quarantine/knowledge_generations/&lt;generation_id&gt;/manifest.json; archive/quarantine/knowledge_generations/&lt;generation_id&gt;/personal_system.sqlite; var/db/personal_system.sqlite; var/db/knowledge_index_active.txt</files>
<action>精确识别并停止 REST/MCP/Kernel 等知识消费者，保留 Chroma 8001 运行。先运行 CLI `plan` 并核对目标 DB、活动 snapshot/pointer、旧 collection 清单、派生表计数和保留源指纹；再运行 `apply --write --i-know`。完成后重启消费者，检查 DB integrity、manifest、snapshot/pointer/index 三方一致和空 collection count=0。运行真实 semantic 查询：知识层必须返回 0 条或明确走 canonical/raw fallback，绝不能命中旧 KU。若任一验收失败，立即用本次精确 manifest rollback 并再次验证迁移前指纹。</action>
<acceptance_criteria>`quick_check=ok`、FK violations=0；旧 KU/inventory/ledger/cache/lifecycle/index 表均为 0（只允许新的 empty generation/index 记录）；AgentView/canonical/normalized/Google 指纹与 before 一致；active snapshot、pointer 和 active index 指向同一空 collection；旧 collections 仍存在但均非 active；真实查询不返回旧 KU。</acceptance_criteria>
<verify>python -m personal_knowledge.application.knowledge.isolate_legacy_knowledge plan --json; python -m personal_knowledge.application.knowledge.isolate_legacy_knowledge apply --write --i-know --json; pk-ku doctor --json; rag-search stats --json; rag-search semantic "PPT 排版" --top-k 3 --json</verify>
<done>真实 live 迁移完成，旧 KU 不再服务，quarantine manifest 可恢复且所有保留源指纹不变。</done>
</task>

<task type="execute">
<name>Task 3: 从 canonical 生成 user/assistant 两轨重建估算并停在付费边界</name>
<files>var/reports/analysis/ai_context/knowledge_rebuild_prepare_&lt;generation_id&gt;.json</files>
<action>仅运行无费用 prepare：`pk-ku prepare --model gemini-3.5-flash-lite --track user --roles user --no-skip-succeeded --artifact var/reports/analysis/ai_context/knowledge_rebuild_prepare_&lt;generation_id&gt;_user.json`，以及 `pk-ku prepare --model gemini-3.5-flash-lite --track assistant --roles assistant --no-skip-succeeded --artifact var/reports/analysis/ai_context/knowledge_rebuild_prepare_&lt;generation_id&gt;_assistant.json`。合并两份隐私安全统计为总报告，记录 canonical source checksum、eligible/queued、排除原因、prompt 版本、预计 calls/tokens/cost、建议试点和批次。命令参数以本机 `pk-ku prepare --help` 为准；本机 BooleanOptionalAction 明确提供 `--no-skip-succeeded`。严禁运行 `pk-ku extract`、provider generate 或任何付费调用。</action>
<acceptance_criteria>user 轨仅 user、assistant 轨仅 assistant；两份 prepare 绑定当前 canonical checksum 且不读取旧 ledger/cache；报告不含正文/引文/密钥；live KU 和空白 serving generation 保持不变；最终输出下一条精确 extract 命令和预算，但标记为 blocked_pending_user_cost_approval。</acceptance_criteria>
<verify>pk-ku prepare --help; pk-ku inspect; pk-ku doctor --json; 确认知识单元仍为 0、空 collection 仍 active，并确认本轮 provider paid call count=0</verify>
<done>两轨无费用 prepare 与预算报告生成，系统仍为空白知识代，付费 extract 未执行。</done>
</task>

</tasks>

<verification>计划只有在沙箱故障回滚测试通过、真实 source 指纹不变、live 空代可查询且两轨 prepare 完全无付费调用时才算完成。任何 projection drift、旧 KU 命中或 source checksum 改变都必须 rollback，而不是带风险继续。</verification>

<success_criteria>旧派生知识不再进入服务路径；完整旧状态可由单一 manifest 恢复；canonical 会话保持权威输入；重建预算已生成但付费 LLM 尚未启动。</success_criteria>
