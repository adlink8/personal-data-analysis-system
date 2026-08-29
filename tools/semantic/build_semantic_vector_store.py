# 正式住所: tools/semantic/build_semantic_vector_store.py（与 mvp_semantic_compress.py 同居）。
# 运行: python tools/semantic/build_semantic_vector_store.py --dry-run | --write [--activate]
"""把语义压缩 MVP 产物（var/db/semantic_mvp_v3.sqlite 的 session_cards + ku_facts）
向量化进 Chroma，并登记构建版本。

数据面（只读）：
- ku_facts（status='active'）：文档 = guard_text(fact)，id = ``f|<fact_key>``，
  metadata {kind:'fact', session_id, fact_key, confidence, valid_from}。
- session_cards（全部）：文档 = guard_text(purpose + '\n' + summary_md)，
  id = ``c|<session_id>``，metadata {kind:'card', session_id, n_messages, created_at}。

collection 命名 ``semantic_mvp_v1_<UTC时间戳>``：版本化惯例，每次构建产生新版本，
旧版本一律保留、绝不删除（本脚本无任何删除路径）。

构建登记写 ``var/db/semantic_index_registry.json``：
  {"builds": [{build_id, collection, docs, dim, model, embedding_policy,
               chroma_endpoint, status, created_at}]}
status 取 candidate | active | superseded，active 至多一个：``--activate`` 把本次
build 标 active，其余曾是 active 的降级为 superseded（candidate 保持 candidate）。

注意：本脚本**不写** canonical 的 knowledge_index_versions（该表外键依赖正式
build_runs，语义 MVP 产物尚未走 KU 程序转正）；登记只落在 var/ 下的 JSON。
等 KU 程序转正后再由正式管线登记 canonical 版本表。

embedding 用本机模型（personal_knowledge.core.local_embed，bge-small-zh-v1.5，
512 维），不经任何联网 LLM。

用法::

    python tools/semantic/build_semantic_vector_store.py --dry-run
    python tools/semantic/build_semantic_vector_store.py --write
    python tools/semantic/build_semantic_vector_store.py --write --activate
"""
from __future__ import annotations

import os

# runtime_config 的默认 embedding 模型候选路径指向 C 盘残缺缓存（实测加载必失败，
# D 盘副本可用）；修复 runtime_config 默认值属另一任务，这里先在进程内兜底。
# setdefault：调用方已显式设置 PERSONAL_DATA_EMBED_MODEL_PATH 时不覆盖。
# 必须在 import local_embed 之前设置。
os.environ.setdefault("PERSONAL_DATA_EMBED_MODEL_PATH", r"D:\models\bge-small-zh-v1.5")

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))

from personal_knowledge.core import local_embed
from personal_knowledge.core.chroma_client import ChromaClient, ChromaError
from personal_knowledge.core.privacy_guard import guard_text
from personal_knowledge.core.project_paths import VAR_DB
from personal_knowledge.retrieval.semantic_cards import CARDS_DB_PATH, SEMANTIC_INDEX_REGISTRY

COLLECTION_PREFIX = "semantic_mvp_v1"
EMBED_MODEL = "bge-small-zh-v1.5"
EMBEDDING_POLICY = "semantic-mvp-cards-facts-v1"
ADD_BATCH = 500  # 单批 HTTP 写入上限，避免大 payload


def load_documents(db_path: Path) -> tuple[list[str], list[str], list[dict], dict]:
    """只读加载 active facts + 全部卡，返回 (ids, documents, metadatas, counts)。

    guard_text 后为空的文档跳过（正常数据不会触发；跳过数计入 counts.skipped）。
    """
    con = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        facts = con.execute(
            "select fact_key, session_id, fact, confidence, valid_from"
            " from ku_facts where status='active' order by fact_key"
        ).fetchall()
        cards = con.execute(
            "select session_id, purpose, summary_md, n_messages, created_at"
            " from session_cards order by session_id"
        ).fetchall()
    finally:
        con.close()

    ids: list[str] = []
    documents: list[str] = []
    metadatas: list[dict] = []
    skipped = 0
    for row in facts:
        text = guard_text(row["fact"]).text
        if not (text or "").strip():
            skipped += 1
            continue
        ids.append(f"f|{row['fact_key']}")
        documents.append(text)
        metadatas.append({
            "kind": "fact",
            "session_id": row["session_id"],
            "fact_key": row["fact_key"],
            "confidence": row["confidence"] or "",
            "valid_from": row["valid_from"] or "",
        })
    for row in cards:
        text = guard_text(f"{row['purpose'] or ''}\n{row['summary_md'] or ''}").text
        if not (text or "").strip():
            skipped += 1
            continue
        ids.append(f"c|{row['session_id']}")
        documents.append(text)
        metadatas.append({
            "kind": "card",
            "session_id": row["session_id"],
            "n_messages": int(row["n_messages"] or 0),
            "created_at": row["created_at"] or "",
        })
    counts = {"facts": len(facts), "cards": len(cards), "docs": len(ids), "skipped": skipped}
    return ids, documents, metadatas, counts


def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def update_registry(
    registry_path: Path,
    entry: dict,
    activate: bool,
) -> None:
    """追加本次 build 到登记文件；activate 时保证 active 至多一个。

    已存在的 active build 降级为 superseded；candidate 保持 candidate（语义上
    candidate 是"从未转正"的构建，不该被后续激活连带改写历史）。
    登记文件已存在但不可解析时报错退出，绝不静默覆盖既有登记。
    """
    builds: list[dict] = []
    if registry_path.exists():
        try:
            data = json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SystemExit(f"[error] 登记文件存在但无法解析（拒绝覆盖）: {registry_path}: {exc}")
        builds = list(data.get("builds", []))
    if activate:
        for b in builds:
            if b.get("status") == "active":
                b["status"] = "superseded"
    entry = dict(entry)
    entry["status"] = "active" if activate else "candidate"
    builds.append(entry)
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(
        json.dumps({"builds": builds}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run(db_path: Path, host: str, port: int, dry_run: bool, write: bool, activate: bool) -> int:
    if dry_run and write:
        print("[error] --dry-run 与 --write 互斥", file=sys.stderr)
        return 2
    if activate:
        write = True  # 激活必须真建

    ts = _utc_ts()
    collection_name = f"{COLLECTION_PREFIX}_{ts}"
    build_id = f"sem_{ts}"

    ok, msg, dim = local_embed.verify_model()
    if not ok:
        print(f"[error] embedding 模型不可用: {msg}", file=sys.stderr)
        return 1

    ids, documents, metadatas, counts = load_documents(db_path)

    print("=" * 60)
    print("语义 MVP 向量层构建（session_cards + ku_facts -> Chroma）")
    print("=" * 60)
    print(f"db:              {db_path}")
    print(f"active facts:    {counts['facts']}")
    print(f"cards:           {counts['cards']}")
    print(f"docs:            {counts['docs']} (skipped empty after guard: {counts['skipped']})")
    print(f"embed:           {EMBED_MODEL} ({dim}d)  [{msg}]")
    print(f"embed policy:    {EMBEDDING_POLICY}")
    print(f"collection:      {collection_name}")
    print(f"build_id:        {build_id}")
    print(f"chroma:          http://{host}:{port}")
    print(f"registry:        {SEMANTIC_INDEX_REGISTRY}")
    print(f"status:          {'active' if activate else 'candidate'}")

    if not write:
        print("[dry-run] 未写入")
        return 0

    client = ChromaClient(host=host, port=port)
    try:
        client.heartbeat()
    except ChromaError as exc:
        print(f"[error] chroma 不可达: {exc}", file=sys.stderr)
        return 1
    # 版本化命名 + 禁止删除：同名已存在说明时间戳撞车或重复运行，拒绝而非覆盖。
    existing = {c.get("name") for c in client.list_collections()}
    if collection_name in existing:
        print(f"[error] collection {collection_name} 已存在（本脚本不覆盖/不删除），请重跑以换时间戳", file=sys.stderr)
        return 1

    coll = client.get_or_create_collection(collection_name, metadata={
        "hnsw:space": "cosine",
        "embedding_policy": EMBEDDING_POLICY,
        "model": EMBED_MODEL,
    })

    print(f"[embed] embedding {len(documents)} docs ...", flush=True)
    embeddings = local_embed.embed_batch(documents)
    if embeddings is None or len(embeddings) != len(documents) or any(e is None for e in embeddings):
        print("[error] embed_batch 失败（返回数不符或含空向量）", file=sys.stderr)
        return 1

    emb_lists = [list(e) for e in embeddings]
    for i in range(0, len(ids), ADD_BATCH):
        j = min(i + ADD_BATCH, len(ids))
        coll.add(ids=ids[i:j], embeddings=emb_lists[i:j],
                 documents=documents[i:j], metadatas=metadatas[i:j], timeout=300)
        print(f"[index] wrote {j}/{len(ids)}", flush=True)

    written = coll.count()
    if written != len(ids):
        print(f"[error] count 不符: collection={written} expected={len(ids)}（未写登记，collection 保留待人工处理）",
              file=sys.stderr)
        return 1

    update_registry(SEMANTIC_INDEX_REGISTRY, {
        "build_id": build_id,
        "collection": collection_name,
        "docs": len(ids),
        "dim": dim,
        "model": EMBED_MODEL,
        "embedding_policy": EMBEDDING_POLICY,
        "chroma_endpoint": f"http://{host}:{port}",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }, activate=activate)

    print(f"[done] collection {collection_name} count={written}")
    print(f"[done] registry updated: {SEMANTIC_INDEX_REGISTRY} (status={'active' if activate else 'candidate'})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="语义 MVP 产物向量化进 Chroma（只读 v3 库，版本化 collection）")
    parser.add_argument("--db", type=Path, default=CARDS_DB_PATH,
                        help="MVP 语义库路径（默认 var/db/semantic_mvp_v3.sqlite，只读）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    parser.add_argument("--dry-run", action="store_true", help="只打印构建计划，不写")
    parser.add_argument("--write", action="store_true", help="真建 collection 并写登记")
    parser.add_argument("--activate", action="store_true",
                        help="建后即标 active（检索层向量路径启用），其余 active build 降级 superseded")
    args = parser.parse_args(argv)
    if not args.write and not args.dry_run:
        args.dry_run = True  # 默认 dry-run，防误写
    return run(args.db, args.host, args.port, args.dry_run, args.write, args.activate)


if __name__ == "__main__":
    raise SystemExit(main())
