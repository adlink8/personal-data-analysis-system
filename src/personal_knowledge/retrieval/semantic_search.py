"""Auto-split from unified_search.py — see facade for the public API."""
from __future__ import annotations

import json
import os
import re
import sqlite3
import csv
import io
import time
from pathlib import Path
from typing import Any, Optional

import sys  # noqa: E402
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
_THIS_DIR = _SCRIPTS_DIR

# search_vectors is used by semantic_search only, but harmless elsewhere.
from personal_knowledge.retrieval.search_vectors import search as _semantic_search, search_all as _semantic_search_all  # noqa: E402
import personal_knowledge.retrieval._constants as _C  # noqa: E402
from personal_knowledge.retrieval._constants import (  # noqa: E402
    DEFAULT_MEMORY_GRAPH_LIMIT, MAX_MEMORY_GRAPH_LIMIT,
    DEFAULT_RELATION_REVIEW_LIMIT, MAX_RELATION_REVIEW_LIMIT,
    RELATION_REVIEW_STATUSES, DEFAULT_DATA_LIMIT, MAX_DATA_LIMIT, MAX_EXPORT_LIMIT,
    DEFAULT_EVENT_FIELDS, EVENT_FIELD_SQL, AGGREGATE_GROUP_SQL,
    _KU_SLOTS, _RAW_SLOTS_DEFAULT, _KU_PORT,
    FALLBACK_POLICIES, DEFAULT_FALLBACK_POLICY,
    CONVERSATION_TURNS_COLLECTION, CANONICAL_MESSAGES_COLLECTION,
    _NON_DIALOGUE_PREFERRED_SOURCE,
)

from personal_knowledge.retrieval._db_utils import (  # noqa: E402
    _bounded_int, _split_csv, _normalize_event_fields, _event_from_clause, _event_filter_sql, _memory_layer_ready, _table_exists, _parse_metadata, _parse_json_list, _memory_row_to_dict,
)
from personal_knowledge.retrieval.google_assertions import get_google_structure_status  # noqa: E402
from personal_knowledge.retrieval.merge_cluster import _merge_layer_ready, _dedup_event_ids  # noqa: E402
from personal_knowledge.retrieval.serving import ServingSnapshotResolver, member_version  # noqa: E402

def search_semantic(
    query: str,
    top_k: int = 5,
    source: Optional[str] = None,
    dedup: bool = False,
    include_turns: bool = True,
) -> list[dict]:
    """语义检索:自然语言召回用户历史事件。

    Wave 7 起默认跨 collection 检索:personal_events(单条事件) +
    conversation_turns(turn 叙述,含因果链)。适合"用户做过什么/怎么做的"类查询。

    query: 自然语言(如"PPT 排版怎么做")
    top_k: 返回条数
    source: 过滤数据源("Google"/"GPT"/"Agent"),None=全源
    dedup:  True=按合并层折叠重复命中(L1 真重复/L2 同主题只留代表),
            返回结果里多一个 merged_count 字段表示该代表背后折叠了几条。
            折叠后实际条数可能少于 top_k。
            注意:dedup 只作用于 personal_events(conversation_turns 不参与合并层折叠)。
    include_turns: True=同时搜 conversation_turns turn 叙述(Wave 7 默认);
                   False=只搜 personal_events(旧行为)。collection 不存在时自动降级。
    返回: list[dict],按相似度降序,字段:
        event_id, source, category_v2, event_type, service,
        event_time, month, title, content, score[, merged_count],
        collection, retrieval_unit, rank_reason
        turn 叙述额外带: session_id, turn_id, turn_no, main_topic
    """
    if not query or not query.strip():
        return []
    # dedup 模式多召回一些,折叠后仍有足够结果
    fetch_k = top_k * 3 if dedup else top_k
    # Wave 7: 跨 collection 检索(include_turns=True 时合并 turn 叙述)
    if include_turns:
        results = _semantic_search_all(query, top_k=fetch_k, source=source)
    else:
        results = _semantic_search(query, top_k=fetch_k, source=source)
    if not dedup or not results:
        return results[:top_k]
    if not _merge_layer_ready():
        return results[:top_k]

    # 按合并层折叠:同簇只留首个(分数最高)命中,附 merged_count
    kept_ids, dup_map = _dedup_event_ids([r["event_id"] for r in results])
    rep_first_idx: dict[str, int] = {}
    for i, r in enumerate(results):
        rep = dup_map.get(r["event_id"], r["event_id"])
        if rep not in rep_first_idx:
            rep_first_idx[rep] = i

    # 统计每个代表折叠了多少条命中
    con = sqlite3.connect(_C.UNIFIED_DB)
    rep_counts: dict[str, int] = {}
    for rep in rep_first_idx:
        try:
            n = con.execute(
                "SELECT COUNT(*) FROM merge_members WHERE cluster_id IN "
                "(SELECT cluster_id FROM merge_members WHERE event_id=?)",
                (rep,),
            ).fetchone()[0]
        except sqlite3.OperationalError:
            n = 0
        # 独立事件(不在任何簇)代表它自己,计 1
        rep_counts[rep] = n if n > 0 else 1
    con.close()

    out = []
    for rep, idx in sorted(rep_first_idx.items(), key=lambda x: x[1]):
        r = dict(results[idx])
        r["merged_count"] = rep_counts.get(rep, 1)
        out.append(r)
        if len(out) >= top_k:
            break
    return out


# --- Knowledge unit hybrid retrieval (Phase 14 Wave 4 / Phase 15 Wave 2) ---

# 混合策略：知识层贡献结构化语义结果；raw 层可配置:
#   legacy  — KU 后补全量 personal_events（旧行为）
#   layered — KU → canonical message 片段/词检索(dialogue) → conversation_turns
#             → personal_events(Google) → 可选 legacy_pad
# Phase 15 W4: message 级 dialogue 补洞（frozen gold snippet R@8=1.0 on canonical）。
_KU_SLOTS = 1
_RAW_SLOTS_DEFAULT = 4
_KU_PORT = 8001

FALLBACK_POLICIES = ("legacy", "layered")
DEFAULT_FALLBACK_POLICY = "layered"
CONVERSATION_TURNS_COLLECTION = "conversation_turns"
CANONICAL_MESSAGES_COLLECTION = "canonical_messages"
_NON_DIALOGUE_PREFERRED_SOURCE = "Google"


def _resolve_fallback_policy(fallback_policy: str | None = None) -> str:
    """Resolve hybrid fallback policy from arg or env PERSONAL_DATA_FALLBACK_POLICY."""
    if fallback_policy is None:
        raw = os.environ.get("PERSONAL_DATA_FALLBACK_POLICY", DEFAULT_FALLBACK_POLICY)
    else:
        raw = fallback_policy
    policy = (raw or DEFAULT_FALLBACK_POLICY).strip().lower()
    if policy not in FALLBACK_POLICIES:
        return DEFAULT_FALLBACK_POLICY
    return policy


def _resolve_allow_legacy_pad(allow_legacy_pad: bool | None = None) -> bool:
    """Whether layered mode may pad with non-Google personal_events when still short.

    Default True (transition safety; see retrieval-ssot.md § legacy_pad rollout).
    Env: PERSONAL_DATA_ALLOW_LEGACY_PAD=0|1|true|false.
    """
    if allow_legacy_pad is not None:
        return bool(allow_legacy_pad)
    env = os.environ.get("PERSONAL_DATA_ALLOW_LEGACY_PAD")
    if env is None or not str(env).strip():
        return True
    return str(env).strip().lower() in ("1", "true", "yes", "on")


def _empty_layer_telemetry(name: str) -> dict[str, Any]:
    return {"name": name, "attempted": False, "hits": 0, "latency_ms": 0.0}


def _finalize_search_telemetry(
    layers: list[dict[str, Any]],
    *,
    pad_allowed: bool,
    t0: float,
) -> dict[str, Any]:
    """Build response telemetry: per-layer hit/attempt/latency + pad usage."""
    first = None
    pad_used = False
    for layer in layers:
        if first is None and int(layer.get("hits") or 0) > 0:
            first = layer.get("name")
        if layer.get("name") == "legacy_pad" and int(layer.get("hits") or 0) > 0:
            pad_used = True
    return {
        "layers": layers,
        "first_contributing_layer": first,
        "pad_allowed": bool(pad_allowed),
        "pad_used": pad_used,
        "total_latency_ms": round((time.perf_counter() - t0) * 1000, 2),
    }


def _raw_event_item(
    ev: dict,
    *,
    retrieval_unit: str,
    collection: str,
    rank_reason: str,
) -> dict:
    """Normalize a vector search hit into the hybrid result schema."""
    title = ev.get("title") or ev.get("main_topic") or ""
    return {
        "unit_id": ev.get("event_id", ""),
        "subject": str(title)[:80],
        "answer": (ev.get("content") or "")[:300],
        "score": ev.get("score", 0),
        "lifecycle": "current",
        "confidence": 0,
        "source_message_ref": "",
        "collection": collection,
        "retrieval_unit": retrieval_unit,
        "rank_reason": rank_reason,
        "event_id": ev.get("event_id", ""),
        "source": ev.get("source", ""),
        "event_time": ev.get("event_time", ""),
    }


def _search_personal_events_filtered(
    query: str,
    top_k: int,
    source: Optional[str],
) -> list[dict]:
    """Query personal_events; prefer server-side where, else client-side source filter."""
    if top_k <= 0:
        return []
    try:
        return _semantic_search(query, top_k=top_k, source=source)
    except Exception:
        pass
    # where may be unsupported / broken — fetch wider and filter client-side
    try:
        events = _semantic_search(query, top_k=max(top_k * 3, top_k), source=None)
    except Exception:
        return []
    if not source:
        return events[:top_k]
    filtered = [e for e in events if (e.get("source") or "") == source]
    return filtered[:top_k] if filtered else []


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _query_tokens(query: str, max_toks: int = 4) -> list[str]:
    """Extract distinctive CJK/latin tokens for AND-style LIKE search."""
    toks = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z_][A-Za-z0-9_\-]{3,}", query or "")
    # longer first (more distinctive for code / paths)
    ordered = sorted(set(toks), key=len, reverse=True)
    return ordered[:max_toks]


def _search_dialogue_canonical_messages(
    query: str,
    top_k: int = 5,
    db_path: Path | None = None,
) -> list[dict]:
    """Message-level dialogue fallback on canonical_messages (read-only).

    Strategy (Phase 15 W4):
    1) For long pastes: sliding snippet LIKE (handles code-literal gold)
    2) Else: multi-token AND LIKE on distinctive terms

    Returns hybrid-schema items with unit_id = canonical_message_id (cm|…).
    """
    if top_k <= 0 or not (query or "").strip():
        return []
    path = Path(db_path) if db_path else _C.AGENT_CONVERSATIONS_DB
    if not path.exists():
        return []

    q = query.strip()
    rows: list[tuple] = []
    try:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            con.execute("PRAGMA query_only=ON")
        except Exception:
            pass
        # Prefer non-system messages when column exists
        try:
            cols = {r[1] for r in con.execute("PRAGMA table_info(canonical_messages)")}
        except Exception:
            cols = set()
        if "canonical_message_id" not in cols or "content" not in cols:
            con.close()
            return []

        base_where = "1=1"
        if "is_system" in cols:
            base_where += " AND COALESCE(is_system,0)=0"

        if len(q) >= 40:
            for start in (0, 20, 50, 100, min(200, max(0, len(q) - 40))):
                snip = q[start : start + 40]
                if len(snip) < 20:
                    continue
                esc = _like_escape(snip)
                sql = (
                    "SELECT canonical_message_id, role, substr(content,1,300), "
                    "COALESCE(timestamp,''), COALESCE(source,'') "
                    f"FROM canonical_messages WHERE {base_where} "
                    "AND content LIKE ? ESCAPE '\\' LIMIT ?"
                )
                try:
                    found = con.execute(sql, (f"%{esc}%", top_k * 2)).fetchall()
                except Exception:
                    found = []
                if found:
                    rows = found
                    break

        if not rows:
            toks = _query_tokens(q, max_toks=4)
            if toks:
                sql = (
                    "SELECT canonical_message_id, role, substr(content,1,300), "
                    "COALESCE(timestamp,''), COALESCE(source,'') "
                    f"FROM canonical_messages WHERE {base_where}"
                )
                params: list[Any] = []
                for t in toks:
                    sql += " AND content LIKE ? ESCAPE '\\'"
                    params.append(f"%{_like_escape(t)}%")
                sql += " LIMIT ?"
                params.append(top_k * 2)
                try:
                    rows = con.execute(sql, params).fetchall()
                except Exception:
                    rows = []
        con.close()
    except Exception:
        return []

    out: list[dict] = []
    seen: set[str] = set()
    for mid, role, content, ts, src in rows:
        mid = str(mid or "")
        if not mid or mid in seen:
            continue
        seen.add(mid)
        # Prefer higher score for earlier ranks; user messages slight boost
        base = 0.92 - 0.02 * len(out)
        if (role or "") == "user":
            base = min(0.99, base + 0.03)
        out.append(
            {
                "unit_id": mid,
                "subject": f"dialogue:{(role or 'msg')}"[:80],
                "answer": (content or "")[:300],
                "score": round(base, 4),
                "lifecycle": "current",
                "confidence": 0,
                "source_message_ref": mid,
                "collection": CANONICAL_MESSAGES_COLLECTION,
                "retrieval_unit": "dialogue",
                "rank_reason": "dialogue_fallback canonical_messages",
                "event_id": mid,
                "source": src or "Agent",
                "event_time": ts or "",
                "role": role or "",
            }
        )
        if len(out) >= top_k:
            break
    return out


def _read_knowledge_active_collection() -> str:
    """Resolve active knowledge index from SQLite authority, then legacy pointer."""
    pointer = _C.DB_DIR / "knowledge_index_active.txt"
    state = ServingSnapshotResolver(_C.UNIFIED_DB, pointer).resolve()
    return str((state.member("knowledge_retrieval") or {}).get("location_ref") or "")


def get_knowledge_status(*, probe_chroma: bool = True) -> dict:
    """知识索引只读状态（CLI / REST / MCP 共用）。

    返回 active collection、pointer、版本行、fallback_policy/ssot 与（可选）Chroma 实际条数。
    不暴露 promote/rollback；运维脚本仍走 knowledge/* 入口。
    """
    from personal_knowledge.core.project_paths import DB_DIR  # noqa: E402

    pointer = _C.DB_DIR / "knowledge_index_active.txt"
    active = _read_knowledge_active_collection()
    serving = ServingSnapshotResolver(_C.UNIFIED_DB, pointer).resolve()
    policy = _resolve_fallback_policy(None)
    if policy == "layered":
        route_policy = "knowledge-first + layered fallback (dialogue→non_dialogue_raw)"
    else:
        route_policy = "knowledge-first + raw fallback"
    out: dict[str, Any] = {
        "available": bool(active),
        "active_collection": active or None,
        "serving_snapshot_id": serving.snapshot_id,
        "snapshot_hash": serving.manifest_hash,
        "snapshot_drift": serving.drift,
        "pointer_path": str(pointer),
        "pointer_exists": pointer.exists(),
        "search_backend": "search_knowledge_units",
        "route_policy": route_policy,
        # Phase 15: 三层 SSOT 与 fallback 策略（见 docs/architecture/retrieval-ssot.md）
        # fallback_policy: legacy = 全量 personal_events 补洞；layered = KU→dialogue→non_dialogue
        "ssot": {
            "dialogue": "agentsview_canonical",
            "knowledge": "canonical_knowledge_units",
            "non_dialogue_raw": "personal_events",
            "google_structure": "google_data.normalized_events+light_assertions",
        },
        "fallback_policy": policy,
        "allow_legacy_pad": _resolve_allow_legacy_pad(None),
        "semantic_routes": {
            "cli": "unified_search.py semantic",
            "rest": "POST /search/semantic",
            "mcp": "search_semantic",
        },
        "unit_count": None,
        "db_unit_count": None,
        "version": {},
        "chroma_available": False,
        "google_structure": get_google_structure_status(),
    }

    if active and _C.UNIFIED_DB.exists():
        try:
            con = sqlite3.connect(f"file:{_C.UNIFIED_DB.as_posix()}?mode=ro", uri=True)
            row = con.execute(
                "SELECT version_id, build_id, collection_name, unit_count, status, "
                "created_at, activated_at, checksum "
                "FROM knowledge_index_versions WHERE collection_name=? "
                "ORDER BY created_at DESC LIMIT 1",
                (active,),
            ).fetchone()
            if row:
                out["version"] = {
                    "version_id": row[0],
                    "build_id": row[1],
                    "collection_name": row[2],
                    "unit_count": row[3],
                    "status": row[4],
                    "created_at": row[5],
                    "activated_at": row[6],
                    "checksum": (row[7] or "")[:16] + ("…" if row[7] and len(row[7]) > 16 else ""),
                }
                out["db_unit_count"] = row[3]
                if out["unit_count"] is None:
                    out["unit_count"] = row[3]
            # canonical current count (may span multiple runs for merged index)
            try:
                cur = con.execute(
                    "SELECT COUNT(*) FROM canonical_knowledge_units WHERE status='current'"
                ).fetchone()
                out["canonical_current_count"] = cur[0] if cur else None
            except sqlite3.Error:
                out["canonical_current_count"] = None
            con.close()
        except Exception as e:
            out["db_error"] = str(e)[:120]

    if probe_chroma and active:
        try:
            from personal_knowledge.core.chroma_client import ChromaClient  # noqa: E402

            client = ChromaClient(port=_KU_PORT)
            coll = client.get_or_create_collection(active)
            count = coll.count()
            out["unit_count"] = count
            out["chroma_available"] = True
            out["chroma_port"] = _KU_PORT
        except Exception as e:
            out["chroma_error"] = str(e)[:120]

    return out


def search_knowledge_units(
    query: str,
    top_k: int = 5,
    source: Optional[str] = None,
    include_evidence: bool = False,
    collection_override: Optional[str] = None,
    fallback_policy: str | None = None,
    allow_legacy_pad: bool | None = None,
) -> dict:
    """知识单元混合检索 backend。

    knowledge-first + fallback：先查 active knowledge unit collection（结构化 Q&A），
    再按 fallback_policy 补洞:
      - legacy:  全量 personal_events（旧行为）
      - layered: conversation_turns(dialogue) → personal_events(Google) → 可选 legacy_pad

    返回 route/versions/results/telemetry，CLI/REST/MCP 共用此唯一 backend。

    query: 自然语言查询
    top_k: 返回条数（默认 5，有界 [1,20]）
    source: 过滤 raw 事件数据源（不影响知识层；layered 下 non_dialogue 默认 Google）
    include_evidence: True=附带 evidence quote（默认只给 refs）
    collection_override: 指定 knowledge collection（canary 用，不改变 active pointer）
    fallback_policy: "legacy" | "layered"；None=读 env PERSONAL_DATA_FALLBACK_POLICY，默认 layered
    allow_legacy_pad: layered 仍不足时是否用非 Google personal_events 填充；默认 True

    返回: {
        "route": "knowledge" | "fallback_raw" | "abstain",
        "reason": str (fallback/abstain 时),
        "fallback_policy": "legacy" | "layered",
        "allow_legacy_pad": bool,
        "telemetry": {layers, first_contributing_layer, pad_allowed, pad_used, total_latency_ms},
        "results": [{"rank","unit_id","subject","answer","score","lifecycle",
                      "confidence","source_message_ref","collection","retrieval_unit"}, ...],
        "versions": {"index_version","build_id","canonical_build_id","unit_count","status"},
    }
    """
    top_k = max(1, min(20, top_k))
    policy = _resolve_fallback_policy(fallback_policy)
    pad_allowed = _resolve_allow_legacy_pad(allow_legacy_pad)
    t0 = time.perf_counter()
    layers: list[dict[str, Any]] = [
        _empty_layer_telemetry("knowledge_unit"),
        _empty_layer_telemetry("canonical_messages"),
        _empty_layer_telemetry("conversation_turns"),
        _empty_layer_telemetry("non_dialogue_raw"),
        _empty_layer_telemetry("legacy_pad"),
        _empty_layer_telemetry("legacy_personal_events"),
    ]
    layer_by_name = {x["name"]: x for x in layers}
    pointer = _C.DB_DIR / "knowledge_index_active.txt"
    serving = ServingSnapshotResolver(_C.UNIFIED_DB, pointer).resolve()
    # Resolve through the public compatibility hook as well. In production it
    # reads the same SQLite authority; tests and embedded callers can inject an
    # isolated authority without inheriting this machine's live snapshot.
    resolved_active = _read_knowledge_active_collection()
    snapshot_collection = str((serving.member("knowledge_retrieval") or {}).get("location_ref") or "")
    snapshot_enforced = bool(
        serving.snapshot_id
        and collection_override is None
        and resolved_active
        and resolved_active == snapshot_collection
    )
    role_by_layer = {
        "knowledge_unit": "knowledge_retrieval",
        "canonical_messages": "canonical_message",
        "conversation_turns": "turn_retrieval",
        "non_dialogue_raw": "google_normalized",
    }
    for layer_name, role in role_by_layer.items():
        layer_by_name[layer_name]["version"] = member_version(serving.member(role))

    def _role_allowed(role: str) -> bool:
        return not snapshot_enforced or serving.member(role) is not None

    def _pack(
        *,
        route: str,
        results: list[dict],
        versions: dict | None = None,
        reason: str | None = None,
        ku_collection: str | None = None,
    ) -> dict:
        out: dict[str, Any] = {
            "route": route,
            "results": results,
            "versions": versions or {},
            "fallback_policy": policy,
            "allow_legacy_pad": pad_allowed,
            "telemetry": _finalize_search_telemetry(
                layers, pad_allowed=pad_allowed, t0=t0
            ),
            "serving_snapshot_id": serving.snapshot_id,
            "snapshot_hash": serving.manifest_hash,
            "snapshot_drift": serving.drift,
            "snapshot_consistency": (
                "override_unbound" if collection_override else
                "enforced" if snapshot_enforced else "legacy"
            ),
        }
        if reason is not None:
            out["reason"] = reason
        if ku_collection is not None:
            out["collection"] = ku_collection
        return out

    if not query or not query.strip():
        return _pack(route="abstain", results=[], reason="empty query")

    # 延迟 import 避免影响无向量库的环境
    try:
        from personal_knowledge.core.chroma_client import ChromaClient, ChromaError  # noqa: E402
        import personal_knowledge.core.local_embed as local_embed  # noqa: E402
    except Exception as e:
        return _pack(
            route="fallback_raw",
            results=[],
            reason=f"vector infra unavailable: {e}",
        )

    route = "knowledge"
    versions: dict = {}

    # 解析 knowledge collection
    if collection_override:
        ku_collection = collection_override
    elif snapshot_enforced:
        ku_collection = snapshot_collection
    else:
        # Compatibility hook retained for tests and pre-snapshot installations.
        ku_collection = resolved_active

    # embedding（一次 embed，两路复用）
    embedding = local_embed.embed(query)
    if embedding is None:
        return _pack(route="fallback_raw", results=[], reason="embedding failed")

    client = ChromaClient(port=_KU_PORT)

    # --- Phase 1: 知识层检索（top-KU_SLOTS） ---
    ku_results: list[dict] = []
    if ku_collection:
        layer = layer_by_name["knowledge_unit"]
        layer["attempted"] = True
        t_layer = time.perf_counter()
        try:
            cols = client.list_collections()
            col_names = {c if isinstance(c, str) else c.get("name", "") for c in cols}
            if ku_collection in col_names:
                ku_coll = client.get_or_create_collection(ku_collection)
                ku_fetch = max(top_k, _KU_SLOTS)
                kr = ku_coll.query(
                    query_embeddings=[embedding], n_results=ku_fetch,
                    include=["metadatas", "documents", "distances"],
                )
                ku_ids = kr.get("ids", [[]])[0] if kr.get("ids") else []
                ku_docs = kr.get("documents", [[]])[0] if kr.get("documents") else []
                ku_dists = kr.get("distances", [[]])[0] if kr.get("distances") else []
                ku_metas = kr.get("metadatas", [[]])[0] if kr.get("metadatas") else []
                for uid, doc, dist, meta in zip(ku_ids, ku_docs, ku_dists, ku_metas):
                    lc = meta.get("lifecycle", "current") if isinstance(meta, dict) else "current"
                    if lc not in ("current",):
                        continue
                    item = {
                        "unit_id": uid,
                        "subject": meta.get("subject", "") if isinstance(meta, dict) else "",
                        "answer": doc[:300] if doc else "",
                        "score": round(1 - dist, 4) if isinstance(dist, (int, float)) else 0,
                        "lifecycle": lc,
                        "confidence": meta.get("confidence", 0) if isinstance(meta, dict) else 0,
                        "source_message_ref": meta.get("source_message_ref", "") if isinstance(meta, dict) else "",
                        "collection": ku_collection,
                        "retrieval_unit": "knowledge_unit",
                        "rank_reason": "knowledge unit semantic match",
                    }
                    if include_evidence:
                        item["evidence_quote"] = ""
                    ku_results.append(item)
                    if len(ku_results) >= _KU_SLOTS:
                        break

                # 读版本信息
                import sqlite3 as _sql  # noqa: E402
                try:
                    con = _sql.connect(f"file:{_C.UNIFIED_DB.as_posix()}?mode=ro", uri=True)
                    row = con.execute(
                        "SELECT version_id, build_id, canonical_build_id, unit_count, status "
                        "FROM knowledge_index_versions WHERE collection_name=? ORDER BY created_at DESC LIMIT 1",
                        (ku_collection,),
                    ).fetchone()
                    if row:
                        versions = {
                            "index_version": row[0], "build_id": row[1],
                            "canonical_build_id": row[2], "unit_count": row[3], "status": row[4],
                        }
                    con.close()
                except Exception:
                    pass
            else:
                route = "fallback_raw"
        except ChromaError:
            route = "fallback_raw"
        finally:
            layer["hits"] = len(ku_results)
            layer["latency_ms"] = round((time.perf_counter() - t_layer) * 1000, 2)
    else:
        route = "fallback_raw"

    seen_ids: set[str] = {
        str(x.get("unit_id") or "") for x in ku_results if x.get("unit_id")
    }
    fallback_results: list[dict] = []

    def _remaining() -> int:
        return top_k - len(ku_results) - len(fallback_results)

    def _append_unique(item: dict) -> bool:
        uid = str(item.get("unit_id") or item.get("event_id") or "")
        if uid and uid in seen_ids:
            return False
        if uid:
            seen_ids.add(uid)
        fallback_results.append(item)
        return True

    if policy == "legacy" and not snapshot_enforced:
        # --- Legacy Phase 2: raw personal_events 检索（补剩余 slot，全源） ---
        raw_target = _remaining()
        layer = layer_by_name["legacy_personal_events"]
        if raw_target > 0:
            layer["attempted"] = True
            t_layer = time.perf_counter()
            n_before = len(fallback_results)
            try:
                raw_fetch = raw_target + 4
                raw_events = _semantic_search(query, top_k=raw_fetch, source=source)
                for ev in raw_events:
                    item = _raw_event_item(
                        ev,
                        retrieval_unit="event",
                        collection="personal_events",
                        rank_reason="raw event semantic match",
                    )
                    if _append_unique(item) and len(fallback_results) >= raw_target:
                        break
                if len(fallback_results) > raw_target:
                    del fallback_results[raw_target:]
            except Exception:
                pass
            finally:
                layer["hits"] = max(0, len(fallback_results) - n_before)
                layer["latency_ms"] = round((time.perf_counter() - t_layer) * 1000, 2)
    else:
        if policy == "legacy" and snapshot_enforced:
            layer_by_name["legacy_personal_events"]["skipped_reason"] = "not_bound_to_serving_snapshot"
        # --- Layered Phase 2a: message-level dialogue (canonical_messages) ---
        need = _remaining()
        layer = layer_by_name["canonical_messages"]
        if need > 0 and not _role_allowed("canonical_message"):
            layer["skipped_reason"] = "snapshot_member_missing:canonical_message"
        if need > 0 and _role_allowed("canonical_message"):
            layer["attempted"] = True
            t_layer = time.perf_counter()
            n_before = len(fallback_results)
            try:
                msg_hits = _search_dialogue_canonical_messages(query, top_k=need + 4)
                for item in msg_hits:
                    _append_unique(item)
                    if _remaining() <= 0:
                        break
            except Exception:
                pass
            finally:
                layer["hits"] = max(0, len(fallback_results) - n_before)
                layer["latency_ms"] = round((time.perf_counter() - t_layer) * 1000, 2)

        # --- Layered Phase 2b: dialogue_fallback via conversation_turns ---
        need = _remaining()
        layer = layer_by_name["conversation_turns"]
        if need > 0 and not _role_allowed("turn_retrieval"):
            layer["skipped_reason"] = "snapshot_member_missing:turn_retrieval"
        if need > 0 and _role_allowed("turn_retrieval"):
            layer["attempted"] = True
            t_layer = time.perf_counter()
            n_before = len(fallback_results)
            try:
                from personal_knowledge.retrieval.search_vectors import search_conversation_turns as _search_turns  # noqa: E402

                turns = _search_turns(query, top_k=need + 4, source=source)
                for ev in turns:
                    item = _raw_event_item(
                        ev,
                        retrieval_unit="dialogue",
                        collection=CONVERSATION_TURNS_COLLECTION,
                        rank_reason="dialogue_fallback conversation_turns",
                    )
                    item["collection"] = CONVERSATION_TURNS_COLLECTION
                    item["retrieval_unit"] = "dialogue"
                    _append_unique(item)
                    if _remaining() <= 0:
                        break
            except Exception:
                # collection missing / chroma error — soft skip
                pass
            finally:
                layer["hits"] = max(0, len(fallback_results) - n_before)
                layer["latency_ms"] = round((time.perf_counter() - t_layer) * 1000, 2)

        # --- Layered Phase 3: non_dialogue_raw (prefer Google personal_events) ---
        need = _remaining()
        layer = layer_by_name["non_dialogue_raw"]
        if need > 0 and not _role_allowed("google_normalized"):
            layer["skipped_reason"] = "snapshot_member_missing:google_normalized"
        if need > 0 and _role_allowed("google_normalized"):
            layer["attempted"] = True
            t_layer = time.perf_counter()
            n_before = len(fallback_results)
            raw_source = source if source else _NON_DIALOGUE_PREFERRED_SOURCE
            try:
                raw_events = _search_personal_events_filtered(
                    query, top_k=need + 4, source=raw_source,
                )
                for ev in raw_events:
                    if not source and (ev.get("source") or "") != _NON_DIALOGUE_PREFERRED_SOURCE:
                        continue
                    item = _raw_event_item(
                        ev,
                        retrieval_unit="event",
                        collection="personal_events",
                        rank_reason="non_dialogue_raw personal_events",
                    )
                    _append_unique(item)
                    if _remaining() <= 0:
                        break
            except Exception:
                pass
            finally:
                layer["hits"] = max(0, len(fallback_results) - n_before)
                layer["latency_ms"] = round((time.perf_counter() - t_layer) * 1000, 2)

        # --- Layered Phase 4: optional legacy pad (non-Google personal_events) ---
        need = _remaining()
        layer = layer_by_name["legacy_pad"]
        if need > 0 and pad_allowed and snapshot_enforced:
            layer["skipped_reason"] = "not_bound_to_serving_snapshot"
        if need > 0 and pad_allowed and not snapshot_enforced:
            layer["attempted"] = True
            t_layer = time.perf_counter()
            n_before = len(fallback_results)
            try:
                pad_events = _search_personal_events_filtered(
                    query, top_k=need + 8, source=source,
                )
                for ev in pad_events:
                    src = ev.get("source") or ""
                    if not source and src == _NON_DIALOGUE_PREFERRED_SOURCE:
                        continue
                    item = _raw_event_item(
                        ev,
                        retrieval_unit="event",
                        collection="personal_events",
                        rank_reason="legacy_pad",
                    )
                    _append_unique(item)
                    if _remaining() <= 0:
                        break
            except Exception:
                pass
            finally:
                layer["hits"] = max(0, len(fallback_results) - n_before)
                layer["latency_ms"] = round((time.perf_counter() - t_layer) * 1000, 2)

    # --- 合并 + 排名 ---
    merged = ku_results + fallback_results
    if not merged:
        return _pack(
            route="abstain",
            results=[],
            versions=versions,
            reason="no results from either source",
            ku_collection=ku_collection or "personal_events",
        )

    # 去 raw fallback 的 reason（有结果就标 knowledge route）
    if route == "fallback_raw" and ku_results:
        route = "knowledge"

    # 编号
    if include_evidence:
        from personal_knowledge.retrieval.evidence import EvidenceResolver  # noqa: E402
        resolver = EvidenceResolver(
            unified_db=_C.UNIFIED_DB,
            conversation_db=_C.AGENT_CONVERSATIONS_DB,
            google_db=_C.GOOGLE_DB,
        )
        for item in merged:
            ref = str(item.get("source_message_ref") or item.get("unit_id") or item.get("event_id") or "")
            if not ref:
                continue
            if item.get("retrieval_unit") == "dialogue" and ref.startswith("cm|"):
                artifact_type = "canonical_message"
                role = "canonical_message"
            elif str(item.get("source") or "").lower() == "google" or ref.startswith("g|"):
                artifact_type = "google_signal"
                role = "google_normalized"
            elif item.get("retrieval_unit") == "dialogue":
                artifact_type = "turn"
                role = "turn_retrieval"
            else:
                artifact_type = "knowledge_unit"
                role = "canonical_knowledge"
            item["evidence"] = resolver.resolve(
                ref,
                artifact_type=artifact_type,
                include_content=True,
                source_version=member_version(serving.member(role)),
            )

    for i, item in enumerate(merged, 1):
        item["rank"] = i

    return _pack(
        route=route,
        results=merged[:top_k],
        versions=versions,
        ku_collection=ku_collection or "personal_events",
    )



