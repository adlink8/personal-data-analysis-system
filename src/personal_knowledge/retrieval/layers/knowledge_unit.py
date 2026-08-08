"""Primary knowledge-unit layer — top of the hybrid retrieval chain.

Port of the "Phase 1: 知识层检索" block from semantic_search.search_knowledge_units.
This layer is not part of the fallback chain; the assembler runs it first,
then feeds the remaining slots through fallback_policy.build_fallback_chain.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from personal_knowledge.retrieval import _constants as _C
from personal_knowledge.retrieval.layers.base import RetrieverLayer, SearchState
from personal_knowledge.retrieval.relevance import annotate_candidate_support


class KnowledgeUnitLayer(RetrieverLayer):
    """Knowledge-first retrieval on the active Chroma KU collection.

    Queries the active collection, keeps only lifecycle=current units, gates
    each candidate through annotate_candidate_support, and reads the index
    version row. ChromaError propagates so the assembler can switch to the
    fallback route; non-Chroma failures propagate exactly like the original
    god function.
    """

    layer_name = "knowledge_unit"
    role = "knowledge_retrieval"

    def retrieve(self, query: str, state: SearchState) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        ku_collection = state.ku_collection
        if not ku_collection:
            state.route = "fallback_raw"
            return results

        client = state.client
        cols = client.list_collections()
        col_names = {c if isinstance(c, str) else c.get("name", "") for c in cols}
        if ku_collection not in col_names:
            state.route = "fallback_raw"
            return results

        ku_coll = client.get_or_create_collection(ku_collection)
        ku_fetch = max(state.top_k, _C._KU_SLOTS)
        kr = ku_coll.query(
            query_embeddings=[state.embedding], n_results=ku_fetch,
            include=["metadatas", "documents", "distances"],
        )
        ku_ids = kr.get("ids", [[]])[0] if kr.get("ids") else []
        ku_docs = kr.get("documents", [[]])[0] if kr.get("documents") else []
        ku_dists = kr.get("distances", [[]])[0] if kr.get("distances") else []
        ku_metas = kr.get("metadatas", [[]])[0] if kr.get("metadatas") else []

        resolve_support_ref = state.resolve_support_ref
        for uid, doc, dist, meta in zip(ku_ids, ku_docs, ku_dists, ku_metas):
            lc = meta.get("lifecycle", "current") if isinstance(meta, dict) else "current"
            if lc not in ("current",):
                continue
            item: dict[str, Any] = {
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
            if state.include_evidence:
                item["evidence_quote"] = ""
            decision = annotate_candidate_support(
                query,
                item,
                resolve=lambda ref: resolve_support_ref(item, ref),
            )
            if decision.state == "unsupported":
                state.ku_abstained += 1
                continue
            results.append(item)
            if len(results) >= _C._KU_SLOTS:
                break

        # 读版本信息 (read index version row for telemetry/response).
        try:
            con = sqlite3.connect(f"file:{_C.UNIFIED_DB.as_posix()}?mode=ro", uri=True)
            row = con.execute(
                "SELECT version_id, build_id, canonical_build_id, unit_count, status "
                "FROM knowledge_index_versions WHERE collection_name=? ORDER BY created_at DESC LIMIT 1",
                (ku_collection,),
            ).fetchone()
            if row:
                state.versions = {
                    "index_version": row[0], "build_id": row[1],
                    "canonical_build_id": row[2], "unit_count": row[3], "status": row[4],
                }
            con.close()
        except Exception:
            pass
        return results
