# AI-SPEC — Phase 14: Training-style Knowledge Unit RAG

> 由 `gsd-ai-integration-phase` 约束的 AI 设计合同。Phase 14 planner/executor/eval 必须遵守。

---

## 1. System Classification

**System Type:** RAG / structured extraction / continual knowledge curation hybrid

**Description:**
系统把个人历史证据蒸馏成带来源、身份、版本和生命周期的 atomic QA/claim units；在查询时优先检索经过验证的 canonical units，并可回查 raw evidence。好的结果必须比 raw-event baseline 更容易命中、更可信，同时不把 assistant 或 subagent 的话误认成用户事实。

**Critical Failure Modes:**

1. 无证据或证据不蕴含 answer 的 unit 被提升为 current。
2. secret、deleted、excluded、thinking/tool raw content 进入索引。
3. assistant/subagent 内容被归因为用户偏好、习惯或现实事实。
4. 相似但不同主体、时态或结论的 units 被错误合并。
5. 新 build 失败后覆盖上一个有效索引/checkpoint。

---

## 1b. Domain Context

**Industry Vertical:** 个人知识管理 / developer productivity / personal analytics

**User Population:** 单用户、本机优先；通过 CLI、REST、MCP 和未来 agent 使用。

**Stakes Level:** High（长期错误记忆会持续影响后续建议和决策）

**Output Consequence:** 检索结果会进入模型上下文，影响项目判断、个人偏好推断和自动化动作。

### What Domain Experts Evaluate Against

| Dimension | Good | Bad | Stakes |
|---|---|---|---|
| Evidence support | answer 可由引用证据直接支持 | 只有主题相关，没有事实支持 | Critical |
| Speaker provenance | user/assistant/subagent/tool 身份明确 | 把模型输出当用户观点 | Critical |
| Temporal validity | current/deprecated/conflict 明确 | 新旧结论混用 | High |
| Retrieval utility | 正确证据进入 top-k，噪声低 | 重复或一次性内容挤占 top-k | High |
| Abstention | 无可靠证据时拒绝建立/回答 | 为追求覆盖率强行生成 | Critical |

### Known Failure Modes in This Domain

- 同一项目反复讨论造成 near-duplicate vector crowding。
- 用户提出问题，assistant 给出假设答案，后续被错误沉淀成用户事实。
- 旧技术选择被新选择替代，但旧 unit 仍标 current。
- subagent 的局部调查结论脱离父任务上下文。
- secret-bearing session 经摘要后仍以改写形式泄漏。

### Regulatory / Compliance Context

无外部行业监管要求；受本机隐私、最小化收集、可删除和可追溯约束。禁止外发原始个人会话作为 tracing/eval telemetry。

### Domain Expert Roles for Evaluation

| Role | Responsibility |
|---|---|
| 数据所有者（用户） | 标注 frozen test、审查 wrong/stale/missing 与高风险 merge |
| 系统维护者 | 维护 schema、lineage、评测脚本和发布 gate |

---

## 2. Framework Decision

**Selected Framework:** Explicit local Python pipeline（无 RAG orchestration framework）

**Version:** Python 3.14；Pydantic 2.x；现有 SQLite/Chroma HTTP client

**Rationale:**
当前项目已经有明确的 SQLite、prompt、Chroma、CLI/REST/MCP 边界。Phase 14 是线性、强审计的数据生产管道，不需要 agent graph 或文档框架。保持显式 SQL 和小型函数，更容易验证 evidence、checkpoint 和删除传播。

**Alternatives Considered:**

| Framework | Ruled Out Because |
|---|---|
| LlamaIndex | 会替换现有 ingest/retrieval 契约，超出最小改动 |
| LangChain | 抽象层增加，但当前没有多 provider chain 需求 |
| LangGraph | 线性 pipeline 不需要图状态机 |
| OpenAI Agents SDK | 本阶段是批处理和检索，不是 agent handoff 系统 |

**Vendor Lock-In Accepted:** Partial。LLM 调用保持 OpenAI-compatible boundary；本阶段默认模型为 `gpt-5.6-luna`，但数据库和索引产物不依赖 provider SDK 对象。

---

## 3. Framework Quick Reference

### Installation

```powershell
python -m pip install "pydantic>=2,<3"
```

### Core Imports

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator
import sqlite3
```

### Entry Point Pattern

```python
def run(*, db_path, run_id, model, write=False):
    snapshot = load_versioned_evidence(db_path)
    raw = call_llm(snapshot, model=model)
    candidates = validate_candidates(raw, snapshot)
    report = evaluate_candidates(candidates)
    if write and report.passed:
        publish_staging(run_id, candidates)
    return report
```

### Key Abstractions

| Concept | What It Is | When You Use It |
|---|---|---|
| run manifest | 输入、prompt/model/schema/index 的版本合同 | 每次抽取、merge、index build |
| staging dataset | 未通过 gate 的 draft units | 所有 LLM 输出 |
| candidate collection | 尚未成为默认检索面的版本化索引 | 离线 A/B 与 canary |
| active checkpoint | 当前通过 gate 的 DB/index 组合 | 生产检索 |
| evidence eligibility | 来源、角色、隐私、删除状态的硬约束 | 抽取和检索前 |

### Common Pitfalls

1. `INSERT OR IGNORE` 不能代替版本管理。
2. 仅验证 JSON 可解析，不等于 schema/evidence 有效。
3. 用“canonical 行数必须减少”作为 gate 会奖励错误合并。

### Recommended Project Structure

```text
integration/
├── prompts/knowledge_unit_extractor/
├── prompts/knowledge_unit_merger/
├── evals/knowledge_units/
├── scripts/build_knowledge_units.py
├── scripts/build_canonical_knowledge_units.py
├── scripts/build_knowledge_unit_vector_store.py
└── scripts/evaluate_knowledge_unit_rag.py
```

---

## 4. Implementation Guidance

**Model Configuration:** `gpt-5.6-luna` via config/CLI；temperature 0；实际 model ID、reasoning effort、prompt version 和 response hash 写入 manifest。

**Core Pattern:** extract → strict validate → evidence gate → staging → canonical pair review → candidate index → frozen-test A/B → atomic promote。

**Tool Use:** 复用现有 SQLite、Chroma client、local bge embedding、pytest、CLI reports；不把原始个人文本发送到 tracing SaaS。

**State Management:** SQLite 是 lineage/版本事实源；Chroma 是可重建 retrieval surface；active pointer 只指向通过 gate 的 build ID。

**Context Window Strategy:** evidence bundle 按 subject/turn 聚合并有字符上限；超限先确定性裁剪，禁止把无关 session 全量塞入 prompt。

---

## 4b. AI Systems Best Practices

### Structured Outputs with Pydantic

```python
class KnowledgeUnitCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=4, max_length=500)
    answer: str = Field(min_length=4, max_length=2000)
    unit_type: str
    subject: str = Field(min_length=1, max_length=200)
    evidence_refs: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("evidence_refs")
    @classmethod
    def unique_refs(cls, refs: list[str]) -> list[str]:
        if len(refs) != len(set(refs)):
            raise ValueError("duplicate evidence refs")
        return refs
```

验证失败最多重试一次；仍失败则记录失败并计入 abort rate，不能构造 deterministic fake answer。

### Async-First Design

LLM 请求可有限并发；SQLite/manifest/index publish 使用单 writer。worker 只返回纯数据，主线程验证并提交。

### Prompt Engineering Discipline

- system prompt 只放角色和不可违反规则；evidence 放 user payload。
- prompt、schema、rubric 分文件版本化。
- extractor 必须输出 abstain/reject 状态，不能为了“至少一条”强行生成。

### Context Window Management

- 以 evidence bundle 为输入单元。
- 保留 source refs 和角色，不保留 thinking/tool raw content。
- 超限时按 eligibility、user-authored evidence、时间与相关度裁剪，并记录被裁剪 refs。

### Cost and Latency Budget

- dev/frozen eval 使用固定样本，避免每次全量调用。
- 输入 hash 命中时复用原始 LLM response cache。
- 每个 run 报告调用数、tokens、cost、p50/p95 latency；预算由配置注入，不硬编码价格。

---

## 5. Evaluation Strategy

### Dimensions

| Dimension | Rubric | Measurement Approach | Priority |
|---|---|---|---|
| schema validity | ≥95%；无效 evidence ref=0 | Code | Critical |
| evidence support | 人工抽查 ≥90% 可直接支持 | Human + calibrated judge | Critical |
| speaker attribution | 用户事实误归因=0 | Code + Human | Critical |
| merge precision | 20 个 hard negatives 错误合并=0 | Code + Human | Critical |
| retrieval | Recall@5/MRR@5 不低于 raw baseline | Code | High |
| grounded top-1 | frozen test ≥85% | Human + judge | High |
| stale/deprecated | deprecated 命中=0 | Code | Critical |
| reproducibility | 同输入 rerun diff=0 | Code | High |
| latency/cost | p95 不超过配置预算 | Code | Medium |

### Eval Tooling

**Primary Tool:** 项目内 pytest + SQLite/JSON evaluator。明确覆盖 Arize Phoenix 默认建议：因为这是单用户私密会话系统，Phase 14 不外发 trace。

**Setup:** 无新增 tracing 服务；Pydantic 为唯一新增显式验证依赖。

**CI/CD Integration:**

```powershell
python -m pytest -q tests\test_knowledge_unit_contracts.py tests\test_knowledge_unit_eval.py
python integration\scripts\evaluate_knowledge_unit_rag.py --dataset frozen-test
```

### Reference Dataset

**Size:** 20 dev + 20 frozen test；另含 20 merge-positive pairs + 20 hard-negative pairs。真实个人 query/evidence 数据集仅本地保存并由 hash 标识，不提交 Git；仓库只保留 schema 文档和 synthetic test cases。

**Composition:** user preference、project decision、capability、time conflict、deprecated、no-answer、assistant-only、subagent-only、secret-ineligible、跨 source 重复。

**Labeling:** 用户确认 gold evidence 和关键 high-stakes cases；LLM judge 必须先与人工样本校准，相关性不足 0.7 时只作辅助。

---

## 6. Guardrails

### Online (Real-Time)

| Guardrail | Trigger | Intervention |
|---|---|---|
| evidence eligibility | secret/deleted/excluded/ineligible | Block |
| personal fact provenance | 无 user-authored evidence | Block promotion / abstain |
| lifecycle | deprecated/conflict 命中 | Filter or flag conflict |
| checkpoint | candidate build 未通过 frozen test | Keep prior active index |
| citation | evidence ref 无法回查 | Block answer or fallback raw |

### Offline (Flywheel)

| Metric | Sampling Strategy | Action on Degradation |
|---|---|---|
| wrong/stale/missing | 所有显式负反馈 | 加入 dev/hard-negative backlog |
| fallback rate | 每周按高 fallback query 抽样 | 补 unit 或改 query/retrieval |
| false merge | 新 cluster + 冲突 subject 全抽 | 回滚 merge/checkpoint |
| evidence drift | 受更新 subject 全量检查 | 重建受影响 units |

---

## 7. Production Monitoring

**Tracing Tool:** 本地 `rag_runs/rag_retrieval_items/rag_feedback` SQLite tables + 脱敏 JSON report。

**Key Metrics to Track:** Recall@5、grounded top-1、fallback rate、deprecated hit、schema/evidence reject rate、p95 latency/cost。

**Alert Thresholds:** deprecated/secret hit >0 立即 abort；schema 有效率 <95% 或 grounded <85% 不 promote；canary critical wrong/stale >0 回滚。

**Smart Sampling Strategy:** 优先抽样 no-answer、低 margin、fallback、conflict、user negative feedback、subagent-only evidence 和新 source sessions。

---

## Checklist

- [x] System type classified
- [x] Critical failure modes identified
- [x] Domain context researched
- [x] Privacy/compliance context identified
- [x] Domain expert roles defined
- [x] Framework decision documented
- [x] Alternatives considered
- [x] Entry point and pitfalls documented
- [x] Pydantic structured output contract provided
- [x] Evaluation dimensions and thresholds defined
- [x] Local tracing override documented
- [x] Reference datasets specified
- [x] Online guardrails defined
- [x] Production monitoring specified
