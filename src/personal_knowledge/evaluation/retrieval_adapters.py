"""Five-mode retrieval adapters without hard-coded collection constants."""

from __future__ import annotations

import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from personal_knowledge.evaluation.eval_contracts import EvalCase, EvalTarget  # noqa: E402
from personal_knowledge.evaluation.knowledge_eval_metrics import RankedHit  # noqa: E402

L2_RUN_IDS_DEFAULT = (
    "205bff9560b915508f343aebc0fe4b0b",
    "2a63b7e98fd3454c1aae3deedcdf038d",
)


@dataclass
class AdapterResult:
    mode: str
    ranked: list[RankedHit]
    latency_ms: float
    first_layer: str = ""
    blocked: bool = False
    blocked_reason: str = ""
    collection: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


def resolve_targets(
    *,
    l1_collection: str,
    l1_l2_collection: str,
    raw_collection: str = "personal_events",
    l2_only_collection: str = "",
    l2_lineage_runs: Sequence[str] | None = None,
    top_k: int = 5,
    embed_model: str = "bge-small-zh-v1.5",
    l2_filter_ids: set[str] | None = None,
    l2_blocked_reason: str = "",
) -> list[EvalTarget]:
    """Build five EvalTargets from injected collection/run config."""
    targets = [
        EvalTarget(
            mode="raw",
            collection=raw_collection,
            top_k=top_k,
            embed_model=embed_model,
        ),
        EvalTarget(
            mode="l1",
            collection=l1_collection,
            top_k=top_k,
            embed_model=embed_model,
            lineage_filter={"exclude_unit_prefix": "l2|"},
        ),
    ]
    if l2_only_collection and l2_filter_ids is not None and len(l2_filter_ids) > 0:
        targets.append(
            EvalTarget(
                mode="l2_only",
                collection=l2_only_collection or l1_l2_collection,
                top_k=top_k,
                embed_model=embed_model,
                lineage_filter={
                    "run_ids": list(l2_lineage_runs or L2_RUN_IDS_DEFAULT),
                    "unit_id_prefix": "l2|",
                    "filter_id_count": len(l2_filter_ids),
                },
            )
        )
    else:
        targets.append(
            EvalTarget(
                mode="l2_only",
                collection=l2_only_collection or l1_l2_collection,
                top_k=top_k,
                embed_model=embed_model,
                blocked=True,
                blocked_reason=l2_blocked_reason
                or "L2-only requires auditable lineage unit_id set; not purified",
            )
        )
    targets.append(
        EvalTarget(
            mode="l1_l2",
            collection=l1_l2_collection,
            top_k=top_k,
            embed_model=embed_model,
        )
    )
    targets.append(
        EvalTarget(
            mode="hybrid",
            collection=l1_l2_collection,
            top_k=top_k,
            embed_model=embed_model,
            fallback_policy="layered",
        )
    )
    return targets


def load_l2_unit_ids(
    db_path: Path,
    run_ids: Sequence[str] | None = None,
) -> set[str]:
    if not db_path.exists():
        return set()
    runs = list(run_ids or L2_RUN_IDS_DEFAULT)
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    ids: set[str] = set()
    for rid in runs:
        for row in con.execute(
            "SELECT unit_id FROM knowledge_units WHERE unit_id LIKE 'l2|%' AND run_id=?",
            (rid,),
        ):
            ids.add(row[0])
    # also include canonical ids that have only l2 members? keep unit_ids for filter
    con.close()
    return ids


def _chroma_query(
    collection: str,
    query: str,
    top_k: int,
    *,
    id_allow: set[str] | None = None,
    id_deny_prefix: str | None = None,
) -> AdapterResult:
    from personal_knowledge.core.chroma_client import ChromaClient, ChromaError
    import personal_knowledge.core.local_embed as local_embed

    t0 = time.perf_counter()
    emb = local_embed.embed(query)
    if emb is None:
        return AdapterResult(
            mode="",
            ranked=[],
            latency_ms=(time.perf_counter() - t0) * 1000,
            blocked=True,
            blocked_reason="embedding unavailable",
            collection=collection,
        )
    client = ChromaClient()
    coll = client.get_or_create_collection(collection)
    # over-fetch if filtering
    n = top_k * 5 if (id_allow is not None or id_deny_prefix) else top_k
    n = max(n, top_k)
    try:
        kr = coll.query(
            query_embeddings=[emb],
            n_results=min(n, 50),
            include=["metadatas", "documents", "distances"],
        )
    except ChromaError as e:
        return AdapterResult(
            mode="",
            ranked=[],
            latency_ms=(time.perf_counter() - t0) * 1000,
            blocked=True,
            blocked_reason=str(e)[:200],
            collection=collection,
        )
    ids = (kr.get("ids") or [[]])[0]
    metas = (kr.get("metadatas") or [[]])[0]
    docs = (kr.get("documents") or [[]])[0]
    dists = (kr.get("distances") or [[]])[0]
    ranked: list[RankedHit] = []
    for uid, meta, doc, dist in zip(ids, metas, docs, dists):
        meta = meta or {}
        if id_allow is not None and uid not in id_allow:
            # also allow if source is l2 via meta
            if not str(uid).startswith("l2|"):
                continue
            if uid not in id_allow:
                continue
        if id_deny_prefix and str(uid).startswith(id_deny_prefix):
            continue
        score = 1.0 / (1.0 + float(dist or 0.0))
        ranked.append(
            RankedHit(
                id=str(uid),
                score=score,
                source_ref=str(meta.get("source_message_ref") or ""),
                subject=str(meta.get("subject") or ""),
                snippet=str(doc or "")[:300],
                layer="knowledge_unit",
                meta=dict(meta),
            )
        )
        if len(ranked) >= top_k:
            break
    return AdapterResult(
        mode="",
        ranked=ranked,
        latency_ms=(time.perf_counter() - t0) * 1000,
        first_layer="knowledge_unit",
        collection=collection,
    )


def run_adapter(
    target: EvalTarget,
    case: EvalCase,
    *,
    l2_unit_ids: set[str] | None = None,
    search_hybrid: Callable[..., dict] | None = None,
) -> AdapterResult:
    """Execute one mode for one case."""
    if target.blocked:
        return AdapterResult(
            mode=target.mode,
            ranked=[],
            latency_ms=0.0,
            blocked=True,
            blocked_reason=target.blocked_reason,
            collection=target.collection,
        )

    if target.mode == "hybrid":
        fn = search_hybrid
        if fn is None:
            from personal_knowledge.retrieval.unified_search import search_knowledge_units

            fn = search_knowledge_units
        t0 = time.perf_counter()
        result = fn(
            case.query,
            top_k=target.top_k,
            fallback_policy=target.fallback_policy or "layered",
            collection_override=target.collection or None,
        )
        latency = (time.perf_counter() - t0) * 1000
        hits = result.get("results") or result.get("hits") or []
        ranked: list[RankedHit] = []
        for h in hits[: target.top_k]:
            ranked.append(
                RankedHit(
                    id=str(
                        h.get("unit_id")
                        or h.get("id")
                        or h.get("canonical_message_id")
                        or h.get("event_id")
                        or ""
                    ),
                    score=float(h.get("score") or h.get("similarity") or 0.0),
                    source_ref=str(
                        h.get("source_message_ref")
                        or h.get("canonical_message_id")
                        or ""
                    ),
                    subject=str(h.get("subject") or h.get("title") or ""),
                    snippet=str(h.get("answer") or h.get("content") or h.get("snippet") or "")[
                        :300
                    ],
                    layer=str(h.get("layer") or h.get("source_layer") or ""),
                    meta=dict(h) if isinstance(h, dict) else {},
                )
            )
        tel = result.get("telemetry") or {}
        first = ""
        for layer in tel.get("layers") or []:
            if layer.get("hits"):
                first = layer.get("name") or ""
                break
        return AdapterResult(
            mode="hybrid",
            ranked=ranked,
            latency_ms=latency,
            first_layer=first or str(result.get("route") or "hybrid"),
            collection=target.collection,
            meta={"telemetry": tel, "fallback_policy": result.get("fallback_policy")},
        )

    if target.mode == "raw":
        # Prefer personal_events chroma; fall back to dialogue search if needed
        res = _chroma_query(target.collection or "personal_events", case.query, target.top_k)
        res.mode = "raw"
        res.first_layer = "raw"
        return res

    if target.mode == "l2_only":
        allow = l2_unit_ids
        if not allow:
            return AdapterResult(
                mode="l2_only",
                ranked=[],
                latency_ms=0.0,
                blocked=True,
                blocked_reason="L2-only lineage unit set empty",
                collection=target.collection,
            )
        res = _chroma_query(
            target.collection,
            case.query,
            target.top_k,
            id_allow=allow,
        )
        # If collection stores canonical ids not l2|, try metadata filter via over-fetch
        if not res.ranked:
            # secondary: query without filter then keep rows whose source is in allow via meta
            res2 = _chroma_query(target.collection, case.query, target.top_k * 10)
            filtered = []
            for h in res2.ranked:
                uid = h.id
                src = h.meta.get("member_unit_ids") or h.meta.get("source_unit_id") or ""
                if uid in allow or str(uid).startswith("l2|") or any(
                    x in allow for x in str(src).split(",") if x
                ):
                    filtered.append(h)
                if len(filtered) >= target.top_k:
                    break
            res.ranked = filtered
            res.latency_ms = res2.latency_ms
            if not filtered:
                res.blocked = True
                res.blocked_reason = (
                    "L2-only could not purify hits from collection "
                    "(canonical index may not expose l2 unit ids)"
                )
        res.mode = "l2_only"
        res.first_layer = "l2_only"
        return res

    if target.mode == "l1":
        res = _chroma_query(
            target.collection,
            case.query,
            target.top_k,
            id_deny_prefix="l2|",
        )
        res.mode = "l1"
        res.first_layer = "l1"
        return res

    if target.mode == "l1_l2":
        res = _chroma_query(target.collection, case.query, target.top_k)
        res.mode = "l1_l2"
        res.first_layer = "l1_l2"
        return res

    return AdapterResult(
        mode=target.mode,
        ranked=[],
        latency_ms=0.0,
        blocked=True,
        blocked_reason=f"unknown mode {target.mode}",
        collection=target.collection,
    )
