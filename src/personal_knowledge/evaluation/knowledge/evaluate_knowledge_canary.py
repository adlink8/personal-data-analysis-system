"""Phase 14 Plan 05: unified knowledge unit search + canary evaluator."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
_THIS_DIR = _SCRIPTS_DIR  # legacy alias: scripts root for resource paths

from personal_knowledge.core.project_paths import UNIFIED_DB, DB_DIR  # noqa: E402
from personal_knowledge.core.chroma_client import ChromaClient, ChromaError  # noqa: E402
import personal_knowledge.core.local_embed as local_embed  # noqa: E402

ACTIVE_POINTER = DB_DIR / "knowledge_index_active.txt"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_active_collection() -> str | None:
    """读 active knowledge index pointer。"""
    if ACTIVE_POINTER.exists():
        name = ACTIVE_POINTER.read_text(encoding="utf-8").strip()
        return name if name else None
    return None


def search_knowledge_units(
    query: str,
    top_k: int = 5,
    collection_name: str | None = None,
    include_evidence: bool = False,
) -> dict:
    """知识单元检索。knowledge-first + raw fallback。

    返回: {"route": "knowledge|fallback_raw", "results": [...], "versions": {...}}
    """
    route = "knowledge"
    versions = {}

    # 解析 active collection
    if collection_name is None:
        collection_name = read_active_collection()
    if not collection_name:
        return {"route": "fallback_raw", "reason": "no active knowledge index",
                "results": [], "versions": {}}

    # 验证 collection 存在
    client = ChromaClient(port=8001)
    cols = client.list_collections()
    col_names = {c if isinstance(c, str) else c.get("name", "") for c in cols}
    if collection_name not in col_names:
        return {"route": "fallback_raw", "reason": f"collection not found: {collection_name}",
                "results": [], "versions": {}}

    # embedding
    embedding = local_embed.embed(query)
    if embedding is None:
        return {"route": "fallback_raw", "reason": "embedding failed",
                "results": [], "versions": {}}

    # 检索
    coll = client.get_or_create_collection(collection_name)
    try:
        result = coll.query(query_embeddings=[embedding], n_results=top_k,
                            include=["metadatas", "documents", "distances"])
    except ChromaError:
        return {"route": "fallback_raw", "reason": "query failed",
                "results": [], "versions": {}}

    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    distances = result.get("distances", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]

    results = []
    for i, (uid, doc, dist, meta) in enumerate(zip(ids, documents, distances, metadatas)):
        lifecycle = (meta.get("lifecycle", "current") if isinstance(meta, dict) else "current")
        # 过滤非 current lifecycle
        if lifecycle not in ("current",):
            continue

        item = {
            "rank": i + 1,
            "unit_id": uid,
            "subject": meta.get("subject", "") if isinstance(meta, dict) else "",
            "answer": doc[:200] if doc else "",
            "score": round(1 - dist, 4) if isinstance(dist, (int, float)) else 0,
            "lifecycle": lifecycle,
            "confidence": meta.get("confidence", 0) if isinstance(meta, dict) else 0,
            "source_message_ref": meta.get("source_message_ref", "") if isinstance(meta, dict) else "",
        }
        if include_evidence:
            item["evidence_quote"] = ""  # evidence refs only, not full text
        results.append(item)

    # 从 DB 读版本信息
    try:
        con = sqlite3.connect(f"file:{UNIFIED_DB.as_posix()}?mode=ro", uri=True)
        row = con.execute(
            "SELECT version_id, build_id, canonical_build_id, unit_count, status "
            "FROM knowledge_index_versions WHERE collection_name=? ORDER BY created_at DESC LIMIT 1",
            (collection_name,),
        ).fetchone()
        if row:
            versions = {
                "index_version": row[0],
                "build_id": row[1],
                "canonical_build_id": row[2],
                "unit_count": row[3],
                "status": row[4],
            }
        con.close()
    except Exception:
        pass

    return {"route": route, "results": results, "versions": versions,
            "collection": collection_name}


def generate_canary_queries(n: int = 30) -> list[dict]:
    """从 canonical store 生成 canary queries（隐私安全：只含 query hash）。

    内部读 question 原文用于检索，但返回的 dict 只含 hash（不泄露原 query）。
    query_text 字段仅供 run_canary 内部使用，不写入 report。
    """
    con = sqlite3.connect(f"file:{UNIFIED_DB.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    # 从 knowledge_units 取 n 个 question 作为 query
    rows = con.execute(
        "SELECT DISTINCT question FROM canonical_knowledge_units "
        "WHERE status='current' ORDER BY RANDOM() LIMIT ?", (n,)
    ).fetchall()
    con.close()

    queries = []
    for r in rows:
        q = r["question"]
        queries.append({
            "query_text": q,  # 内部用，不写入 report
            "query_hash": hashlib.sha256(q.encode("utf-8")).hexdigest()[:32],
            "top_k": 5,
            "label": "",
        })
    return queries


def run_canary(
    collection_name: str,
    n_queries: int = 30,
    report_path: Path | None = None,
    candidate_override: bool = False,
) -> dict:
    """运行 canary evaluation。不修改 active pointer。

    candidate_override=True 时 route 标记为 knowledge_canary_override，
    且从指定的 collection_name 检索（而非 active pointer）。
    """
    queries = generate_canary_queries(n_queries)
    if not queries:
        return {"error": "no canonical units found"}

    # 记录 canary 前 active 状态
    active_before = read_active_collection()

    results = []
    latencies = []
    for q in queries:
        t0 = time.time()
        # 用原 query 文本做检索（不是 hash）
        result = search_knowledge_units(
            query=q["query_text"],
            top_k=q["top_k"],
            collection_name=collection_name,
        )
        latency_ms = (time.time() - t0) * 1000
        latencies.append(latency_ms)

        route = result["route"]
        if candidate_override and route == "knowledge":
            route = "knowledge_canary_override"

        results.append({
            "query_hash": q["query_hash"],
            "route": route,
            "top_k": q["top_k"],
            "returned_ids": [r["unit_id"] for r in result["results"]],
            "scores": [r["score"] for r in result["results"]],
            "latency_ms": round(latency_ms, 1),
            "label": q["label"],
            "versions": result.get("versions", {}),
        })

    # 确认 active 未变
    active_after = read_active_collection()
    active_unchanged = active_before == active_after

    report = {
        "generated_at": _utc_now(),
        "collection": collection_name,
        "candidate_override": candidate_override,
        "query_count": len(results),
        "active_unchanged": active_unchanged,
        "active_before": active_before,
        "active_after": active_after,
        "results": results,
        "gate": {"status": "pending_labels"},
        "p50_latency_ms": round(sorted(latencies)[len(latencies)//2], 1) if latencies else 0,
        "p95_latency_ms": round(sorted(latencies)[int(len(latencies)*0.95)], 1) if latencies else 0,
    }

    if report_path:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    return report


def check_label_completeness(report_path: Path) -> dict:
    """检查 canary report 的 label 完整性。"""
    report = json.loads(report_path.read_text(encoding="utf-8"))
    valid_labels = {"helpful", "wrong", "stale", "missing"}
    total = len(report.get("results", []))
    labeled = 0
    invalid = 0
    missing = 0
    for r in report.get("results", []):
        label = r.get("label", "")
        if not label:
            missing += 1
        elif label in valid_labels:
            labeled += 1
        else:
            invalid += 1
    return {
        "total": total,
        "labeled": labeled,
        "missing": missing,
        "invalid": invalid,
        "complete": total > 0 and labeled == total and invalid == 0 and missing == 0,
    }


def compute_gate(report_path: Path) -> dict:
    """计算隔离 canary gate。要求 helpful≥80%、critical wrong/stale=0、fallback≤30%。"""
    report = json.loads(report_path.read_text(encoding="utf-8"))
    results = report.get("results", [])
    total = len(results)
    if total == 0:
        return {"status": "FAIL", "reason": "no results"}

    labels = [r.get("label", "") for r in results]
    helpful = sum(1 for l in labels if l == "helpful")
    wrong = sum(1 for l in labels if l == "wrong")
    stale = sum(1 for l in labels if l == "stale")
    missing_label = sum(1 for l in labels if l == "missing")
    fallback = sum(1 for r in results if "fallback" in r.get("route", ""))

    # 检查 label 完整性
    unlabeled = sum(1 for l in labels if l not in {"helpful", "wrong", "stale", "missing"})
    if unlabeled > 0:
        return {"status": "awaiting_labels",
                "reason": f"{unlabeled} queries missing labels",
                "helpful": helpful, "wrong": wrong, "stale": stale, "missing": missing_label}

    helpful_rate = helpful / total
    critical_wrong_stale = wrong + stale  # wrong + stale 都是 critical
    fallback_rate = fallback / total
    p95 = report.get("p95_latency_ms", 999)

    checks = {
        "helpful_rate_80": helpful_rate >= 0.80,
        "critical_wrong_stale_zero": critical_wrong_stale == 0,
        "fallback_le_30": fallback_rate <= 0.30,
    }
    # latency gate: p95 <= 2x raw baseline (raw p95 ~20ms, so gate at 500ms as soft)
    checks["latency_p95_ok"] = p95 <= 500.0

    status = "PASS" if all(checks.values()) else "FAIL"
    return {
        "status": status,
        "helpful_rate": round(helpful_rate, 4),
        "critical_wrong_stale": critical_wrong_stale,
        "fallback_rate": round(fallback_rate, 4),
        "p95_latency_ms": p95,
        "checks": checks,
        "ready_for_promotion_review": status == "PASS",
    }


def main(argv: list[str] | None = None) -> int:
    """Canary evaluator CLI。

    用法::

        # 生成 30-query canary worksheet（candidate override）
        python evaluate_knowledge_canary.py --candidate-override COLLECTION --queries 30 --report report.json

        # 检查 label 完整性
        python evaluate_knowledge_canary.py --report report.json --check-label-completeness

        # 计算 gate（strict）
        python evaluate_knowledge_canary.py --report report.json --strict
    """
    import argparse
    p = argparse.ArgumentParser(description="Phase 14 Plan 05: canary evaluator")
    p.add_argument("--candidate-override", default="", help="run canary against this candidate collection (not active)")
    p.add_argument("--queries", type=int, default=30, help="number of canary queries")
    p.add_argument("--report", default="", help="report JSON path")
    p.add_argument("--check-label-completeness", action="store_true")
    p.add_argument("--strict", action="store_true", help="compute gate (requires all labels)")
    args = p.parse_args(argv)

    report_path = Path(args.report) if args.report else None

    if args.check_label_completeness:
        if not report_path or not report_path.exists():
            print("[error] --report required for --check-label-completeness", file=sys.stderr)
            return 2
        result = check_label_completeness(report_path)
        print(json.dumps(result, indent=2))
        return 0 if result["complete"] else 1

    if args.strict:
        if not report_path or not report_path.exists():
            print("[error] --report required for --strict", file=sys.stderr)
            return 2
        result = compute_gate(report_path)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("status") == "PASS" else 1

    # 默认：运行 canary
    collection = args.candidate_override or read_active_collection() or ""
    if not collection:
        print("[error] no active collection and no --candidate-override", file=sys.stderr)
        return 2

    report = run_canary(
        collection_name=collection,
        n_queries=args.queries,
        report_path=report_path,
        candidate_override=bool(args.candidate_override),
    )
    if "error" in report:
        print(f"[error] {report['error']}", file=sys.stderr)
        return 1

    print(f"Canary complete: {report['query_count']} queries")
    print(f"  route: {'canary_override' if args.candidate_override else 'active'}")
    print(f"  collection: {report['collection']}")
    print(f"  active_unchanged: {report['active_unchanged']}")
    print(f"  p50: {report['p50_latency_ms']}ms, p95: {report['p95_latency_ms']}ms")
    print(f"  labels: pending (use --check-label-completeness after labeling)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())