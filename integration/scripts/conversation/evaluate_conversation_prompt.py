"""Wave 6 Task 2/4/5: Prompt Lab 压缩评测门。

PLAN 强制:prompt 没经过固定样本反复测试,不能把结果写进 SQLite 或向量库。
本脚本对 `conversation_prompt_eval_set.json` 的固定样本跑两轮 LLM:
  1. 压缩轮:用 v1_main.md prompt 把 turn 压缩成 context_brief。
  2. 评分轮(LLM-as-judge):按 eval_rubric.md 的 7 维度打分。

最终输出 prompt_eval_results.json/md,并判定 gate_passed。
未通过 gate 时退出码非 0(PLAN Wave 6 Acceptance Criteria)。

环境变量(沿用项目约定):
  OPENAI_API_KEY / MEM0_API_KEY  — 必填
  OPENAI_BASE_URL               — 兼容端点(如小米 MiMo)
  MEM0_LLM_MODEL                — 模型名(默认 gpt-4o-mini)
  EVAL_JUDGE_MODEL              — 评分模型(默认同 MEM0_LLM_MODEL)

用法:
  python evaluate_conversation_prompt.py --dry-run --limit 3   # 验证结构 + 评分阈值逻辑
  python evaluate_conversation_prompt.py --write --limit 7     # 跑全量评测
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROMPT_DIR = ROOT / "integration" / "prompts" / "conversation_compression"
EVAL_SET = ROOT / "integration" / "analysis" / "ai_context" / "conversation_prompt_eval_set.json"
OUT_JSON = ROOT / "integration" / "analysis" / "ai_context" / "prompt_eval_results.json"
OUT_MD = ROOT / "integration" / "analysis" / "ai_context" / "prompt_eval_results.md"

PROMPT_VERSION = "v1"

# ---- gate 阈值(eval_rubric.md)----
GATE_AVG_SCORE = 4.0          # 单样本平均分门槛
GATE_FAITHFULNESS = 4         # 忠实度硬门槛
GATE_PASS_RATE = 0.85         # 全样本通过率
GATE_REFS_COVERAGE = 0.9      # source_refs 匹配覆盖率


@dataclass
class SampleResult:
    sample_id: str
    category: str
    label: str
    focus_notes: str
    turn_text_len: int
    # 压缩产物
    compressed: dict | None = None
    # 评分(7 维 + 专项)
    scores: dict = field(default_factory=dict)
    oneoff_as_preference: bool = False
    # 单样本 gate
    sample_gate_passed: bool = False
    fail_reasons: list[str] = field(default_factory=list)


@dataclass
class EvalReport:
    prompt_version: str
    model: str
    judge_model: str
    sample_count: int
    results: list[SampleResult]
    # 整体 gate
    gate_passed: bool = False
    avg_faithfulness: float = 0.0
    refs_coverage: float = 0.0
    pass_rate: float = 0.0
    overall_avg_score: float = 0.0
    known_failures: list[str] = field(default_factory=list)


# ============ prompt 加载 ============

def load_prompt_main() -> str:
    """从 v1_main.md 提取 system prompt 块(```...``` 内的内容)。"""
    md = (PROMPT_DIR / "v1_main.md").read_text(encoding="utf-8")
    # 提取 "## System Prompt" 下的第一个代码块
    m = re.search(r"## System Prompt.*?```\n(.*?)```", md, re.DOTALL)
    if not m:
        sys.exit(f"[error] v1_main.md 未找到 System Prompt 代码块")
    return m.group(1).strip()


def load_schema_inline() -> str:
    """从 v1_schema.md 提取 schema 代码块,内联进 user prompt。

    MiMo 等模型只看 system+user,看不到独立的 schema 文件。必须把 schema
    明确贴进 user prompt,否则模型只输出 context_brief + source_refs,
    缺 main_topic/key_details/preference_vs_oneoff 等关键字段。
    """
    md = (PROMPT_DIR / "v1_schema.md").read_text(encoding="utf-8")
    m = re.search(r"## JSON Schema.*?```json\n(.*?)```", md, re.DOTALL)
    if not m:
        sys.exit("[error] v1_schema.md 未找到 JSON Schema 代码块")
    schema = m.group(1).strip()
    # 删掉 example 值,只留结构和字段说明,避免模型照抄示例
    schema = re.sub(r'"turn_no":\s*\d+', '"turn_no": <整数>', schema)
    schema = re.sub(r'"main_topic":\s*"[^"]*"', '"main_topic": "<≤20字中文话题>"', schema)
    schema = re.sub(r'"context_brief":\s*"[^"]*"', '"context_brief": "<200-1200字中文叙述,见 system prompt 压缩率目标>"', schema)
    schema = re.sub(r'"key_details":\s*\[.*?\]', '"key_details": ["<逐字保留的细节1>", "<细节2>"]', schema, flags=re.DOTALL)
    schema = re.sub(r'"branches":\s*\[.*?\]', '"branches": ["<分支1>", "<分支2>或空数组"]', schema, flags=re.DOTALL)
    schema = re.sub(r'"conclusion":\s*"[^"]*"', '"conclusion": "<助手结论+不确定边界>"', schema)
    schema = re.sub(r'"preference_vs_oneoff":\s*"[^"]*"', '"preference_vs_oneoff": "<格式:稳定偏好:...;一次性指令:...;都没有写无>"', schema)
    schema = re.sub(r'"source_refs":\s*\[[^\]]*\]', '"source_refs": <直接回填下面的 source_refs,不要编造>', schema)
    return schema


def build_user_prompt(focus_notes: str, turn_text: str, source_refs: list[str]) -> str:
    """构造压缩轮的 user prompt(模板见 v1_main.md + schema 内联)。"""
    md = (PROMPT_DIR / "v1_main.md").read_text(encoding="utf-8")
    # 提取 user prompt 模板
    m = re.search(r"## User Prompt 模板.*?```\n(.*?)```", md, re.DOTALL)
    if not m:
        sys.exit("[error] v1_main.md 未找到 User Prompt 模板")
    tpl = m.group(1)
    schema_inline = load_schema_inline()
    prompt = (tpl.replace("{{focus_notes}}", focus_notes or "(无)")
                .replace("{{turn_text}}", turn_text)
                .replace("{{source_refs}}", ", ".join(source_refs)))
    # 把 schema 内联到输出要求那段(替换"严格按 schema 输出 JSON")
    prompt = prompt.replace(
        "严格按 schema 输出 JSON。",
        f"严格按下面的 schema 输出 JSON(7 个顶层字段全都要有,缺一不可):\n\n```json\n{schema_inline}\n```")
    return prompt


# ============ LLM client ============

def make_llm_client():
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("[error] 未安装 openai 库,请运行: pip install openai")
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("MEM0_API_KEY")
    if not api_key:
        sys.exit("[error] 未设置 OPENAI_API_KEY / MEM0_API_KEY")
    return OpenAI()


def extract_json(raw: str) -> dict | None:
    """从 LLM 输出提取 JSON,容错 markdown 包裹和前后噪声(v1_schema.md 解析容错)。"""
    if not raw:
        return None
    # 去代码块包裹
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)
    # 提取第一个 { 到最后一个 }
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    chunk = raw[start:end + 1]
    try:
        return json.loads(chunk)
    except json.JSONDecodeError:
        return None


MAX_TURN_CHARS = 6000   # 单 turn 喂给 LLM 的字符上限(与 build_conversation_summary 一致)
CALL_TIMEOUT = 120      # 单次 LLM 调用超时秒(MiMo 推理模型长输入易卡)


def _truncate_turn_text(turn_text: str, focus_notes: str) -> tuple[str, bool]:
    """超长 turn 截断到 MAX_TURN_CHARS,保留开头(用户诉求)和结尾(结论)。

    MiMo 推理模型对 >6k 字符输入容易超时。截断策略:留前 70% + 后 25%,
    中间用省略标注。返回 (处理后文本, 是否截断)。
    """
    if len(turn_text) <= MAX_TURN_CHARS:
        return turn_text, False
    head = int(MAX_TURN_CHARS * 0.7)
    tail = int(MAX_TURN_CHARS * 0.25)
    truncated = (turn_text[:head]
                 + f"\n\n[...中间内容已截断,原文 {len(turn_text)} 字符,评测用截断版...]\n\n"
                 + turn_text[-tail:])
    return truncated, True


def compress_turn(client, model: str, system_prompt: str, user_prompt: str) -> dict | None:
    """压缩轮:调 LLM 把 turn 压成 context_brief(JSON)。单次超时返回 None。"""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            timeout=CALL_TIMEOUT,
        )
    except Exception as exc:
        print(f"[warn] 压缩调用超时/失败: {type(exc).__name__}: {str(exc)[:80]}",
              file=sys.stderr)
        return None
    raw = resp.choices[0].message.content
    return extract_json(raw)


# ============ LLM-as-judge 评分 ============

JUDGE_SYSTEM = """你是严格的对话压缩质量评审。给你一段原始 turn 文本和 LLM 的压缩输出,按 7 个维度打分(每维 1-5 整数)。

7 个维度:
1. trunk_preservation:主干(用户诉求+助手推进路径)是否完整。
2. branch_preservation:分支(子问题/报错/替代方案)是否保留。原 turn 无分支时给 5。
3. detail_retention:路径/命令/错误栈/函数名/阈值等细节是否逐字保留,无改写。
4. compression_ratio:压缩率是否合适(不过短不过长)。
5. retrieval_usefulness:看到摘要能否判断 turn 与查询相关。
6. faithfulness:是否引入原文没有的结论/推断/常识补充。完全忠于原文给 5。
7. context_brief_quality:context_brief 是否连贯叙述可直接注入后续 AI。

专项检查 oneoff_as_preference:
- 检查 compressed 的 preference_vs_oneoff 字段是否把"一次性操作指令"误判为"稳定偏好"。
- 例:原 turn 是"帮我重构PPT",但输出判成"用户喜欢重构PPT" -> oneoff_as_preference=true。
- 正确区分 -> false。

严格输出 JSON(不要 markdown 包裹):
{
  "scores": {"trunk_preservation":5, "branch_preservation":4, "detail_retention":4, "compression_ratio":5, "retrieval_usefulness":4, "faithfulness":5, "context_brief_quality":4},
  "oneoff_as_preference": false,
  "judge_note": "一句话评语"
}"""


def judge_sample(client, judge_model: str, turn_text: str, compressed: dict) -> dict:
    """评分轮:LLM-as-judge 打分。失败返回默认低分。"""
    user = (f"【原始 turn 文本】\n{turn_text}\n\n"
            f"【LLM 压缩输出】\n{json.dumps(compressed, ensure_ascii=False, indent=2)}\n\n"
            f"严格按 schema 输出 JSON 评分。")
    try:
        resp = client.chat.completions.create(
            model=judge_model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user},
            ],
            temperature=0.0,
        )
        out = extract_json(resp.choices[0].message.content)
        if out and "scores" in out:
            return out
    except Exception as exc:
        print(f"[warn] judge 失败: {type(exc).__name__}: {str(exc)[:80]}", file=sys.stderr)
    return {"scores": {}, "oneoff_as_preference": False, "judge_note": "(judge 失败)"}


# ============ 自动可判维度 ============

SCORE_DIMS = ["trunk_preservation", "branch_preservation", "detail_retention",
              "compression_ratio", "retrieval_usefulness", "faithfulness",
              "context_brief_quality"]


def auto_compression_ratio(turn_len: int, brief_len: int) -> float:
    """返回 ratio,用于交叉验证 judge 的 compression_ratio 打分。"""
    return brief_len / turn_len if turn_len else 0.0


def auto_source_refs_match(expected: list[str], actual: list[str]) -> int:
    """检查 expected 里有多少条被 actual 匹配(子串即可,路径分隔符差异容忍)。

    返回的是 expected 中被命中的条数(0..len(expected)),不是 actual 的累加,
    避免同 session 多行 ref 因路径前缀相同导致子串匹配膨胀(曾出现 220/2)。
    """
    if not expected:
        return 0
    norm_actual = [a.replace("\\", "/") for a in (actual or [])]
    matched = 0
    for e in expected:
        ne = e.replace("\\", "/")
        if any(ne == na or ne in na or na in ne for na in norm_actual):
            matched += 1
    return matched


# ============ gate 判定 ============

def _pure_scores(scores: dict) -> dict:
    """剥离 _ 开头的内部字段(_refs_matched/_auto_ratio),只留 7 维评分。"""
    return {k: v for k, v in scores.items() if not k.startswith("_")}


def judge_sample_gate(scores: dict, faithfulness: int,
                      oneoff_as_preference: bool, refs_matched: int) -> tuple[bool, list[str]]:
    """单样本 gate(eval_rubric.md)。"""
    reasons: list[str] = []
    pure = _pure_scores(scores)
    avg = sum(pure.values()) / len(pure) if pure else 0.0
    if avg < GATE_AVG_SCORE:
        reasons.append(f"avg_score={avg:.2f}<{GATE_AVG_SCORE}")
    if faithfulness < GATE_FAITHFULNESS:
        reasons.append(f"faithfulness={faithfulness}<{GATE_FAITHFULNESS}")
    if oneoff_as_preference:
        reasons.append("oneoff_as_preference=true (一次性任务被误判为偏好)")
    if refs_matched < 1:
        reasons.append("source_refs 与输入不匹配")
    return (len(reasons) == 0), reasons


def judge_overall_gate(results: list[SampleResult]) -> tuple[bool, dict]:
    """整体 gate(eval_rubric.md)。"""
    n = len(results)
    if n == 0:
        return False, {"pass_rate": 0, "avg_faithfulness": 0, "refs_coverage": 0,
                       "overall_avg_score": 0}
    pass_count = sum(1 for r in results if r.sample_gate_passed)
    faith_vals = [r.scores.get("faithfulness", 0) for r in results if r.scores]
    # 用每个 result 自己算过的 refs 匹配状态
    all_avgs = []
    for r in results:
        pure = _pure_scores(r.scores)
        if pure:
            all_avgs.append(sum(pure.values()) / len(pure))
    metrics = {
        "pass_rate": pass_count / n,
        "avg_faithfulness": sum(faith_vals) / len(faith_vals) if faith_vals else 0,
        "refs_coverage": _compute_refs_coverage(results),
        "overall_avg_score": sum(all_avgs) / len(all_avgs) if all_avgs else 0,
    }
    passed = (metrics["pass_rate"] >= GATE_PASS_RATE
              and metrics["avg_faithfulness"] >= GATE_FAITHFULNESS
              and metrics["refs_coverage"] >= GATE_REFS_COVERAGE)
    return passed, metrics


def _has_matching_refs(r: SampleResult) -> bool:
    """result 里是否已经标记 refs 匹配(在 run 里设置)。"""
    return r.scores.get("_refs_matched", 0) >= 1


def _compute_refs_coverage(results: list[SampleResult]) -> float:
    n = len(results)
    if n == 0:
        return 0.0
    hit = sum(1 for r in results if r.scores.get("_refs_matched", 0) >= 1)
    return hit / n


# ============ 主流程 ============

def run(write: bool, limit: int) -> int:
    if not EVAL_SET.exists():
        print(f"[error] 缺少评测样本集: {EVAL_SET.relative_to(ROOT)}")
        print("        先运行: python integration/scripts/build_conversation_eval_set.py --write")
        return 1

    samples = json.loads(EVAL_SET.read_text(encoding="utf-8"))
    if limit:
        samples = samples[:limit]
    if not samples:
        print("[error] 评测样本集为空")
        return 1

    system_prompt = load_prompt_main()
    model = os.environ.get("MEM0_LLM_MODEL", "gpt-4o-mini")
    judge_model = os.environ.get("EVAL_JUDGE_MODEL", model)

    print(f"Prompt Lab 评测 (version={PROMPT_VERSION})")
    print(f"  样本数: {len(samples)} | 压缩模型: {model} | 评分模型: {judge_model}")
    print(f"  Gate 阈值: 单样本 avg>={GATE_AVG_SCORE} & faithfulness>={GATE_FAITHFULNESS} "
          f"| 整体 pass_rate>={GATE_PASS_RATE} & faithfulness>={GATE_FAITHFULNESS} "
          f"& refs_coverage>={GATE_REFS_COVERAGE}")
    print("-" * 70)

    if not write:
        return run_dry(samples, system_prompt, model, judge_model)

    return run_write(samples, system_prompt, model, judge_model)


def run_dry(samples: list[dict], system_prompt: str, model: str, judge_model: str) -> int:
    """dry-run:不调 LLM,验证脚本结构 + 评分阈值逻辑(PLAN Wave 6-4)。"""
    print("[dry] 验证脚本结构 + 评分阈值逻辑(不调 LLM)")
    print()
    # 1. 验证 prompt 加载
    print(f"  [✓] system_prompt 加载成功 ({len(system_prompt)} 字符)")
    # 2. 构造 user prompt 样例
    s0 = samples[0]
    up = build_user_prompt(s0["focus_notes"], s0["turn_text"], s0["source_refs"])
    print(f"  [✓] user_prompt 构造成功 (样本 {s0['category']}, {len(up)} 字符)")
    print()
    # 3. 验证评分阈值逻辑:用 3 组人造分数测试 gate
    print("  --- gate 判定逻辑测试 ---")
    test_cases = [
        ("全 5 分 + refs 匹配", {"trunk_preservation":5,"branch_preservation":5,
            "detail_retention":5,"compression_ratio":5,"retrieval_usefulness":5,
            "faithfulness":5,"context_brief_quality":5}, 5, False, 2, True),
        ("faithfulness=3 失败", {"trunk_preservation":5,"branch_preservation":5,
            "detail_retention":5,"compression_ratio":5,"retrieval_usefulness":5,
            "faithfulness":3,"context_brief_quality":5}, 3, False, 2, False),
        ("oneoff 误判失败", {"trunk_preservation":5,"branch_preservation":5,
            "detail_retention":5,"compression_ratio":5,"retrieval_usefulness":5,
            "faithfulness":5,"context_brief_quality":5}, 5, True, 2, False),
        ("refs 不匹配失败", {"trunk_preservation":5,"branch_preservation":5,
            "detail_retention":5,"compression_ratio":5,"retrieval_usefulness":5,
            "faithfulness":5,"context_brief_quality":5}, 5, False, 0, False),
        ("低均分失败", {"trunk_preservation":3,"branch_preservation":3,
            "detail_retention":3,"compression_ratio":3,"retrieval_usefulness":3,
            "faithfulness":4,"context_brief_quality":3}, 4, False, 2, False),
    ]
    all_ok = True
    for name, scores, faith, oneoff, refs, expect in test_cases:
        passed, reasons = judge_sample_gate(scores, faith, oneoff, refs)
        ok = passed == expect
        all_ok = all_ok and ok
        mark = "✓" if ok else "✗"
        print(f"  {mark} {name}: gate={passed} (期望 {expect}) "
              f"{('' if passed else '原因='+','.join(reasons))}")
    print()
    # 4. 整体 gate 测试
    print("  --- 整体 gate 逻辑测试 ---")
    fake_results = []
    for i in range(7):
        scores = {"trunk_preservation":5,"branch_preservation":5,"detail_retention":5,
                  "compression_ratio":5,"retrieval_usefulness":5,"faithfulness":5,
                  "context_brief_quality":5,"_refs_matched":2}
        # 第 6 个样本故意失败(faithfulness=2)
        if i == 5:
            scores["faithfulness"] = 2
        fake_r = SampleResult(
            sample_id=f"fake:{i}", category="test", label="test", focus_notes="",
            turn_text_len=1000, compressed={"source_refs":[]}, scores=scores,
            oneoff_as_preference=False,
        )
        fake_r.sample_gate_passed, fake_r.fail_reasons = judge_sample_gate(
            {k:v for k,v in scores.items() if k != "_refs_matched"},
            scores["faithfulness"], False, scores["_refs_matched"])
        fake_results.append(fake_r)
    overall, metrics = judge_overall_gate(fake_results)
    print(f"  [人造样本集] pass_rate={metrics['pass_rate']:.2f} "
          f"avg_faith={metrics['avg_faithfulness']:.2f} "
          f"refs_cov={metrics['refs_coverage']:.2f} -> gate={overall}")
    # 6/7 通过 = 0.857 >= 0.85,但 avg_faith = 32/7 = 4.57 >= 4 -> 应通过
    expect_overall = True
    mark = "✓" if overall == expect_overall else "✗"
    print(f"  {mark} 整体 gate 判定 {'正确' if overall == expect_overall else '错误'}")
    all_ok = all_ok and (overall == expect_overall)

    print()
    if all_ok:
        print("[dry] 脚本结构和评分阈值逻辑验证通过 ✓")
        print("      加 --write 配合 OPENAI_API_KEY/OPENAI_BASE_URL/MEM0_LLM_MODEL 跑真实评测。")
        return 0
    print("[dry] ✗ 评分阈值逻辑有误,需修正", file=sys.stderr)
    return 1


def run_write(samples: list[dict], system_prompt: str, model: str,
              judge_model: str) -> int:
    """write:调 LLM 跑真实评测。"""
    client = make_llm_client()
    results: list[SampleResult] = []

    for idx, s in enumerate(samples, 1):
        sr = SampleResult(
            sample_id=s["sample_id"], category=s["category"], label=s["label"],
            focus_notes=s["focus_notes"], turn_text_len=s["turn_text_len"],
        )
        print(f"[{idx}/{len(samples)}] {s['category']:14s} 压缩中...", end=" ", flush=True)
        # 1. 压缩轮(超长 turn 先截断,避免 MiMo 推理模型超时)
        turn_text, was_truncated = _truncate_turn_text(s["turn_text"], s["focus_notes"])
        if was_truncated:
            print(f"(截断 {s['turn_text_len']}→{len(turn_text)}字) ", end="", flush=True)
        user_prompt = build_user_prompt(s["focus_notes"], turn_text, s["source_refs"])
        compressed = compress_turn(client, model, system_prompt, user_prompt)
        if not compressed or "context_brief" not in compressed:
            sr.fail_reasons.append("压缩轮无 context_brief 输出")
            sr.scores = {d: 1 for d in SCORE_DIMS}
            sr.sample_gate_passed = False
            results.append(sr)
            print("✗ 压缩失败")
            continue
        sr.compressed = compressed

        # 2. refs 匹配检查(自动)
        refs_matched = auto_source_refs_match(
            s["source_refs"], compressed.get("source_refs", []))
        # 3. ratio 自动计算(交叉验证)
        ratio = auto_compression_ratio(
            s["turn_text_len"], len(compressed.get("context_brief", "")))

        # 4. judge 评分
        judged = judge_sample(client, judge_model, s["turn_text"], compressed)
        scores = judged.get("scores", {})
        # 补全缺失维度为 1(扣分)
        scores = {d: int(scores.get(d, 1)) for d in SCORE_DIMS}
        scores["_refs_matched"] = refs_matched
        scores["_auto_ratio"] = round(ratio, 3)
        sr.scores = scores
        sr.oneoff_as_preference = bool(judged.get("oneoff_as_preference", False))

        # 5. 单样本 gate
        sr.sample_gate_passed, sr.fail_reasons = judge_sample_gate(
            {k: v for k, v in scores.items() if not k.startswith("_")},
            scores["faithfulness"], sr.oneoff_as_preference, refs_matched)
        results.append(sr)
        brief_len = len(compressed.get("context_brief", ""))
        avg = sum(v for k, v in scores.items() if not k.startswith("_")) / 7
        print(f"gate={'通过' if sr.sample_gate_passed else '✗'} "
              f"avg={avg:.1f} faith={scores['faithfulness']} "
              f"ratio={ratio:.2f} refs={refs_matched}/{len(s['source_refs'])}")

    # 整体 gate
    gate, metrics = judge_overall_gate(results)
    report = EvalReport(
        prompt_version=PROMPT_VERSION, model=model, judge_model=judge_model,
        sample_count=len(results), results=results, gate_passed=gate,
        avg_faithfulness=metrics["avg_faithfulness"],
        refs_coverage=metrics["refs_coverage"],
        pass_rate=metrics["pass_rate"],
        overall_avg_score=metrics["overall_avg_score"],
    )
    # 收集 known_failures
    for r in results:
        if not r.sample_gate_passed:
            report.known_failures.append(f"{r.sample_id}: {', '.join(r.fail_reasons)}")

    write_outputs(report)
    print()
    print("=" * 70)
    print(f"整体 gate: {'✓ 通过' if gate else '✗ 未通过'}")
    print(f"  pass_rate={metrics['pass_rate']:.2f} (阈值 {GATE_PASS_RATE})")
    print(f"  avg_faithfulness={metrics['avg_faithfulness']:.2f} (阈值 {GATE_FAITHFULNESS})")
    print(f"  refs_coverage={metrics['refs_coverage']:.2f} (阈值 {GATE_REFS_COVERAGE})")
    print(f"  overall_avg_score={metrics['overall_avg_score']:.2f}")
    if report.known_failures:
        print(f"  失败样本 {len(report.known_failures)} 个:")
        for f in report.known_failures:
            print(f"    - {f}")
    print("=" * 70)
    return 0 if gate else 1


def write_outputs(report: EvalReport) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSON.open("w", encoding="utf-8") as fh:
        json.dump(asdict(report), fh, ensure_ascii=False, indent=2)

    lines = ["# Prompt Lab 评测报告", "",
             f"- prompt_version: `{report.prompt_version}`",
             f"- 压缩模型: `{report.model}` | 评分模型: `{report.judge_model}`",
             f"- 样本数: {report.sample_count}",
             f"- **整体 gate: {'✓ 通过' if report.gate_passed else '✗ 未通过'}**",
             f"  - pass_rate={report.pass_rate:.2f} (阈值 {GATE_PASS_RATE})",
             f"  - avg_faithfulness={report.avg_faithfulness:.2f} (阈值 {GATE_FAITHFULNESS})",
             f"  - refs_coverage={report.refs_coverage:.2f} (阈值 {GATE_REFS_COVERAGE})",
             f"  - overall_avg_score={report.overall_avg_score:.2f}", ""]
    lines.append("## 单样本结果")
    lines.append("")
    lines.append("| 样本 | 平均分 | faith | ratio | refs | gate | 失败原因 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for r in report.results:
        sc = r.scores
        avg = (sum(v for k, v in sc.items() if not k.startswith("_")) / 7) if sc else 0
        faith = sc.get("faithfulness", "-") if sc else "-"
        ratio = sc.get("_auto_ratio", "-") if sc else "-"
        refs = sc.get("_refs_matched", "-") if sc else "-"
        gate_mark = "✓" if r.sample_gate_passed else "✗"
        reason = ", ".join(r.fail_reasons) if r.fail_reasons else ""
        lines.append(f"| {r.category} | {avg:.1f} | {faith} | {ratio} | {refs} | "
                     f"{gate_mark} | {reason} |")
    lines.append("")
    if report.known_failures:
        lines.append("## 失败样本详情")
        lines.append("")
        for f in report.known_failures:
            lines.append(f"- {f}")
        lines.append("")
    lines.append("## 压缩产物样例")
    lines.append("")
    for r in report.results[:3]:
        if r.compressed:
            lines.append(f"### {r.category} ({r.label})")
            lines.append(f"**main_topic:** {r.compressed.get('main_topic','')}")
            lines.append("")
            lines.append(f"**context_brief:**")
            lines.append(r.compressed.get("context_brief", ""))
            lines.append("")
            lines.append(f"**preference_vs_oneoff:** "
                         f"{r.compressed.get('preference_vs_oneoff','')}")
            lines.append("")
            if r.compressed.get("key_details"):
                lines.append(f"**key_details:**")
                for d in r.compressed["key_details"]:
                    lines.append(f"- {d}")
                lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n已写入:")
    print(f"  {OUT_JSON.relative_to(ROOT)}")
    print(f"  {OUT_MD.relative_to(ROOT)}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Prompt Lab 压缩评测门 (Wave 6 Task 2/4/5)")
    p.add_argument("--dry-run", action="store_true",
                   help="不调 LLM,验证脚本结构 + 评分阈值逻辑")
    p.add_argument("--write", action="store_true", help="调 LLM 跑真实评测并落盘")
    p.add_argument("--limit", type=int, default=0,
                   help="只评测前 N 个样本(0=全部)")
    args = p.parse_args(argv)
    if args.dry_run and args.write:
        print("[error] --dry-run 与 --write 互斥", file=sys.stderr)
        return 2
    if not args.dry_run and not args.write:
        print("[error] 必须指定 --dry-run 或 --write", file=sys.stderr)
        return 2
    return run(args.write, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
