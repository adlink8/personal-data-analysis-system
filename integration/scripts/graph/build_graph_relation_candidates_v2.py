"""Wave 9.2: LLM-assisted graph relation candidate generation.

两段式流程:
1. 脚本只做 coarse recall package,不直接把 pair 当成 graph candidate。
2. LLM 基于 package 输出 semantic candidate proposal。
3. 只有通过 schema/evidence gate 的 proposal 才能写入 graph_relation_candidates。

无 live LLM / API key 时:
- 不伪装 live
- 可以写 proposal 审计表和 report
- 不把 coarse recall 直接写成 accepted graph candidates
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

from conversation import build_conversation_summary as llm_mod
from graph import build_graph_relation_candidates as base
ROOT = Path(__file__).resolve().parents[3]
PROMPT_DIR = ROOT / "integration" / "prompts" / "graph_candidate_proposal"
REPORT_JSON = ROOT / "integration" / "analysis" / "ai_context" / "graph_relation_candidate_proposals_report.json"
REPORT_MD = ROOT / "integration" / "analysis" / "ai_context" / "graph_relation_candidate_proposals_report.md"

DEFAULT_LIMIT = 0
DEFAULT_TOP_K = 6
DEFAULT_MODEL = os.environ.get("MEM0_LLM_MODEL", "gpt-5.4")
DEFAULT_TEMPERATURE = 0.2
PROMPT_VERSION = "graph_candidate_proposal/v1"
GRAPH_CANDIDATE_TYPE_V2 = "semantic_candidate_v2"

ALLOWED_RELATION_TYPES = {
    "same_problem",
    "subproblem_of",
    "follow_up",
    "tool_used_for",
    "preference_signal",
    "contradiction",
    "temporal_next",
    "capability_signal",
    "tooling_signal",
    "no_relation",
}
ALLOWED_PROPOSAL_STATUS = {"proposed", "downgrade", "reject", "needs_human_review", "blocked"}
ALLOWED_CANDIDATE_TYPE = {"semantic_relation_candidate", "weak_semantic_signal"}

PROPOSAL_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS graph_relation_candidate_proposals (
    proposal_id TEXT PRIMARY KEY,
    candidate_id TEXT,
    package_id TEXT NOT NULL,
    source_node_id TEXT NOT NULL,
    target_node_id TEXT NOT NULL,
    proposed_relation_type TEXT NOT NULL,
    proposal_status TEXT NOT NULL,
    candidate_type TEXT NOT NULL,
    why_candidate TEXT NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    source_refs_json TEXT NOT NULL,
    risk_flags_json TEXT NOT NULL,
    event_ids_json TEXT NOT NULL DEFAULT '[]',
    session_ids_json TEXT NOT NULL DEFAULT '[]',
    turn_ids_json TEXT NOT NULL DEFAULT '[]',
    needs_human_review INTEGER NOT NULL DEFAULT 0,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    temperature REAL NOT NULL,
    llm_status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_grcp_package_id ON graph_relation_candidate_proposals(package_id);
CREATE INDEX IF NOT EXISTS idx_grcp_status ON graph_relation_candidate_proposals(proposal_status);
CREATE INDEX IF NOT EXISTS idx_grcp_llm_status ON graph_relation_candidate_proposals(llm_status);
"""


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}:{digest}"


def unique_strs(values: list | tuple | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def load_turn_index() -> tuple[dict[str, dict], list[str]]:
    if not base.SUMMARIES_JSON.exists():
        raise FileNotFoundError(f"缺少 summary 产物: {base.SUMMARIES_JSON}")
    data = json.loads(base.SUMMARIES_JSON.read_text(encoding="utf-8"))
    turn_map: dict[str, dict] = {}
    order: list[str] = []
    for session in data:
        sid = session["session_id"]
        main_topic = session.get("main_topic", "")
        source = session.get("meta", {}).get("source", "")
        for turn_no, turn in enumerate(session.get("turn_summaries", []), 1):
            node_id = base.make_node_id(sid, turn.get("turn_id"), turn_no)
            turn_map[node_id] = {
                "node_id": node_id,
                "session_id": sid,
                "turn_id": turn.get("turn_id") or "",
                "turn_no": turn_no,
                "main_topic": main_topic,
                "source": source,
                "narrative": (turn.get("narrative") or "").strip(),
                "source_refs": unique_strs(turn.get("source_refs") or []),
                "tools_used": unique_strs(turn.get("tools_used") or []),
            }
            order.append(node_id)
    return turn_map, order


def build_same_session_adjacent_packages(turn_map: dict[str, dict], order: list[str]) -> list[dict]:
    raw = base.build_temporal_candidates(turn_map, order)
    filtered, _stats = base.filter_candidates(raw, min_semantic_score=0.0)
    out = []
    for cand in filtered:
        out.append(
            {
                "source_node_id": cand["source_node_id"],
                "target_node_id": cand["target_node_id"],
                "signal": "same_session_adjacent",
                "signal_reason": cand["candidate_reason"],
                "signal_score": float(cand.get("similarity") or 1.0),
            }
        )
    return out


def build_vector_topk_packages(
    turn_map: dict[str, dict], embedded_rows: list[dict], top_k: int, min_similarity: float
) -> list[dict]:
    raw = base.build_semantic_candidates(turn_map, embedded_rows, top_k)
    filtered, _stats = base.filter_candidates(raw, min_similarity)
    out = []
    for cand in filtered:
        out.append(
            {
                "source_node_id": cand["source_node_id"],
                "target_node_id": cand["target_node_id"],
                "signal": "vector_topk",
                "signal_reason": cand["candidate_reason"],
                "signal_score": float(cand.get("similarity") or 0.0),
            }
        )
    return out


def merge_coarse_packages(turn_map: dict[str, dict], signals: list[dict]) -> list[dict]:
    packages: dict[tuple[str, str], dict] = {}
    for row in signals:
        src = row["source_node_id"]
        tgt = row["target_node_id"]
        if src not in turn_map or tgt not in turn_map or src == tgt:
            continue
        left, right = base.canonical_pair(src, tgt)
        key = (left, right)
        src_turn = turn_map[left]
        tgt_turn = turn_map[right]
        package = packages.get(key)
        if not package:
            package = {
                "package_id": stable_id("grpkg", left, right),
                "source_node_id": left,
                "target_node_id": right,
                "source_turn": {
                    "node_id": left,
                    "session_id": src_turn["session_id"],
                    "turn_id": src_turn["turn_id"] or f"t{src_turn['turn_no']}",
                    "turn_no": src_turn["turn_no"],
                    "main_topic": src_turn.get("main_topic") or "",
                    "narrative": src_turn.get("narrative") or "",
                    "source_refs": list(src_turn.get("source_refs") or []),
                    "tools_used": list(src_turn.get("tools_used") or []),
                },
                "target_turn": {
                    "node_id": right,
                    "session_id": tgt_turn["session_id"],
                    "turn_id": tgt_turn["turn_id"] or f"t{tgt_turn['turn_no']}",
                    "turn_no": tgt_turn["turn_no"],
                    "main_topic": tgt_turn.get("main_topic") or "",
                    "narrative": tgt_turn.get("narrative") or "",
                    "source_refs": list(tgt_turn.get("source_refs") or []),
                    "tools_used": list(tgt_turn.get("tools_used") or []),
                },
                "coarse_recall_signals": [],
                "signal_reasons": [],
                "signal_scores": {},
                "allowed_source_refs": unique_strs(
                    list(src_turn.get("source_refs") or []) + list(tgt_turn.get("source_refs") or [])
                ),
                "allowed_session_ids": unique_strs([src_turn["session_id"], tgt_turn["session_id"]]),
                "allowed_turn_ids": unique_strs(
                    [
                        src_turn["turn_id"] or f"t{src_turn['turn_no']}",
                        tgt_turn["turn_id"] or f"t{tgt_turn['turn_no']}",
                    ]
                ),
                "allowed_event_ids": [],
            }
            packages[key] = package
        if row["signal"] not in package["coarse_recall_signals"]:
            package["coarse_recall_signals"].append(row["signal"])
        reason = str(row.get("signal_reason") or "").strip()
        if reason and reason not in package["signal_reasons"]:
            package["signal_reasons"].append(reason)
        package["signal_scores"][row["signal"]] = max(
            float(package["signal_scores"].get(row["signal"], 0.0)), float(row.get("signal_score") or 0.0)
        )
    return list(packages.values())


def load_prompt_assets() -> tuple[str, str]:
    main_prompt = (PROMPT_DIR / "v1_main.md").read_text(encoding="utf-8").strip()
    schema_text = (PROMPT_DIR / "v1_schema.md").read_text(encoding="utf-8").strip()
    return main_prompt, schema_text


def build_llm_messages(package: dict, main_prompt: str, schema_text: str) -> list[dict]:
    system_prompt = (
        f"{main_prompt}\n\n"
        "下面是输出 schema 约束。你必须严格遵守，且只能引用输入中已有的 refs / ids。\n\n"
        f"{schema_text}"
    )
    package_payload = {
        "package_id": package["package_id"],
        "prompt_version": PROMPT_VERSION,
        "llm_status": "live_api_key_present",
        "coarse_recall_signals": package["coarse_recall_signals"],
        "signal_reasons": package["signal_reasons"],
        "pair": {
            "source_node_id": package["source_node_id"],
            "target_node_id": package["target_node_id"],
            "source_turn": package["source_turn"],
            "target_turn": package["target_turn"],
            "source_refs": package["allowed_source_refs"],
            "event_ids": package["allowed_event_ids"],
            "session_ids": package["allowed_session_ids"],
            "turn_ids": package["allowed_turn_ids"],
        },
    }
    user_prompt = (
        "请基于下面 package 输出 JSON。只能输出 JSON，不要输出解释。\n\n"
        f"{json.dumps(package_payload, ensure_ascii=False, indent=2)}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def extract_json(raw: str) -> dict | None:
    if not raw:
        return None
    text = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def detect_llm_status() -> tuple[str, bool]:
    if not (os.environ.get("OPENAI_API_KEY") or os.environ.get("MEM0_API_KEY")):
        return "fallback:no_api_key", False
    return "live_api_key_present", True


def make_proposal_id(package_id: str, source_node_id: str, target_node_id: str, relation_type: str, status: str) -> str:
    return stable_id("grcp", package_id, source_node_id, target_node_id, relation_type, status)


def build_audit_row(
    *,
    package: dict,
    source_node_id: str,
    target_node_id: str,
    relation_type: str,
    proposal_status: str,
    candidate_type: str,
    why_candidate: str,
    evidence_refs: list[str],
    source_refs: list[str],
    risk_flags: list[str],
    event_ids: list[str],
    session_ids: list[str],
    turn_ids: list[str],
    needs_human_review: bool,
    model: str,
    temperature: float,
    llm_status: str,
    prompt_version: str = PROMPT_VERSION,
    candidate_id: str | None = None,
) -> dict:
    if not candidate_id:
        candidate_id = stable_id("grcand", package["package_id"], source_node_id, target_node_id, relation_type)
    return {
        "proposal_id": make_proposal_id(package["package_id"], source_node_id, target_node_id, relation_type, proposal_status),
        "candidate_id": candidate_id,
        "package_id": package["package_id"],
        "source_node_id": source_node_id,
        "target_node_id": target_node_id,
        "proposed_relation_type": relation_type,
        "proposal_status": proposal_status,
        "candidate_type": candidate_type,
        "why_candidate": why_candidate,
        "evidence_refs_json": json.dumps(unique_strs(evidence_refs), ensure_ascii=False),
        "source_refs_json": json.dumps(unique_strs(source_refs), ensure_ascii=False),
        "risk_flags_json": json.dumps(unique_strs(risk_flags), ensure_ascii=False),
        "event_ids_json": json.dumps(unique_strs(event_ids), ensure_ascii=False),
        "session_ids_json": json.dumps(unique_strs(session_ids), ensure_ascii=False),
        "turn_ids_json": json.dumps(unique_strs(turn_ids), ensure_ascii=False),
        "needs_human_review": 1 if needs_human_review else 0,
        "model": model,
        "prompt_version": prompt_version,
        "temperature": temperature,
        "llm_status": llm_status,
        "created_at": _now_iso(),
    }


def blocked_row_for_package(package: dict, llm_status: str, model: str, temperature: float, reason: str) -> dict:
    return build_audit_row(
        package=package,
        source_node_id=package["source_node_id"],
        target_node_id=package["target_node_id"],
        relation_type="no_relation",
        proposal_status="blocked",
        candidate_type="weak_semantic_signal",
        why_candidate=reason,
        evidence_refs=[],
        source_refs=package["allowed_source_refs"],
        risk_flags=[llm_status.replace(":", "_"), "no_llm_proposal"],
        event_ids=package["allowed_event_ids"],
        session_ids=package["allowed_session_ids"],
        turn_ids=package["allowed_turn_ids"],
        needs_human_review=True,
        model=model,
        temperature=temperature,
        llm_status=llm_status,
    )


def rejection_row_for_package(
    package: dict, llm_status: str, model: str, temperature: float, reason: str, flag: str
) -> dict:
    return build_audit_row(
        package=package,
        source_node_id=package["source_node_id"],
        target_node_id=package["target_node_id"],
        relation_type="no_relation",
        proposal_status="reject",
        candidate_type="weak_semantic_signal",
        why_candidate=reason,
        evidence_refs=[],
        source_refs=package["allowed_source_refs"],
        risk_flags=[flag],
        event_ids=package["allowed_event_ids"],
        session_ids=package["allowed_session_ids"],
        turn_ids=package["allowed_turn_ids"],
        needs_human_review=False,
        model=model,
        temperature=temperature,
        llm_status=llm_status,
    )


def validate_proposal_fields(proposal: dict, package: dict) -> tuple[dict | None, str | None, str | None]:
    if not isinstance(proposal, dict):
        return None, "proposal is not an object", None

    candidate_type = str(proposal.get("candidate_type") or "").strip()
    source_node_id = str(proposal.get("source_node_id") or "").strip()
    target_node_id = str(proposal.get("target_node_id") or "").strip()
    relation_type = str(proposal.get("proposed_relation_type") or "").strip()
    proposal_status = str(proposal.get("proposal_status") or "").strip()
    why_candidate = str(proposal.get("why_candidate") or "").strip()
    if not all([candidate_type, source_node_id, target_node_id, relation_type, proposal_status, why_candidate]):
        return None, "missing required proposal fields", None
    if candidate_type not in ALLOWED_CANDIDATE_TYPE:
        return None, f"invalid candidate_type={candidate_type}", None
    if relation_type not in ALLOWED_RELATION_TYPES:
        return None, f"invalid proposed_relation_type={relation_type}", None
    if proposal_status not in ALLOWED_PROPOSAL_STATUS - {"blocked"}:
        return None, f"invalid proposal_status={proposal_status}", None

    package_nodes = {package["source_node_id"], package["target_node_id"]}
    if source_node_id not in package_nodes or target_node_id not in package_nodes or source_node_id == target_node_id:
        return None, "proposal nodes are outside package pair", None

    evidence_refs = unique_strs(proposal.get("evidence_refs") or [])
    source_refs = unique_strs(proposal.get("source_refs") or [])
    risk_flags = unique_strs(proposal.get("risk_flags") or [])
    event_ids = unique_strs(proposal.get("event_ids") or [])
    session_ids = unique_strs(proposal.get("session_ids") or [])
    turn_ids = unique_strs(proposal.get("turn_ids") or [])
    needs_human_review = bool(proposal.get("needs_human_review", False))

    if needs_human_review and proposal_status not in {"needs_human_review", "downgrade"}:
        return None, "needs_human_review=true requires needs_human_review or downgrade", None
    if proposal_status == "proposed":
        if relation_type == "no_relation":
            return None, "proposed proposal cannot use no_relation", None
        if not evidence_refs or not source_refs:
            return None, "proposed proposal requires evidence_refs and source_refs", None

    allowed_source_refs = set(package["allowed_source_refs"])
    allowed_session_ids = set(package["allowed_session_ids"])
    allowed_turn_ids = set(package["allowed_turn_ids"])
    allowed_event_ids = set(package["allowed_event_ids"])
    if any(ref not in allowed_source_refs for ref in evidence_refs):
        return None, None, "evidence_refs contain values outside package"
    if any(ref not in allowed_source_refs for ref in source_refs):
        return None, None, "source_refs contain values outside package"
    if any(value not in allowed_session_ids for value in session_ids):
        return None, None, "session_ids contain values outside package"
    if any(value not in allowed_turn_ids for value in turn_ids):
        return None, None, "turn_ids contain values outside package"
    if any(value not in allowed_event_ids for value in event_ids):
        return None, None, "event_ids contain values outside package"

    return (
        {
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "relation_type": relation_type,
            "proposal_status": proposal_status,
            "candidate_type": candidate_type,
            "why_candidate": why_candidate,
            "evidence_refs": evidence_refs,
            "source_refs": source_refs,
            "risk_flags": risk_flags,
            "event_ids": event_ids,
            "session_ids": session_ids,
            "turn_ids": turn_ids,
            "needs_human_review": needs_human_review,
            "candidate_id": str(proposal.get("candidate_id") or "").strip() or None,
        },
        None,
        None,
    )


def normalize_llm_response(
    parsed: dict | None, package: dict, llm_status: str, model: str, temperature: float
) -> tuple[list[dict], int, int]:
    if not parsed:
        return [rejection_row_for_package(package, llm_status, model, temperature, "LLM 输出无法解析为 JSON", "schema_invalid")], 1, 0
    if str(parsed.get("package_id") or "").strip() != package["package_id"]:
        return [rejection_row_for_package(package, llm_status, model, temperature, "package_id 不匹配", "schema_invalid")], 1, 0
    proposals = parsed.get("candidate_proposals")
    if not isinstance(proposals, list) or not proposals:
        return [rejection_row_for_package(package, llm_status, model, temperature, "candidate_proposals 为空", "schema_invalid")], 1, 0

    out: list[dict] = []
    schema_rejected = 0
    evidence_rejected = 0
    for proposal in proposals:
        normalized, schema_error, evidence_error = validate_proposal_fields(proposal, package)
        if schema_error:
            schema_rejected += 1
            out.append(
                rejection_row_for_package(
                    package,
                    llm_status,
                    model,
                    temperature,
                    f"schema gate rejected: {schema_error}",
                    "schema_invalid",
                )
            )
            continue
        if evidence_error:
            evidence_rejected += 1
            out.append(
                rejection_row_for_package(
                    package,
                    llm_status,
                    model,
                    temperature,
                    f"evidence gate rejected: {evidence_error}",
                    "evidence_invalid",
                )
            )
            continue
        assert normalized is not None
        out.append(
            build_audit_row(
                package=package,
                source_node_id=normalized["source_node_id"],
                target_node_id=normalized["target_node_id"],
                relation_type=normalized["relation_type"],
                proposal_status=normalized["proposal_status"],
                candidate_type=normalized["candidate_type"],
                why_candidate=normalized["why_candidate"],
                evidence_refs=normalized["evidence_refs"],
                source_refs=normalized["source_refs"],
                risk_flags=normalized["risk_flags"],
                event_ids=normalized["event_ids"],
                session_ids=normalized["session_ids"],
                turn_ids=normalized["turn_ids"],
                needs_human_review=normalized["needs_human_review"],
                model=model,
                temperature=temperature,
                llm_status=llm_status,
                prompt_version=str(parsed.get("prompt_version") or PROMPT_VERSION).strip() or PROMPT_VERSION,
                candidate_id=normalized["candidate_id"],
            )
        )
    return out, schema_rejected, evidence_rejected


def graph_candidate_row_from_proposal(proposal_row: dict, turn_map: dict[str, dict], package_by_id: dict[str, dict]) -> dict | None:
    if proposal_row["proposal_status"] != "proposed":
        return None
    source_refs = unique_strs(json.loads(proposal_row["source_refs_json"]))
    evidence_refs = unique_strs(json.loads(proposal_row["evidence_refs_json"]))
    if not source_refs or not evidence_refs:
        return None
    src_turn = turn_map.get(proposal_row["source_node_id"])
    tgt_turn = turn_map.get(proposal_row["target_node_id"])
    package = package_by_id.get(proposal_row["package_id"])
    if not src_turn or not tgt_turn or not package:
        return None
    max_signal_score = 0.0
    for score in package.get("signal_scores", {}).values():
        max_signal_score = max(max_signal_score, float(score or 0.0))
    candidate_id = proposal_row["candidate_id"] or stable_id(
        "grcand", proposal_row["source_node_id"], proposal_row["target_node_id"], proposal_row["proposed_relation_type"]
    )
    return {
        "candidate_id": candidate_id,
        "source_node_id": proposal_row["source_node_id"],
        "target_node_id": proposal_row["target_node_id"],
        "source_session_id": src_turn["session_id"],
        "source_turn_id": src_turn["turn_id"],
        "target_session_id": tgt_turn["session_id"],
        "target_turn_id": tgt_turn["turn_id"],
        "similarity": round(max_signal_score, 4),
        "candidate_reason": (
            f"llm_proposal:{proposal_row['proposed_relation_type']}|"
            f"signals={','.join(package.get('coarse_recall_signals') or [])}"
        ),
        "candidate_type": GRAPH_CANDIDATE_TYPE_V2,
        "source_refs_json": json.dumps(source_refs, ensure_ascii=False),
        "created_at": _now_iso(),
    }


def write_proposals(rows: list[dict], sqlite_db: Path) -> None:
    sqlite_db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(sqlite_db)
    try:
        con.executescript(PROPOSAL_SCHEMA_SQL)
        payload = [
            (
                row["proposal_id"],
                row["candidate_id"],
                row["package_id"],
                row["source_node_id"],
                row["target_node_id"],
                row["proposed_relation_type"],
                row["proposal_status"],
                row["candidate_type"],
                row["why_candidate"],
                row["evidence_refs_json"],
                row["source_refs_json"],
                row["risk_flags_json"],
                row["event_ids_json"],
                row["session_ids_json"],
                row["turn_ids_json"],
                row["needs_human_review"],
                row["model"],
                row["prompt_version"],
                row["temperature"],
                row["llm_status"],
                row["created_at"],
            )
            for row in rows
        ]
        con.executemany(
            "INSERT OR REPLACE INTO graph_relation_candidate_proposals "
            "(proposal_id, candidate_id, package_id, source_node_id, target_node_id, proposed_relation_type, "
            "proposal_status, candidate_type, why_candidate, evidence_refs_json, source_refs_json, risk_flags_json, "
            "event_ids_json, session_ids_json, turn_ids_json, needs_human_review, model, prompt_version, temperature, "
            "llm_status, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            payload,
        )
        con.commit()
    finally:
        con.close()


def write_graph_candidates(rows: list[dict], sqlite_db: Path) -> None:
    if not rows:
        return
    con = sqlite3.connect(sqlite_db)
    try:
        con.executescript(base.SCHEMA_SQL)
        payload = [
            (
                row["candidate_id"],
                row["source_node_id"],
                row["target_node_id"],
                row["source_session_id"],
                row["source_turn_id"],
                row["target_session_id"],
                row["target_turn_id"],
                row["similarity"],
                row["candidate_reason"],
                row["candidate_type"],
                row["source_refs_json"],
                row["created_at"],
            )
            for row in rows
        ]
        con.executemany(
            "INSERT OR REPLACE INTO graph_relation_candidates "
            "(candidate_id, source_node_id, target_node_id, source_session_id, source_turn_id, target_session_id, "
            "target_turn_id, similarity, candidate_reason, candidate_type, source_refs_json, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            payload,
        )
        con.commit()
    finally:
        con.close()


def build_report(
    *,
    packages: list[dict],
    proposal_rows: list[dict],
    schema_rejected: int,
    evidence_rejected: int,
    written_candidates: int,
    llm_status_counts: dict[str, int],
    limit: int,
    top_k: int,
    min_similarity: float,
    vector_preflight: dict,
) -> dict:
    signals: dict[str, int] = {}
    for package in packages:
        for signal in package.get("coarse_recall_signals", []):
            signals[signal] = signals.get(signal, 0) + 1
    proposal_status: dict[str, int] = {}
    for row in proposal_rows:
        proposal_status[row["proposal_status"]] = proposal_status.get(row["proposal_status"], 0) + 1
    return {
        "prompt_version": PROMPT_VERSION,
        "limit": limit,
        "top_k": top_k,
        "min_similarity": min_similarity,
        "coarse_packages": len(packages),
        "coarse_signals": signals,
        "proposal_rows": len(proposal_rows),
        "proposal_status_counts": proposal_status,
        "llm_proposed": proposal_status.get("proposed", 0),
        "schema_rejected": schema_rejected,
        "evidence_rejected": evidence_rejected,
        "written_candidates": written_candidates,
        "llm_status": llm_status_counts,
        "vector_preflight": vector_preflight,
        "preview_packages": [
            {
                "package_id": package["package_id"],
                "source_node_id": package["source_node_id"],
                "target_node_id": package["target_node_id"],
                "signals": package["coarse_recall_signals"],
            }
            for package in packages[:10]
        ],
        "preview_proposals": [
            {
                "proposal_id": row["proposal_id"],
                "package_id": row["package_id"],
                "status": row["proposal_status"],
                "relation_type": row["proposed_relation_type"],
                "llm_status": row["llm_status"],
            }
            for row in proposal_rows[:10]
        ],
    }


def render_report_markdown(report: dict) -> str:
    lines = [
        "# Graph Relation Candidate Proposals Report",
        "",
        f"- prompt_version: `{report['prompt_version']}`",
        f"- coarse_packages: **{report['coarse_packages']}**",
        f"- llm_proposed: **{report['llm_proposed']}**",
        f"- schema_rejected: **{report['schema_rejected']}**",
        f"- evidence_rejected: **{report['evidence_rejected']}**",
        f"- written_candidates: **{report['written_candidates']}**",
        "",
        "## LLM Status",
        "",
    ]
    for key, value in sorted(report["llm_status"].items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Coarse Signals", ""])
    for key, value in sorted(report["coarse_signals"].items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Proposal Status", ""])
    for key, value in sorted(report["proposal_status_counts"].items()):
        lines.append(f"- `{key}`: {value}")
    return "\n".join(lines) + "\n"


def run_pipeline(
    *,
    dry_run: bool,
    write: bool,
    limit: int,
    top_k: int,
    min_similarity: float,
    model: str,
    temperature: float,
    sqlite_db: Path = base.SQLITE_DB,
) -> dict:
    turn_map, order = load_turn_index()
    vector_preflight = base.preflight_vector_sync(turn_map)
    embedded_rows = base.load_embeddings(limit=limit)
    if limit > 0:
        allowed = {row["node_id"] for row in embedded_rows}
        turn_map = {node_id: turn for node_id, turn in turn_map.items() if node_id in allowed}
        order = [node_id for node_id in order if node_id in allowed]

    coarse_rows = []
    coarse_rows.extend(build_vector_topk_packages(turn_map, embedded_rows, top_k, min_similarity))
    coarse_rows.extend(build_same_session_adjacent_packages(turn_map, order))
    packages = merge_coarse_packages(turn_map, coarse_rows)
    package_by_id = {package["package_id"]: package for package in packages}

    main_prompt, schema_text = load_prompt_assets()
    llm_status, has_live_llm = detect_llm_status()
    llm_status_counts: dict[str, int] = {}
    proposal_rows: list[dict] = []
    schema_rejected = 0
    evidence_rejected = 0
    client = None
    if has_live_llm:
        try:
            client = llm_mod.make_llm_client()
        except SystemExit:
            has_live_llm = False
            llm_status = "blocked:no_live_llm"
        except Exception:
            has_live_llm = False
            llm_status = "blocked:no_live_llm"

    for idx, package in enumerate(packages, 1):
        current_llm_status = llm_status
        if not has_live_llm or client is None:
            row = blocked_row_for_package(
                package,
                current_llm_status,
                model,
                temperature,
                "无 live LLM/API key，coarse recall package 仅记录审计，不生成语义候选。",
            )
            proposal_rows.append(row)
            llm_status_counts[current_llm_status] = llm_status_counts.get(current_llm_status, 0) + 1
            continue
        try:
            raw = llm_mod._chat_with_retry(
                client,
                model,
                messages=build_llm_messages(package, main_prompt, schema_text),
                temperature=temperature,
            )
            parsed = extract_json(raw)
            rows, schema_count, evidence_count = normalize_llm_response(
                parsed, package, current_llm_status, model, temperature
            )
            schema_rejected += schema_count
            evidence_rejected += evidence_count
            proposal_rows.extend(rows)
            llm_status_counts[current_llm_status] = llm_status_counts.get(current_llm_status, 0) + 1
        except Exception as exc:
            current_llm_status = "blocked:no_live_llm"
            proposal_rows.append(
                blocked_row_for_package(
                    package,
                    current_llm_status,
                    model,
                    temperature,
                    f"LLM proposal 调用失败: {type(exc).__name__}: {str(exc)[:120]}",
                )
            )
            llm_status_counts[current_llm_status] = llm_status_counts.get(current_llm_status, 0) + 1
        if idx <= 5:
            print(
                f"[{idx}/{len(packages)}] package={package['package_id']} "
                f"signals={','.join(package['coarse_recall_signals'])} llm_status={current_llm_status}",
                flush=True,
            )

    writable_rows = []
    for row in proposal_rows:
        graph_row = graph_candidate_row_from_proposal(row, turn_map, package_by_id)
        if graph_row:
            writable_rows.append(graph_row)

    if write:
        write_proposals(proposal_rows, sqlite_db)
        write_graph_candidates(writable_rows, sqlite_db)

    report = build_report(
        packages=packages,
        proposal_rows=proposal_rows,
        schema_rejected=schema_rejected,
        evidence_rejected=evidence_rejected,
        written_candidates=len(writable_rows),
        llm_status_counts=llm_status_counts or {llm_status: len(packages)},
        limit=limit,
        top_k=top_k,
        min_similarity=min_similarity,
        vector_preflight=vector_preflight,
    )
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_MD.write_text(render_report_markdown(report), encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Wave 9.2 LLM-assisted graph relation candidate generation")
    parser.add_argument("--dry-run", action="store_true", help="只生成 package/proposal/report，不写 SQLite")
    parser.add_argument("--write", action="store_true", help="写 proposal 审计表，并在 gate 通过时写入 graph_relation_candidates")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="只处理前 N 个 turn（0=全部）")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="vector recall 的每 turn top-k")
    parser.add_argument(
        "--min-similarity",
        type=float,
        default=base.MIN_SEMANTIC_SCORE,
        help="vector_topk 的最小相似度阈值",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    args = parser.parse_args(argv)
    if args.dry_run and args.write:
        print("[error] --dry-run 与 --write 互斥", file=sys.stderr)
        return 2
    if not args.dry_run and not args.write:
        print("[error] 必须指定 --dry-run 或 --write", file=sys.stderr)
        return 2

    report = run_pipeline(
        dry_run=args.dry_run,
        write=args.write,
        limit=args.limit,
        top_k=args.top_k,
        min_similarity=args.min_similarity,
        model=args.model,
        temperature=args.temperature,
    )
    print("# Graph Relation Candidate Proposals")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
