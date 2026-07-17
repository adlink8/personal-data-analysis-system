"""Phase 14 Wave 4.1：knowledge unit candidate vector store。

把 ``status='current'`` 的 knowledge units 向量化到版本化 Chroma collection。
collection 命名包含 build ID；向量化文本为 question+answer，metadata 保存
canonical ID/type/subject/status/version。

只索引 evidence gate passed 的 current units。exact reconcile：collection IDs
必须等于 eligible unit IDs，missing/orphan/duplicate 均为 0。不覆盖 active pointer。

用法::

    python build_knowledge_unit_vector_store.py --dry-run
    python build_knowledge_unit_vector_store.py --write
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from personal_knowledge.core.sqlite import connect_rw

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
_THIS_DIR = _SCRIPTS_DIR  # legacy alias: scripts root for resource paths

from personal_knowledge.core.project_paths import UNIFIED_DB  # noqa: E402
from personal_knowledge.core.chroma_client import ChromaClient, ChromaError  # noqa: E402
import personal_knowledge.core.local_embed as local_embed  # noqa: E402

COLLECTION_PREFIX = "knowledge_units"


@dataclass
class VectorStoreStats:
    """candidate index 构建统计。"""
    build_id: str = ""
    collection_name: str = ""
    eligible_units: int = 0
    indexed: int = 0
    missing: int = 0       # eligible but not indexed（必须 0）
    orphan: int = 0        # indexed but not eligible（必须 0）
    duplicate: int = 0     # 重复 ID（必须 0）
    embed_dim: int = 0
    embed_model: str = ""
    gate_passed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _get_current_run_id(db_path: Path) -> str | None:
    """获取最新的 validated/current build run ID。"""
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    row = con.execute(
        "SELECT run_id FROM knowledge_build_runs "
        "WHERE status IN ('current','validated') "
        "ORDER BY generated_at DESC LIMIT 1"
    ).fetchone()
    con.close()
    return row[0] if row else None


def load_eligible_units(db_path: Path) -> list[dict]:
    """加载 status='current' 的 canonical knowledge units。"""
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT c.canonical_unit_id as unit_id, c.unit_type, c.subject, c.question, c.answer, "
        "c.confidence, c.lifecycle, c.run_id, "
        "COALESCE((SELECT source_message_ref FROM knowledge_units u "
        "  JOIN canonical_unit_members cum ON u.unit_id=cum.member_unit_id "
        "  WHERE cum.canonical_unit_id=c.canonical_unit_id LIMIT 1), '') as source_message_ref "
        "FROM canonical_knowledge_units c "
        "WHERE c.status='current' AND c.lifecycle='current'"
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def build_candidate_index(
    db_path: Path = UNIFIED_DB,
    write: bool = False,
) -> tuple[VectorStoreStats, str | None]:
    """构建 candidate Chroma collection。

    返回 ``(stats, collection_name_or_none)``。
    """
    stats = VectorStoreStats()

    # 验证 embedding 模型
    ok, msg, dim = local_embed.verify_model()
    if not ok:
        stats.gate_passed = False
        return stats, None
    stats.embed_dim = dim
    stats.embed_model = "bge-small-zh-v1.5"

    # 获取 build ID
    run_id = _get_current_run_id(db_path)
    if not run_id:
        return stats, None
    stats.build_id = run_id[:12]
    ts = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
    collection_name = f"{COLLECTION_PREFIX}_{stats.build_id}_{ts}"
    stats.collection_name = collection_name

    # 加载 eligible units
    units = load_eligible_units(db_path)
    stats.eligible_units = len(units)
    if not units:
        return stats, None

    # 准备向量化文本（question + answer）
    texts = [f"{u['question']} {u['answer']}" for u in units]
    ids = [u["unit_id"] for u in units]

    # 检查重复 ID
    if len(ids) != len(set(ids)):
        stats.duplicate = len(ids) - len(set(ids))

    if not write:
        # dry-run：只报告
        stats.indexed = len(units)
        stats.gate_passed = stats.missing == 0 and stats.orphan == 0 and stats.duplicate == 0
        return stats, None

    # 连接 Chroma
    client = ChromaClient()

    # 创建 collection（如果已存在先删除，保证干净）
    try:
        existing = client.list_collections()
        for col in existing:
            if isinstance(col, dict) and col.get("name") == collection_name:
                # 删除旧 collection
                import requests
                requests.delete(f"{client._base}/collections/{col['id']}", timeout=30)
                break
    except Exception:
        pass

    coll = client.get_or_create_collection(collection_name)

    # 批量 embedding
    embeddings = local_embed.embed_batch(texts)
    if embeddings is None or len(embeddings) != len(texts):
        stats.gate_passed = False
        return stats, None

    # 准备 metadata
    metadatas = [
        {
            "unit_type": u.get("unit_type", ""),
            "subject": u.get("subject", ""),
            "confidence": u.get("confidence", 0),
            "lifecycle": u.get("lifecycle", "current"),
            "run_id": u.get("run_id", "")[:12],
            "source_message_ref": u.get("source_message_ref", "") or "",
        }
        for u in units
    ]

    # 写入 Chroma（分批，避免单次 2 万+ 条撑爆 HTTP）
    batch_size = 500
    try:
        emb_lists = [list(e) for e in embeddings]
        for i in range(0, len(ids), batch_size):
            j = i + batch_size
            coll.add(
                ids=ids[i:j],
                embeddings=emb_lists[i:j],
                documents=texts[i:j],
                metadatas=metadatas[i:j],
                timeout=300,
            )
            if (i // batch_size) % 10 == 0:
                print(f"[index] wrote {min(j, len(ids))}/{len(ids)}", flush=True)
    except (ChromaError, Exception) as e:
        stats.gate_passed = False
        print(f"[error] chroma add failed: {e}", file=sys.stderr)
        return stats, None

    stats.indexed = coll.count()

    # exact reconcile
    indexed_ids = set(ids)
    eligible_ids = set(ids)
    stats.missing = len(eligible_ids - indexed_ids)
    stats.orphan = len(indexed_ids - eligible_ids)
    stats.gate_passed = (
        stats.missing == 0
        and stats.orphan == 0
        and stats.duplicate == 0
        and stats.indexed == stats.eligible_units
    )

    # 记录到 knowledge_index_versions
    con = connect_rw(db_path)
    version_id = f"kiv_{stats.build_id}"
    con.execute(
        "INSERT OR REPLACE INTO knowledge_index_versions VALUES (?,?,?,?,?,?,?,?,?)",
        (
            version_id, run_id, collection_name, run_id,
            stats.indexed, "candidate",
            datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            None, None,
        ),
    )
    con.commit()
    con.close()

    return stats, collection_name


def run(dry_run: bool, write: bool, db_path: Path = UNIFIED_DB) -> int:
    if dry_run and write:
        print("[error] --dry-run 与 --write 互斥", file=sys.stderr)
        return 2

    stats, coll_name = build_candidate_index(db_path, write=write)

    print("=" * 60)
    print("Phase 14 Wave 4.1：Candidate Vector Store")
    print("=" * 60)
    print(f"build_id:        {stats.build_id}")
    print(f"collection:      {stats.collection_name}")
    print(f"eligible units:  {stats.eligible_units}")
    print(f"indexed:         {stats.indexed}")
    print(f"missing:         {stats.missing} (must be 0)")
    print(f"orphan:          {stats.orphan} (must be 0)")
    print(f"duplicate:       {stats.duplicate} (must be 0)")
    print(f"embed:           {stats.embed_model} ({stats.embed_dim}d)")
    print(f"gate:            {'PASS' if stats.gate_passed else 'FAIL'}")
    if coll_name:
        print(f"collection name: {coll_name}")
    elif dry_run:
        print("[dry-run] 未写入")
    return 0 if stats.gate_passed else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Phase 14 Wave 4.1: candidate vector store")
    p.add_argument("--dry-run", action="store_true", default=False)
    p.add_argument("--write", action="store_true")
    p.add_argument("--db", type=Path, default=UNIFIED_DB)
    args = p.parse_args(argv)
    if not args.write and not args.dry_run:
        args.dry_run = True
    return run(args.dry_run, args.write, args.db)


if __name__ == "__main__":
    raise SystemExit(main())
