r"""Wave 2: compare first-gen memory items with second-gen graph judgments.

目标:
1. 抽样旧 memory_items(至少 20 条，带 memory_links / unified_events 证据摘要)。
2. 读取全部 accepted graph_relation_judgments，以及 review queue 样本。
3. 用版本化 prompt + schema 做 comparison judgment；脚本只做证据装配、调用、校验和报告。
4. 没有 LLM key 或调用失败时，走 deterministic fallback，但必须显式标明 llm_status。

用法:
  python -m personal_knowledge.evaluation.memory.compare_memory_experiments --dry-run --limit 5
  python -m personal_knowledge.evaluation.memory.compare_memory_experiments --write
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from personal_knowledge.core import llm as llm_mod
ROOT = Path(__file__).resolve().parents[4]
PROMPT_DIR = ROOT / "assets" / "prompts" / "memory_experiment_judge"
SQLITE_DB = ROOT / "integration" / "db" / "personal_system.sqlite"
OUT_JSON = ROOT / "integration" / "analysis" / "ai_context" / "memory_experiment_comparison.json"
OUT_MD = ROOT / "integration" / "analysis" / "ai_context" / "memory_experiment_comparison.md"

PROMPT_VERSION = "v1"
SCHEMA_VERSION = "v1"
DEFAULT_MODEL = "gpt-5.4"
DEFAULT_TEMPERATURE = 0.1
DEFAULT_OLD_SAMPLE_SIZE = 20
DEFAULT_REVIEW_SAMPLE_SIZE = 10
DEFAULT_MAX_EVENT_LINKS = 5
DEFAULT_CONTEXT_LIMIT = 3
PREVIEW_CHARS = 1800

RECORD_KINDS = {"old_memory_sample", "accepted_graph_edge", "review_queue_sample"}
OLD_MEMORY_ACTIONS = {"keep", "merge_candidate", "downgrade", "delete_candidate", "review_only", "analysis_only"}
GRAPH_ACTIONS = {"promote_candidate", "merge_candidate", "analysis_only", "review_only", "keep"}

DIMENSION_KEYS = [
    "evidence_coverage",
    "source_traceability",
    "relation_depth",
    "noise_risk",
    "long_term_usefulness",
    "retrieval_usefulness",
    "duplicate_overlap",
    "conflict_risk",
]

STOP_WORDS = {
    "用户", "助手", "需要", "这个", "那个", "以及", "然后", "继续", "进行", "已经", "当前",
    "任务", "问题", "项目", "代码", "脚本", "文件", "memory", "graph", "candidate", "session",
    "turn", "json", "python", "agent", "codex", "tool", "source", "target",
}


@dataclass
class LLMRuntime:
    status: str
    client: Any | None
    error: str = ""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_prompt_block(path: Path, heading: str) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"## {re.escape(heading)}.*?```\n(.*?)```", text, re.DOTALL)
    if not match:
        raise ValueError(f"{path.name} 未找到 {heading} 代码块")
    return match.group(1).strip()


def load_schema_inline() -> str:
    text = (PROMPT_DIR / "v1_schema.md").read_text(encoding="utf-8")
    match = re.search(r"## JSON Schema.*?```json\n(.*?)```", text, re.DOTALL)
    if not match:
        raise ValueError("v1_schema.md 未找到 JSON Schema 代码块")
    return match.group(1).strip()


def load_prompts() -> tuple[str, str]:
    main = PROMPT_DIR / "v1_main.md"
    system_prompt = load_prompt_block(main, "System Prompt")
    user_template = load_prompt_block(main, "User Prompt 模板")
    schema_inline = load_schema_inline()
    user_template = user_template.replace(
        "请按 `memory_experiment_judge/v1_schema.md` 的 schema 输出 1 条 JSON 记录。",
        "请按下面的 schema 输出 1 条 JSON 记录:\n\n```json\n" + schema_inline + "\n```",
    )
    return system_prompt, user_template


def extract_json(raw: str) -> dict | None:
    if not raw:
        return None
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return None


def make_llm_runtime() -> LLMRuntime:
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("MEM0_API_KEY")
    if not api_key:
        return LLMRuntime(status="fallback:no_api_key", client=None, error="missing OPENAI_API_KEY/MEM0_API_KEY")
    try:
        client = llm_mod.make_llm_client()
        return LLMRuntime(status="live", client=client)
    except SystemExit as exc:
        message = str(exc).replace("[error] ", "").strip()
        return LLMRuntime(status="fallback:client_init_failed", client=None, error=message)
    except Exception as exc:  # pragma: no cover - environment-specific
        return LLMRuntime(status="fallback:client_init_failed", client=None, error=f"{type(exc).__name__}: {exc}")


def tokenize_text(text: str) -> set[str]:
    lowered = (text or "").lower()
    tokens: set[str] = set()
    for token in re.findall(r"[a-z0-9_./:-]{2,}", lowered):
        if token not in STOP_WORDS:
            tokens.add(token)
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", lowered):
        if chunk not in STOP_WORDS:
            tokens.add(chunk)
        for idx in range(len(chunk) - 1):
            piece = chunk[idx: idx + 2]
            if piece not in STOP_WORDS:
                tokens.add(piece)
    return tokens


def overlap_score(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    inter = len(left & right)
    if inter == 0:
        return 0.0
    return inter / max(min(len(left), len(right)), 1)


def safe_text(value: Any, limit: int = 220) -> str:
    text = str(value or "").strip().replace("\r", " ").replace("\n", " ")
    return text[: limit - 1] + "…" if len(text) > limit else text


def parse_json_field(raw: Any, default: Any) -> Any:
    if raw in (None, ""):
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    con = sqlite3.connect(SQLITE_DB)
    con.row_factory = sqlite3.Row
    try:
        return list(con.execute(query, params).fetchall())
    finally:
        con.close()


def build_turn_lookup() -> dict[str, dict]:
    rows = fetch_all(
        """
        SELECT session_id, turn_no, turn_id, narrative, tools_used, source_ref, main_topic
        FROM conversation_turns_summary
        ORDER BY session_id, turn_no
        """
    )
    lookup: dict[str, dict] = {}
    for row in rows:
        session_id = row["session_id"]
        turn_no = int(row["turn_no"])
        turn_id = str(row["turn_id"] or "")
        record = {
            "session_id": session_id,
            "turn_no": turn_no,
            "turn_id": turn_id,
            "node_id": f"{session_id}#{turn_id or turn_no}",
            "narrative": row["narrative"] or "",
            "tools_used": row["tools_used"] or "",
            "source_ref": row["source_ref"] or "",
            "main_topic": row["main_topic"] or "",
        }
        keys = {
            f"{session_id}#{turn_id}" if turn_id else "",
            f"{session_id}#{turn_no}",
            f"{session_id}#t{turn_no}",
            f"{session_id}#t{turn_no:03d}",
        }
        for key in keys:
            if key:
                lookup[key] = record
    return lookup


def choose_old_memory_sample(rows: list[dict], sample_size: int) -> list[dict]:
    by_type: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_type[row["memory_type"]].append(row)
    ordered_types = sorted(by_type)
    chosen: list[dict] = []
    index = 0
    while len(chosen) < sample_size:
        picked = False
        for memory_type in ordered_types:
            group = by_type[memory_type]
            if index < len(group):
                chosen.append(group[index])
                picked = True
                if len(chosen) >= sample_size:
                    break
        if not picked:
            break
        index += 1
    return chosen[:sample_size]


def load_old_memories(sample_size: int, max_event_links: int) -> list[dict]:
    rows = fetch_all(
        """
        SELECT memory_id, memory_type, memory_subtype, subject, description, confidence,
               evidence_count, metadata, created_at
        FROM memory_items
        ORDER BY memory_type, evidence_count DESC, confidence DESC, memory_id
        """
    )
    picked = choose_old_memory_sample([dict(r) for r in rows], sample_size)
    con = sqlite3.connect(SQLITE_DB)
    con.row_factory = sqlite3.Row
    try:
        out = []
        for row in picked:
            links = list(
                con.execute(
                    """
                    SELECT l.target_id, l.relation, u.source, u.source_table, u.source_id, u.event_type,
                           u.service, u.event_time, u.title, u.content, u.category, u.session_id
                    FROM memory_links l
                    LEFT JOIN unified_events u ON u.event_id = l.target_id
                    WHERE l.memory_id = ?
                    ORDER BY COALESCE(u.event_time, '') DESC, l.id ASC
                    LIMIT ?
                    """,
                    (row["memory_id"], max_event_links),
                ).fetchall()
            )
            metadata = parse_json_field(row.get("metadata"), {})
            event_summaries = []
            evidence_refs = []
            text_parts = [row["subject"], row["description"], row["memory_type"], row["memory_subtype"]]
            for link in links:
                ref = f"unified_events:{link['target_id']}"
                evidence_refs.append(ref)
                summary = {
                    "event_id": link["target_id"],
                    "evidence_ref": ref,
                    "relation": link["relation"],
                    "source": link["source"] or "",
                    "source_id": link["source_id"] or "",
                    "service": link["service"] or "",
                    "event_type": link["event_type"] or "",
                    "event_time": link["event_time"] or "",
                    "title": safe_text(link["title"], 120),
                    "content_snippet": safe_text(link["content"], 180),
                }
                event_summaries.append(summary)
                text_parts.extend(
                    [summary["source"], summary["service"], summary["event_type"], summary["title"], summary["content_snippet"]]
                )
            out.append(
                {
                    "record_kind": "old_memory_sample",
                    "memory_id": row["memory_id"],
                    "memory_type": row["memory_type"],
                    "memory_subtype": row["memory_subtype"],
                    "subject": row["subject"],
                    "description": row["description"],
                    "confidence": float(row["confidence"] or 0.0),
                    "evidence_count": int(row["evidence_count"] or 0),
                    "created_at": row["created_at"],
                    "metadata": metadata,
                    "memory_link_evidence": event_summaries,
                    "allowed_evidence_refs": evidence_refs,
                    "text_blob": " | ".join(part for part in text_parts if part),
                }
            )
        return out
    finally:
        con.close()


def build_candidate_record(row: sqlite3.Row, turn_lookup: dict[str, dict], record_kind: str) -> dict:
    row = dict(row)
    source_turn = turn_lookup.get(row["source_node_id"], {})
    target_turn = turn_lookup.get(row["target_node_id"], {})
    judgment_refs = parse_json_field(row["evidence_refs_json"], [])
    risk_flags = parse_json_field(row["risk_flags_json"], [])
    source_refs = [ref for ref in [source_turn.get("source_ref"), target_turn.get("source_ref")] if ref]
    allowed_refs = list(dict.fromkeys([str(ref) for ref in judgment_refs + source_refs if str(ref).strip()]))
    text_parts = [
        row["candidate_id"],
        row["candidate_type"] or "",
        row["candidate_reason"] or "",
        row["relation_type"] or "",
        row["reason"] or "",
        source_turn.get("main_topic") or "",
        source_turn.get("narrative") or "",
        target_turn.get("main_topic") or "",
        target_turn.get("narrative") or "",
    ]
    return {
        "record_kind": record_kind,
        "candidate_id": row["candidate_id"],
        "candidate_type": row["candidate_type"] or "",
        "candidate_reason": row["candidate_reason"] or "",
        "relation_type": row["relation_type"] or "",
        "confidence": float(row["confidence"] or 0.0),
        "judge_reason": row["reason"] or "",
        "evidence_refs": judgment_refs,
        "risk_flags": [str(flag) for flag in risk_flags],
        "source_node_id": row["source_node_id"] or "",
        "target_node_id": row["target_node_id"] or "",
        "source_turn": source_turn,
        "target_turn": target_turn,
        "source_refs": source_refs,
        "allowed_evidence_refs": allowed_refs,
        "review_reason": row.get("review_reason") or "",
        "model": row.get("model") or "",
        "prompt_version": row.get("prompt_version") or "",
        "temperature": row.get("temperature"),
        "similarity": row.get("similarity"),
        "text_blob": " | ".join(part for part in text_parts if part),
    }


def load_accepted_candidates(turn_lookup: dict[str, dict]) -> list[dict]:
    rows = fetch_all(
        """
        SELECT j.candidate_id, j.relation_type, j.confidence, j.evidence_refs_json, j.reason,
               j.risk_flags_json, j.model, j.prompt_version, j.temperature,
               c.candidate_type, c.candidate_reason, c.source_node_id, c.target_node_id, c.similarity
        FROM graph_relation_judgments j
        JOIN graph_relation_candidates c ON c.candidate_id = j.candidate_id
        WHERE j.gate_status = 'accepted'
        ORDER BY j.confidence DESC, j.candidate_id
        """
    )
    return [build_candidate_record(row, turn_lookup, "accepted_graph_edge") for row in rows]


def load_review_samples(turn_lookup: dict[str, dict], sample_size: int) -> list[dict]:
    rows = fetch_all(
        """
        SELECT q.candidate_id, q.review_reason, q.relation_type, q.confidence,
               q.evidence_refs_json, q.risk_flags_json,
               j.reason, j.model, j.prompt_version, j.temperature,
               c.candidate_type, c.candidate_reason, c.source_node_id, c.target_node_id, c.similarity
        FROM graph_relation_review_queue q
        JOIN graph_relation_candidates c ON c.candidate_id = q.candidate_id
        LEFT JOIN graph_relation_judgments j ON j.candidate_id = q.candidate_id
        ORDER BY q.candidate_id
        LIMIT ?
        """,
        (sample_size,),
    )
    return [build_candidate_record(row, turn_lookup, "review_queue_sample") for row in rows]


def build_overlap_links(old_memories: list[dict], graph_records: list[dict], context_limit: int) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    old_index: dict[str, list[dict]] = defaultdict(list)
    graph_index: dict[str, list[dict]] = defaultdict(list)
    memory_tokens = {item["memory_id"]: tokenize_text(item["text_blob"]) for item in old_memories}
    graph_tokens = {item["candidate_id"]: tokenize_text(item["text_blob"]) for item in graph_records}

    for memory in old_memories:
        left = memory_tokens[memory["memory_id"]]
        for candidate in graph_records:
            right = graph_tokens[candidate["candidate_id"]]
            score = overlap_score(left, right)
            if score <= 0:
                continue
            snippet = {
                "candidate_id": candidate["candidate_id"],
                "record_kind": candidate["record_kind"],
                "relation_type": candidate["relation_type"],
                "confidence": candidate["confidence"],
                "candidate_type": candidate["candidate_type"],
                "review_reason": candidate["review_reason"],
                "overlap_score": round(score, 4),
                "judge_reason": safe_text(candidate["judge_reason"], 160),
                "source_main_topic": safe_text(candidate["source_turn"].get("main_topic"), 80),
                "target_main_topic": safe_text(candidate["target_turn"].get("main_topic"), 80),
                "allowed_evidence_refs": candidate["allowed_evidence_refs"][:4],
            }
            old_index[memory["memory_id"]].append(snippet)
            graph_index[candidate["candidate_id"]].append(
                {
                    "memory_id": memory["memory_id"],
                    "memory_type": memory["memory_type"],
                    "subject": memory["subject"],
                    "description": safe_text(memory["description"], 120),
                    "evidence_count": memory["evidence_count"],
                    "overlap_score": round(score, 4),
                    "allowed_evidence_refs": memory["allowed_evidence_refs"][:4],
                }
            )

    for memory_id, items in old_index.items():
        items.sort(key=lambda item: (-item["overlap_score"], -item["confidence"], item["candidate_id"]))
        old_index[memory_id] = items[:context_limit]
    for candidate_id, items in graph_index.items():
        items.sort(key=lambda item: (-item["overlap_score"], -item["evidence_count"], item["memory_id"]))
        graph_index[candidate_id] = items[:context_limit]
    return old_index, graph_index


def build_old_memory_payload(memory: dict, context_items: list[dict]) -> dict:
    return {
        "record_kind": "old_memory_sample",
        "focus": {
            "old_memory_id": memory["memory_id"],
            "memory_type": memory["memory_type"],
            "memory_subtype": memory["memory_subtype"],
            "subject": memory["subject"],
            "description": memory["description"],
            "confidence": memory["confidence"],
            "evidence_count": memory["evidence_count"],
            "created_at": memory["created_at"],
            "metadata_summary": {
                "rules_version": memory["metadata"].get("rules_version"),
                "recent_count": memory["metadata"].get("recent_count"),
                "active_months": memory["metadata"].get("active_months"),
                "total_events": memory["metadata"].get("total_events"),
            },
            "memory_link_evidence": memory["memory_link_evidence"],
        },
        "graph_context": context_items,
        "allowed_evidence_refs": list(dict.fromkeys(memory["allowed_evidence_refs"] + [ref for item in context_items for ref in item["allowed_evidence_refs"]])),
    }


def build_graph_payload(candidate: dict, context_items: list[dict]) -> dict:
    return {
        "record_kind": candidate["record_kind"],
        "focus": {
            "new_candidate_id": candidate["candidate_id"],
            "candidate_type": candidate["candidate_type"],
            "candidate_reason": candidate["candidate_reason"],
            "relation_type": candidate["relation_type"],
            "confidence": candidate["confidence"],
            "review_reason": candidate["review_reason"],
            "judge_reason": candidate["judge_reason"],
            "risk_flags": candidate["risk_flags"],
            "source_turn": {
                "session_id": candidate["source_turn"].get("session_id"),
                "turn_no": candidate["source_turn"].get("turn_no"),
                "turn_id": candidate["source_turn"].get("turn_id"),
                "main_topic": candidate["source_turn"].get("main_topic"),
                "source_ref": candidate["source_turn"].get("source_ref"),
                "narrative": candidate["source_turn"].get("narrative"),
            },
            "target_turn": {
                "session_id": candidate["target_turn"].get("session_id"),
                "turn_no": candidate["target_turn"].get("turn_no"),
                "turn_id": candidate["target_turn"].get("turn_id"),
                "main_topic": candidate["target_turn"].get("main_topic"),
                "source_ref": candidate["target_turn"].get("source_ref"),
                "narrative": candidate["target_turn"].get("narrative"),
            },
        },
        "old_memory_context": context_items,
        "allowed_evidence_refs": list(dict.fromkeys(candidate["allowed_evidence_refs"] + [ref for item in context_items for ref in item["allowed_evidence_refs"]])),
    }


def make_messages(system_prompt: str, user_template: str, payload: dict) -> list[dict]:
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    user_prompt = user_template.replace("{{payload_json}}", payload_json)
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def score_bucket(value: int, reverse: bool = False) -> int:
    value = max(0, min(10, value))
    if value >= 8:
        score = 5
    elif value >= 6:
        score = 4
    elif value >= 4:
        score = 3
    elif value >= 2:
        score = 2
    elif value >= 1:
        score = 1
    else:
        score = 0
    return 5 - score if reverse else score


def fallback_decision(payload: dict, runtime_status: str, model: str, temperature: float) -> dict:
    kind = payload["record_kind"]
    allowed_refs = payload.get("allowed_evidence_refs", [])
    base = {
        "record_kind": kind,
        "old_memory_id": None,
        "new_candidate_id": None,
        "judgment": "no_clear_match",
        "long_term_value_score": 3,
        "duplicate_status": "no_clear_match",
        "conflict_status": "insufficient_evidence",
        "recommended_action": "review_only",
        "dimension_scores": {
            "evidence_coverage": 2,
            "source_traceability": 2,
            "relation_depth": 2,
            "noise_risk": 3,
            "long_term_usefulness": 2,
            "retrieval_usefulness": 2,
            "duplicate_overlap": 1,
            "conflict_risk": 2,
        },
        "evidence_refs": allowed_refs[:3],
        "reason": "使用 deterministic fallback 生成比较结果；未进行真实 LLM judgment。",
        "risk_flags": [runtime_status.replace(":", "_"), "deterministic_fallback"],
        "prompt_version": PROMPT_VERSION,
        "model": model,
        "temperature": temperature,
        "llm_status": runtime_status,
    }
    if kind == "old_memory_sample":
        focus = payload["focus"]
        context = payload.get("graph_context", [])
        match = context[0] if context else None
        long_term_score = min(10, max(1, int(focus.get("evidence_count", 0) / 3) + (2 if focus["memory_type"] in {"tooling", "capability", "preference"} else 0)))
        base["old_memory_id"] = focus["old_memory_id"]
        base["long_term_value_score"] = long_term_score
        base["dimension_scores"] = {
            "evidence_coverage": min(5, max(1, int(focus.get("evidence_count", 0) / 4) + 1)),
            "source_traceability": 4 if focus.get("memory_link_evidence") else 1,
            "relation_depth": 3 if match else 2,
            "noise_risk": 1 if focus["memory_type"] in {"tooling", "preference", "capability"} else 3,
            "long_term_usefulness": score_bucket(long_term_score),
            "retrieval_usefulness": 4 if focus["memory_type"] in {"tooling", "preference", "capability"} else 3,
            "duplicate_overlap": 4 if match and match["overlap_score"] >= 0.12 else 1,
            "conflict_risk": 2,
        }
        if match and match["relation_type"] in {"preference_signal", "tool_used_for"} and match["overlap_score"] >= 0.12:
            base["new_candidate_id"] = match["candidate_id"]
            base["judgment"] = "merge_candidate"
            base["duplicate_status"] = "overlaps_old_memory"
            base["conflict_status"] = "no_conflict"
            base["recommended_action"] = "merge_candidate"
            base["reason"] = "旧 memory 具备长期价值，且存在高重叠 graph signal，可进入后续 merge/promotion candidate 评审。"
            base["evidence_refs"] = list(dict.fromkeys(base["evidence_refs"] + match["allowed_evidence_refs"]))[:4]
        elif focus["memory_type"] in {"tooling", "capability", "preference", "habit"} and long_term_score >= 6:
            base["judgment"] = "retain_old_memory"
            base["duplicate_status"] = "distinct"
            base["conflict_status"] = "no_conflict"
            base["recommended_action"] = "keep"
            base["reason"] = "旧 memory 证据量较高且类型偏长期信号，fallback 判断为继续保留。"
        elif focus["memory_type"] in {"fact", "project"} and focus.get("evidence_count", 0) <= 2:
            base["judgment"] = "downgrade_old_memory"
            base["duplicate_status"] = "distinct"
            base["conflict_status"] = "temporal_or_scope_conflict"
            base["recommended_action"] = "downgrade"
            base["reason"] = "旧 memory 更像弱证据或阶段性上下文，fallback 判断为降级候选。"
        else:
            base["judgment"] = "analysis_only"
            base["duplicate_status"] = "potential_duplicate" if match else "no_clear_match"
            base["conflict_status"] = "insufficient_evidence"
            base["recommended_action"] = "review_only"
            base["reason"] = "旧 memory 暂未形成明确保留/删除结论，fallback 保守标记为 review_only。"
        return base

    focus = payload["focus"]
    context = payload.get("old_memory_context", [])
    match = context[0] if context else None
    conf = float(focus.get("confidence") or 0.0)
    stable_relation = focus["relation_type"] in {"preference_signal", "tool_used_for"}
    episodic_relation = focus["relation_type"] in {"same_problem", "subproblem_of", "follow_up", "temporal_next"}
    base["new_candidate_id"] = focus["new_candidate_id"]
    base["old_memory_id"] = match["memory_id"] if match and match["overlap_score"] >= 0.12 else None
    base["long_term_value_score"] = 8 if stable_relation and conf >= 0.75 else 4 if episodic_relation else 3
    base["dimension_scores"] = {
        "evidence_coverage": 4 if focus.get("source_turn", {}).get("source_ref") else 2,
        "source_traceability": 5 if base["evidence_refs"] else 2,
        "relation_depth": 4 if stable_relation else 2,
        "noise_risk": 1 if stable_relation else 4 if episodic_relation else 3,
        "long_term_usefulness": score_bucket(base["long_term_value_score"]),
        "retrieval_usefulness": 4 if stable_relation else 2,
        "duplicate_overlap": 4 if match and match["overlap_score"] >= 0.12 else 1,
        "conflict_risk": 4 if focus["relation_type"] == "contradiction" else 2,
    }
    if stable_relation and conf >= 0.75:
        base["judgment"] = "graph_promotion_candidate"
        base["duplicate_status"] = "overlaps_old_memory" if base["old_memory_id"] else "distinct"
        base["conflict_status"] = "no_conflict"
        base["recommended_action"] = "merge_candidate" if base["old_memory_id"] else "promote_candidate"
        base["reason"] = "graph edge 指向稳定偏好/工具信号，fallback 判断适合进入后续 promotion candidate 层。"
    elif focus["relation_type"] == "contradiction":
        base["judgment"] = "review_only"
        base["duplicate_status"] = "distinct"
        base["conflict_status"] = "conflicts_graph_context"
        base["recommended_action"] = "review_only"
        base["reason"] = "graph edge 含冲突语义，fallback 不建议直接晋级，只保留 review。"
    else:
        base["judgment"] = "analysis_only"
        base["duplicate_status"] = "potential_duplicate" if base["old_memory_id"] else "distinct"
        base["conflict_status"] = "temporal_or_scope_conflict" if episodic_relation else "insufficient_evidence"
        base["recommended_action"] = "analysis_only"
        base["reason"] = "graph edge 更像过程关系或分析线索，fallback 建议只留在分析层。"
    return base


def normalize_dimension_scores(raw: Any) -> dict:
    out = {}
    raw = raw if isinstance(raw, dict) else {}
    for key in DIMENSION_KEYS:
        value = raw.get(key, 0)
        try:
            num = int(round(float(value)))
        except (TypeError, ValueError):
            num = 0
        out[key] = max(0, min(5, num))
    return out


def normalize_result(parsed: dict | None, payload: dict, runtime_status: str, model: str, temperature: float) -> dict:
    if not parsed:
        return fallback_decision(payload, runtime_status, model, temperature)

    allowed_ref_list = [str(ref) for ref in payload.get("allowed_evidence_refs", []) if str(ref).strip()]
    allowed_refs = set(allowed_ref_list)
    result = {
        "record_kind": str(parsed.get("record_kind") or payload["record_kind"]).strip(),
        "old_memory_id": parsed.get("old_memory_id"),
        "new_candidate_id": parsed.get("new_candidate_id"),
        "judgment": str(parsed.get("judgment") or "no_clear_match").strip(),
        "long_term_value_score": 0,
        "duplicate_status": str(parsed.get("duplicate_status") or "no_clear_match").strip(),
        "conflict_status": str(parsed.get("conflict_status") or "insufficient_evidence").strip(),
        "recommended_action": str(parsed.get("recommended_action") or "review_only").strip(),
        "dimension_scores": normalize_dimension_scores(parsed.get("dimension_scores")),
        "evidence_refs": [],
        "reason": str(parsed.get("reason") or "").strip() or "(empty reason)",
        "risk_flags": [str(flag) for flag in parsed.get("risk_flags", []) if str(flag).strip()] if isinstance(parsed.get("risk_flags"), list) else [],
        "prompt_version": PROMPT_VERSION,
        "model": model,
        "temperature": temperature,
        "llm_status": runtime_status,
    }

    try:
        result["long_term_value_score"] = max(0, min(10, int(round(float(parsed.get("long_term_value_score", 0))))))
    except (TypeError, ValueError):
        result["long_term_value_score"] = 0

    refs = parsed.get("evidence_refs") if isinstance(parsed.get("evidence_refs"), list) else []
    normalized_refs = [str(ref) for ref in refs if str(ref).strip() and str(ref) in allowed_refs]
    result["evidence_refs"] = normalized_refs[:6]
    if refs and not normalized_refs:
        result["risk_flags"].append("invalid_evidence_refs_filtered")
        result["evidence_refs"] = allowed_ref_list[:3]

    if result["record_kind"] not in RECORD_KINDS:
        result["record_kind"] = payload["record_kind"]
        result["risk_flags"].append("invalid_record_kind")

    if payload["record_kind"] == "old_memory_sample":
        result["old_memory_id"] = payload["focus"]["old_memory_id"]
        if result["recommended_action"] not in OLD_MEMORY_ACTIONS:
            result["recommended_action"] = "review_only"
            result["risk_flags"].append("invalid_old_memory_action")
    else:
        result["new_candidate_id"] = payload["focus"]["new_candidate_id"]
        if result["recommended_action"] not in GRAPH_ACTIONS:
            result["recommended_action"] = "analysis_only"
            result["risk_flags"].append("invalid_graph_action")

    if not result["evidence_refs"] and allowed_refs:
        result["evidence_refs"] = allowed_ref_list[:3]
        result["risk_flags"].append("evidence_refs_defaulted")
    return result


def judge_payload(payload: dict, runtime: LLMRuntime, system_prompt: str, user_template: str, model: str, temperature: float) -> dict:
    if runtime.status != "live" or runtime.client is None:
        return fallback_decision(payload, runtime.status, model, temperature)
    try:
        raw = llm_mod._chat_with_retry(
            runtime.client,
            model,
            messages=make_messages(system_prompt, user_template, payload),
            temperature=temperature,
        )
        return normalize_result(extract_json(raw), payload, "live", model, temperature)
    except Exception as exc:  # pragma: no cover - network dependent
        runtime_status = f"fallback:judge_failed:{type(exc).__name__}"
        return fallback_decision(payload, runtime_status, model, temperature)


def summarize_records(records: list[dict]) -> dict:
    by_kind = Counter(record["record_kind"] for record in records)
    by_llm_status = Counter(record["llm_status"] for record in records)
    old_actions = Counter(record["recommended_action"] for record in records if record["record_kind"] == "old_memory_sample")
    accepted_actions = Counter(record["recommended_action"] for record in records if record["record_kind"] == "accepted_graph_edge")
    review_actions = Counter(record["recommended_action"] for record in records if record["record_kind"] == "review_queue_sample")
    return {
        "record_count": len(records),
        "by_record_kind": dict(by_kind),
        "by_llm_status": dict(by_llm_status),
        "old_memory_actions": dict(old_actions),
        "accepted_edge_actions": dict(accepted_actions),
        "review_queue_actions": dict(review_actions),
    }


def render_md(report: dict) -> str:
    lines = [
        "# Memory Experiment Comparison",
        "",
        f"- generated_at: {report['generated_at']}",
        f"- prompt_version: {report['prompt_version']}",
        f"- schema_version: {report['schema_version']}",
        f"- llm_status: {report['llm_status']}",
        f"- model: {report['model']}",
        f"- temperature: {report['temperature']}",
        "",
        "## Input Scope",
        "",
        f"- old_memory_sample_count: {report['inputs']['old_memory_sample_count']}",
        f"- accepted_graph_edge_count: {report['inputs']['accepted_graph_edge_count']}",
        f"- review_queue_sample_count: {report['inputs']['review_queue_sample_count']}",
        "",
        "## LLM Status",
        "",
    ]
    for key, value in sorted(report["summary"]["by_llm_status"].items()):
        lines.append(f"- {key}: {value}")

    lines += ["", "## Old Memory Decisions", ""]
    for key, value in sorted(report["summary"]["old_memory_actions"].items()):
        lines.append(f"- {key}: {value}")
    if not report["summary"]["old_memory_actions"]:
        lines.append("- none")

    lines += ["", "## Accepted Graph Edge Decisions", ""]
    for key, value in sorted(report["summary"]["accepted_edge_actions"].items()):
        lines.append(f"- {key}: {value}")
    if not report["summary"]["accepted_edge_actions"]:
        lines.append("- none")

    lines += ["", "## Review Queue Decisions", ""]
    for key, value in sorted(report["summary"]["review_queue_actions"].items()):
        lines.append(f"- {key}: {value}")
    if not report["summary"]["review_queue_actions"]:
        lines.append("- none")

    lines += ["", "## Old Memory Keep / Downgrade / Merge / Delete Candidates", ""]
    for record in report["records"]:
        if record["record_kind"] != "old_memory_sample":
            continue
        lines.append(
            f"- `{record['old_memory_id']}` | {record['recommended_action']} | score={record['long_term_value_score']} | "
            f"match={record.get('new_candidate_id') or '-'} | {record['reason']}"
        )

    lines += ["", "## Phase 07 Accepted Graph Edges: Promote vs Analysis Layer", ""]
    for record in report["records"]:
        if record["record_kind"] != "accepted_graph_edge":
            continue
        lines.append(
            f"- `{record['new_candidate_id']}` | {record['recommended_action']} | score={record['long_term_value_score']} | "
            f"old_memory={record.get('old_memory_id') or '-'} | {record['reason']}"
        )

    lines += ["", "## Review Queue Samples", ""]
    for record in report["records"]:
        if record["record_kind"] != "review_queue_sample":
            continue
        lines.append(
            f"- `{record['new_candidate_id']}` | {record['recommended_action']} | score={record['long_term_value_score']} | "
            f"old_memory={record.get('old_memory_id') or '-'} | {record['reason']}"
        )

    lines += ["", "## Notes", ""]
    lines.append("- 本报告只生成 comparison 结论，不写 `memory_items` / `memory_relations` / promotion table。")
    lines.append("- `llm_status` 为 `live` 时表示真实调用 OpenAI-compatible endpoint；`fallback:*` 表示 deterministic mock/fallback。")
    return "\n".join(lines) + "\n"


def build_report(records: list[dict], old_memories: list[dict], accepted: list[dict], review_samples: list[dict], llm_status: str, model: str, temperature: float) -> dict:
    summary = summarize_records(records)
    overall_llm_status = llm_status if len(summary["by_llm_status"]) <= 1 else "mixed"
    return {
        "generated_at": utc_now(),
        "phase": "08",
        "wave": "2",
        "prompt_version": PROMPT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "llm_status": overall_llm_status,
        "model": model,
        "temperature": temperature,
        "inputs": {
            "old_memory_sample_count": len(old_memories),
            "accepted_graph_edge_count": len(accepted),
            "review_queue_sample_count": len(review_samples),
        },
        "summary": summary,
        "records": records,
    }


def run_dry_run(old_memories: list[dict], accepted: list[dict], review_samples: list[dict], payloads: list[dict], llm_status: str, limit: int) -> int:
    print(f"[dry] llm_status={llm_status}")
    print(f"[dry] old_memory_sample_count={len(old_memories)} accepted_graph_edge_count={len(accepted)} review_queue_sample_count={len(review_samples)}")
    preview_payloads: list[dict] = []
    preview_payloads.extend(payloads[: min(len(old_memories), max(1, min(limit, 2)))])
    old_count = len(preview_payloads)
    graph_payloads = payloads[len(old_memories):]
    remaining = max(0, limit - old_count)
    if graph_payloads and remaining:
        preview_payloads.extend(graph_payloads[:remaining])
    if not preview_payloads:
        preview_payloads = payloads[:1]
    for idx, payload in enumerate(preview_payloads, 1):
        print("=" * 80)
        print(f"[preview {idx}] kind={payload['record_kind']}")
        print(json.dumps(payload, ensure_ascii=False, indent=2)[:PREVIEW_CHARS])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare first-gen memories with Phase 07 graph edges.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--limit", type=int, default=5, help="dry-run preview payload count")
    parser.add_argument("--old-sample-size", type=int, default=DEFAULT_OLD_SAMPLE_SIZE)
    parser.add_argument("--review-sample-size", type=int, default=DEFAULT_REVIEW_SAMPLE_SIZE)
    parser.add_argument("--model", default=os.environ.get("MEM0_LLM_MODEL", DEFAULT_MODEL))
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    args = parser.parse_args(argv)

    if args.dry_run and args.write:
        print("[error] --dry-run 与 --write 互斥", file=sys.stderr)
        return 2
    if not args.dry_run and not args.write:
        print("[error] 必须指定 --dry-run 或 --write", file=sys.stderr)
        return 2
    if args.old_sample_size < 20 and args.write:
        print("[error] --write 时 old-sample-size 必须 >= 20", file=sys.stderr)
        return 2

    system_prompt, user_template = load_prompts()
    runtime = make_llm_runtime()
    turn_lookup = build_turn_lookup()
    old_memories = load_old_memories(args.old_sample_size, DEFAULT_MAX_EVENT_LINKS)
    accepted = load_accepted_candidates(turn_lookup)
    review_samples = load_review_samples(turn_lookup, args.review_sample_size)
    graph_records = accepted + review_samples
    old_index, graph_index = build_overlap_links(old_memories, graph_records, DEFAULT_CONTEXT_LIMIT)

    payloads = [build_old_memory_payload(memory, old_index.get(memory["memory_id"], [])) for memory in old_memories]
    payloads.extend(build_graph_payload(candidate, graph_index.get(candidate["candidate_id"], [])) for candidate in graph_records)

    if args.dry_run:
        return run_dry_run(old_memories, accepted, review_samples, payloads, runtime.status, args.limit)

    records = [
        judge_payload(payload, runtime, system_prompt, user_template, args.model, args.temperature)
        for payload in payloads
    ]
    report = build_report(records, old_memories, accepted, review_samples, runtime.status, args.model, args.temperature)
    md = render_md(report)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    OUT_MD.write_text(md, encoding="utf-8")
    print(f"llm_status: {runtime.status}")
    print(f"old_memory_sample_count: {len(old_memories)}")
    print(f"accepted_graph_edge_count: {len(accepted)}")
    print(f"review_queue_sample_count: {len(review_samples)}")
    print(f"[write] {OUT_JSON.relative_to(ROOT)}")
    print(f"[write] {OUT_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
