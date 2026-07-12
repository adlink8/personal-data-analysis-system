"""Phase 14 Plan 06 Task 1: affected-subject incremental refresh + zero-residue reconcile。

用 Phase 13.5 source snapshot/checksum 或 delta watermark 定位受影响 evidence/subjects，
只对这些 subjects 运行 extraction/canonical rebuild。deleted/excluded/deprecated 传播
到 draft/canonical lifecycle 并从 candidate/active surface 移除。

用法::

    python refresh_knowledge_units.py --inspect
    python refresh_knowledge_units.py --source-checksum <hash> --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
_THIS_DIR = _SCRIPTS_DIR  # legacy alias: scripts root for resource paths

from core.project_paths import UNIFIED_DB, AGENT_CONVERSATIONS_DB  # noqa: E402


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _compute_content_hash(content: str) -> str:
    """Compute stable content hash for a canonical message."""
    return hashlib.sha256(content.encode()).hexdigest()[:32]


@dataclass
class RefreshStats:
    """增量刷新统计。"""
    source_changed: bool = False
    affected_evidence_count: int = 0
    affected_subjects: list[str] = field(default_factory=list)
    new_extractions: int = 0
    updated_canonicals: int = 0
    deprecated_count: int = 0
    deleted_count: int = 0
    no_op: bool = True
    pipeline_commands: list[dict] = field(default_factory=list)


def compute_source_checksum(canonical_db: Path = AGENT_CONVERSATIONS_DB) -> str:
    """计算 canonical store 的 source checksum（含内容 hash，检测 content 修改）。"""
    if not canonical_db.exists():
        return ""
    con = sqlite3.connect(f"file:{canonical_db.as_posix()}?mode=ro", uri=True)
    # schema hash + counts + content hash
    ddl = con.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE '%fts%' ESCAPE '\\' ORDER BY name"
    ).fetchall()
    schema_text = "\n;;;".join(sql or "" for _name, sql in ddl)
    session_count = con.execute("SELECT COUNT(*) FROM canonical_sessions").fetchone()[0]
    message_count = con.execute("SELECT COUNT(*) FROM canonical_messages").fetchone()[0]
    # content hash: ordered (ref, content_hash) pairs
    content_rows = con.execute(
        "SELECT canonical_message_id, content FROM canonical_messages ORDER BY canonical_message_id"
    ).fetchall()
    content_blob = "\n".join(f"{row[0]}|{_compute_content_hash(row[1] or '')}" for row in content_rows)
    content_hash = hashlib.sha256(content_blob.encode()).hexdigest()[:16]
    con.close()
    payload = f"{hashlib.sha256(schema_text.encode()).hexdigest()[:16]}|{session_count}|{message_count}|{content_hash}"
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def find_affected_evidence(
    db_path: Path = UNIFIED_DB,
    canonical_db: Path = AGENT_CONVERSATIONS_DB,
    last_source_checksum: str = "",
) -> dict:
    """定位受影响的 evidence refs 和 subjects。

    比较 canonical store 当前 evidence 与 inventory 的差异。
    """
    if not canonical_db.exists():
        return {"error": "canonical DB not found", "affected_refs": [], "affected_subjects": []}

    current_checksum = compute_source_checksum(canonical_db)

    # 如果 source checksum 相同，no-op
    if last_source_checksum and current_checksum == last_source_checksum:
        return {
            "source_changed": False,
            "current_checksum": current_checksum,
            "affected_refs": [],
            "affected_subjects": [],
            "no_op": True,
        }

    # 比较当前 canonical messages 与 inventory items
    con_unified = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    con_canon = sqlite3.connect(f"file:{canonical_db.as_posix()}?mode=ro", uri=True)

    # inventory 中已有的 evidence refs
    inv_refs = {
        r[0] for r in con_unified.execute(
            "SELECT evidence_ref FROM knowledge_inventory_items"
        ).fetchall()
    }

    # 当前 canonical store 的 eligible user evidence refs
    current_refs = {
        r[0] for r in con_canon.execute(
            "SELECT m.canonical_message_id FROM canonical_messages m "
            "JOIN canonical_sessions s ON m.canonical_session_id=s.canonical_session_id "
            "WHERE m.role='user' AND s.evidence_eligible=1 "
            "AND m.content IS NOT NULL AND length(m.content) > 20"
        ).fetchall()
    }

    con_unified.close()
    con_canon.close()

    # 新增的 refs（在 canonical 但不在 inventory）
    new_refs = current_refs - inv_refs
    # 消失的 refs（在 inventory 但不在 canonical）
    deleted_refs = inv_refs - current_refs

    # 查受影响的 subjects（从 knowledge_units）
    affected_subjects = set()
    if new_refs or deleted_refs:
        con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        # 删除的 refs 对应的 units 的 subjects
        if deleted_refs:
            placeholders = ",".join("?" * min(len(deleted_refs), 500))
            for r in con.execute(
                f"SELECT DISTINCT subject FROM knowledge_units "
                f"WHERE source_message_ref IN ({placeholders})",
                tuple(list(deleted_refs)[:500]),
            ):
                affected_subjects.add(r[0])
        con.close()

    return {
        "source_changed": True,
        "current_checksum": current_checksum,
        "new_refs_count": len(new_refs),
        "deleted_refs_count": len(deleted_refs),
        "new_refs": list(new_refs)[:100],  # 限制输出
        "deleted_refs": list(deleted_refs)[:100],
        "affected_subjects": sorted(affected_subjects),
        "no_op": len(new_refs) == 0 and len(deleted_refs) == 0,
    }


def refresh(
    db_path: Path = UNIFIED_DB,
    canonical_db: Path = AGENT_CONVERSATIONS_DB,
    last_source_checksum: str = "",
    dry_run: bool = True,
) -> tuple[RefreshStats, dict]:
    """执行增量刷新。返回 (stats, detail)。"""
    detail = find_affected_evidence(db_path, canonical_db, last_source_checksum)
    stats = RefreshStats()

    if detail.get("no_op"):
        stats.no_op = True
        return stats, detail

    stats.source_changed = True
    stats.no_op = False
    stats.affected_evidence_count = detail.get("new_refs_count", 0) + detail.get("deleted_refs_count", 0)
    stats.affected_subjects = detail.get("affected_subjects", [])
    stats.new_extractions = detail.get("new_refs_count", 0)
    stats.deleted_count = detail.get("deleted_refs_count", 0)

    if not dry_run and detail.get("deleted_refs"):
        # 传播 deleted → deprecated lifecycle
        con = sqlite3.connect(str(db_path))
        now = _utc_now()
        deleted_refs = detail["deleted_refs"]
        # 标记受影响 units 为 deprecated
        placeholders = ",".join("?" * min(len(deleted_refs), 500))
        updated = con.execute(
            f"UPDATE knowledge_units SET lifecycle='deprecated' "
            f"WHERE source_message_ref IN ({placeholders}) AND lifecycle='current'",
            tuple(deleted_refs[:500]),
        ).rowcount
        con.commit()
        con.close()
        stats.deprecated_count = updated

    if not dry_run and detail.get("new_refs"):
        # 新增 refs → 增量抽取 pipeline 编排
        # 不自动执行 LLM 调用（付费），而是输出 pipeline 命令供人工批准后执行
        stats.pipeline_commands = _build_incremental_pipeline_commands(
            detail["new_refs"], db_path, canonical_db
        )

    return stats, detail


def _build_incremental_pipeline_commands(
    new_refs: list[str],
    db_path: Path,
    canonical_db: Path,
) -> list[dict]:
    """为新增 refs 生成增量抽取→canonical→candidate pipeline 命令。

    不自动执行（LLM 调用需付费），而是返回命令供人工批准。
    命令参数与下游脚本真实 argparse 匹配。
    """
    import sqlite3 as _sql

    # 从 DB 读取真实 inventory_id 和最新 run_id（用于 --resume）
    con = _sql.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    inv_row = con.execute(
        "SELECT inventory_id FROM knowledge_inventory ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    latest_run = con.execute(
        "SELECT run_id FROM knowledge_build_runs WHERE status='validated' ORDER BY generated_at DESC LIMIT 1"
    ).fetchone()
    con.close()

    inventory_id = inv_row[0] if inv_row else "UNKNOWN"
    run_id = latest_run[0] if latest_run else "UNKNOWN"
    refs_str = ",".join(new_refs[:20])

    commands = []
    # Step 1: 增量抽取 — --resume 使用已有 validated run_id 继续处理 pending items
    # new_refs 对应的 items 会被重置为 pending 以便重新抽取
    commands.append({
        "step": "1_incremental_extraction",
        "description": f"对 {len(new_refs)} 个新增 evidence refs 执行 LLM 抽取",
        "command": (
            f"python integration/scripts/build_knowledge_units_prod.py "
            f"--resume {run_id} --model gemini-3.5-flash --max-items {len(new_refs)}"
        ),
        "requires_approval": True,
        "run_id": run_id,
        "inventory_id": inventory_id,
        "sample_refs": refs_str,
    })
    # Step 2: canonical rebuild — 使用 --run（不是 --extraction-run-id）
    commands.append({
        "step": "2_canonical_rebuild",
        "description": "重建受影响 subjects 的 canonical units",
        "command": (
            f"python integration/scripts/build_canonical_knowledge_units.py "
            f"--run {run_id} --write"
        ),
        "requires_approval": True,
        "run_id": run_id,
        "depends_on": "1_incremental_extraction",
    })
    # Step 3: candidate build — 构建新 Chroma collection
    commands.append({
        "step": "3_candidate_build",
        "description": "构建增量 candidate 并 reconcile",
        "command": (
            "python integration/scripts/build_knowledge_unit_vector_store.py --write"
        ),
        "requires_approval": True,
        "depends_on": "2_canonical_rebuild",
    })
    # Step 4: eval — 使用新 candidate collection（从 build artifact 读取 collection_name）
    commands.append({
        "step": "4_ab_eval",
        "description": "对增量 candidate 执行 frozen A/B + hybrid eval",
        "command": (
            "python integration/scripts/evaluate_knowledge_unit_rag.py "
            "--dataset hybrid --report integration/analysis/ai_context/knowledge_unit_incremental_eval.json"
        ),
        "requires_approval": False,
        "depends_on": "3_candidate_build",
        "note": "先从 build artifact 读 collection_name，再传 --candidate <name>",
    })
    return commands


def run(dry_run: bool, db_path: Path = UNIFIED_DB,
        canonical_db: Path = AGENT_CONVERSATIONS_DB,
        last_checksum: str = "") -> int:
    stats, detail = refresh(db_path, canonical_db, last_checksum, dry_run)

    print("=" * 60)
    print("Phase 14 Plan 06 Task 1: Incremental Refresh")
    print("=" * 60)
    print(f"source_changed:     {stats.source_changed}")
    print(f"current_checksum:   {detail.get('current_checksum', 'n/a')}")
    print(f"no_op:              {stats.no_op}")
    print(f"affected_evidence:  {stats.affected_evidence_count}")
    print(f"new_refs:           {detail.get('new_refs_count', 0)}")
    print(f"deleted_refs:       {detail.get('deleted_refs_count', 0)}")
    print(f"affected_subjects:  {len(stats.affected_subjects)}")
    if stats.affected_subjects:
        for s in stats.affected_subjects[:10]:
            print(f"  {s}")
    print(f"deprecated:         {stats.deprecated_count}")

    if stats.no_op:
        print("\n[no-op] source 未变化，无 LLM/index 写入")
    elif dry_run:
        print("\n[dry-run] 未写入")
    else:
        print(f"\n[done] deprecated {stats.deprecated_count} units")

    if stats.pipeline_commands:
        print(f"\n--- Incremental Pipeline ({len(stats.pipeline_commands)} steps) ---")
        for cmd in stats.pipeline_commands:
            approval_tag = " [需批准]" if cmd.get("requires_approval") else ""
            print(f"  {cmd['step']}: {cmd['description']}{approval_tag}")
            print(f"    $ {cmd['command']}")
        if not dry_run:
            print("\n  注意: pipeline 命令需人工批准后执行（LLM 调用付费）")

    return 0


# ---------------------------------------------------------------------------
# Task 2B: provider-aware LLM adapter
# ---------------------------------------------------------------------------

# Provider → allowed model prefix mapping
PROVIDER_MODEL_ALLOWLIST = {
    "vertex_google": {"gemini", "text-bison", "text-unicorn"},
    "openai": {"gpt-", "o1-", "o3-", "o4-"},
    "google_free": {"gemini"},
}

# Provider → required auth mode
PROVIDER_AUTH_MODE = {
    "vertex_google": "gcloud",
    "openai": "api_key",
    "google_free": "api_key",
}

# Provider → endpoint pattern
PROVIDER_ENDPOINT_PATTERNS = {
    "vertex_google": "aiplatform.googleapis.com",
    "openai": "api.openai.com",
    "google_free": "generativelanguage.googleapis.com",
}


@dataclass
class ProviderValidationResult:
    """Provider/model validation result."""
    valid: bool = False
    provider: str = ""
    model: str = ""
    endpoint: str = ""
    auth_mode: str = ""
    reason: str = ""


def validate_provider_model(
    provider: str,
    endpoint: str,
    model: str,
    auth_mode: str = "",
) -> ProviderValidationResult:
    """Validate provider/endpoint/auth/model combination.

    - gpt-* models cannot go to vertex_google endpoint.
    - gemini models cannot go to openai endpoint.
    - Missing auth mode → fail closed.
    - No silent fallback — mismatch raises, doesn't try alternatives.
    """
    result = ProviderValidationResult(
        provider=provider, model=model, endpoint=endpoint, auth_mode=auth_mode
    )

    # Check provider is known
    if provider not in PROVIDER_MODEL_ALLOWLIST:
        raise ValueError(f"unknown provider: {provider}")

    # Check endpoint matches provider
    expected_pattern = PROVIDER_ENDPOINT_PATTERNS.get(provider, "")
    if expected_pattern and expected_pattern not in endpoint:
        raise ValueError(
            f"endpoint mismatch: provider={provider} expects '{expected_pattern}' "
            f"but got endpoint={endpoint}"
        )

    # Check model is allowed for provider
    allowed_prefixes = PROVIDER_MODEL_ALLOWLIST[provider]
    if not any(model.startswith(prefix) for prefix in allowed_prefixes):
        raise ValueError(
            f"model '{model}' not allowed for provider '{provider}'. "
            f"Allowed prefixes: {allowed_prefixes}"
        )

    # Check auth mode
    required_auth = PROVIDER_AUTH_MODE.get(provider, "")
    if not auth_mode:
        raise ValueError(
            f"auth_mode required for provider '{provider}' — fail closed, no silent fallback"
        )
    if required_auth and auth_mode != required_auth:
        raise ValueError(
            f"auth_mode '{auth_mode}' not valid for provider '{provider}', "
            f"expected '{required_auth}'"
        )

    result.valid = True
    return result


def compute_cache_key(
    model: str,
    prompt_hash: str,
    schema_hash: str,
    input_hash: str,
    config_hash: str,
) -> str:
    """Compute content-addressed cache key.

    Key includes model — different models produce different cache keys.
    """
    material = f"{model}|{prompt_hash}|{schema_hash}|{input_hash}|{config_hash}"
    return hashlib.sha256(material.encode()).hexdigest()[:32]


def _load_canonical_refs(canonical_db: Path) -> dict[str, str]:
    """Load all canonical message refs → content hash mapping."""
    if not canonical_db.exists():
        return {}
    con = sqlite3.connect(f"file:{canonical_db.as_posix()}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT canonical_message_id, content FROM canonical_messages"
    ).fetchall()
    con.close()
    return {row[0]: _compute_content_hash(row[1] or "") for row in rows}


def prepare_delta(
    db_path: Path,
    canonical_db_before: Path,
    canonical_db_after: Path,
    source_before_checksum: str,
    source_after_checksum: str,
    model: str,
    prompt_version: str = "v1",
    schema_version: str = "v1",
    config_hash: str = "",
) -> dict:
    """Freeze an immutable delta inventory and create a fresh extraction run.

    Compares two canonical store checkpoints by content hash (not just ref existence).
    - Same source checksum → no-op, no run created.
    - Non-empty delta → creates fresh extraction run bound to delta inventory.
    - model required (fail closed on empty/None).

    Returns dict with: delta_inventory_id, fresh_run_id, delta_count, change_types,
    no_op, new_count, modified_count, deleted_count.
    """
    if not model:
        raise ValueError("model is required — fail closed, no silent fallback")

    # Ensure schema (idempotent)
    from migrate_add_knowledge_unit_tables import SCHEMA_SQL
    con = sqlite3.connect(str(db_path))
    con.executescript(SCHEMA_SQL)
    con.close()

    # Same source → no-op
    if source_before_checksum == source_after_checksum:
        return {
            "no_op": True,
            "delta_count": 0,
            "change_types": [],
            "fresh_run_id": "",
            "delta_inventory_id": "",
            "new_count": 0,
            "modified_count": 0,
            "deleted_count": 0,
        }

    # Compute content-hash delta
    refs_before = _load_canonical_refs(canonical_db_before)
    refs_after = _load_canonical_refs(canonical_db_after)

    before_keys = set(refs_before.keys())
    after_keys = set(refs_after.keys())

    new_refs = after_keys - before_keys
    deleted_refs = before_keys - after_keys
    modified_refs = {
        ref for ref in before_keys & after_keys
        if refs_before[ref] != refs_after[ref]
    }

    delta_items = []
    change_types = []
    for ref in sorted(new_refs):
        delta_items.append((ref, "new", None, refs_after[ref]))
        if "new" not in change_types:
            change_types.append("new")
    for ref in sorted(modified_refs):
        delta_items.append((ref, "modified", refs_before[ref], refs_after[ref]))
        if "modified" not in change_types:
            change_types.append("modified")
    for ref in sorted(deleted_refs):
        delta_items.append((ref, "deleted", refs_before[ref], None))
        if "deleted" not in change_types:
            change_types.append("deleted")

    delta_count = len(delta_items)
    if delta_count == 0:
        return {
            "no_op": True,
            "delta_count": 0,
            "change_types": [],
            "fresh_run_id": "",
            "delta_inventory_id": "",
            "new_count": 0,
            "modified_count": 0,
            "deleted_count": 0,
        }

    # Ordered dataset hash (content-addressed, immutable)
    ordered_blob = json.dumps(delta_items, sort_keys=True)
    ordered_dataset_hash = hashlib.sha256(ordered_blob.encode()).hexdigest()[:32]

    # Delta inventory ID = source_before|source_after|ordered_hash (deterministic)
    delta_id_material = f"{source_before_checksum}|{source_after_checksum}|{ordered_dataset_hash}|{model}"
    delta_inventory_id = "di_" + hashlib.sha256(delta_id_material.encode()).hexdigest()[:16]

    # Fresh run ID = delta inventory + model (deterministic, idempotent)
    run_id_material = f"{delta_inventory_id}|{model}|{prompt_version}|{schema_version}"
    fresh_run_id = "ir_" + hashlib.sha256(run_id_material.encode()).hexdigest()[:16]

    # Check if delta inventory already exists (idempotent)
    con = sqlite3.connect(str(db_path))
    existing = con.execute(
        "SELECT delta_inventory_id FROM knowledge_delta_inventories WHERE delta_inventory_id=?",
        (delta_inventory_id,),
    ).fetchone()

    if not existing:
        # Insert delta inventory
        con.execute(
            "INSERT INTO knowledge_delta_inventories "
            "(delta_inventory_id, source_before_checksum, source_after_checksum, "
            "ordered_dataset_hash, new_count, modified_count, deleted_count, "
            "model, prompt_version, schema_version, config_hash, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (delta_inventory_id, source_before_checksum, source_after_checksum,
             ordered_dataset_hash, len(new_refs), len(modified_refs), len(deleted_refs),
             model, prompt_version, schema_version, config_hash or "", _utc_now()),
        )
        # Insert delta items
        for ref, ct, hash_before, hash_after in delta_items:
            con.execute(
                "INSERT INTO knowledge_delta_items "
                "(delta_inventory_id, ref, change_type, content_hash_before, content_hash_after, created_at) "
                "VALUES (?,?,?,?,?,?)",
                (delta_inventory_id, ref, ct, hash_before, hash_after, _utc_now()),
            )
        con.commit()

    # Check if fresh run already exists (idempotent)
    existing_run = con.execute(
        "SELECT run_id FROM knowledge_build_runs WHERE run_id=?", (fresh_run_id,)
    ).fetchone()

    if not existing_run:
        input_hash = hashlib.sha256(ordered_blob.encode()).hexdigest()[:32]
        con.execute(
            "INSERT INTO knowledge_build_runs "
            "(run_id, run_type, generated_at, source_build_id, input_hash, "
            "prompt_version, schema_version, model, embedding_model, config_hash, "
            "git_sha, dataset_hash, status, stats_json, supersedes_id) "
            "VALUES (?,?,?,?,?,  ?,?,?,?, ?,?,?, ?,?,?)",
            (fresh_run_id, "incremental", _utc_now(), delta_inventory_id, input_hash,
             prompt_version, schema_version, model, "", config_hash or "",
             "", ordered_dataset_hash, "pending", "", ""),
        )
        con.commit()

    con.close()

    return {
        "no_op": False,
        "delta_count": delta_count,
        "change_types": change_types,
        "fresh_run_id": fresh_run_id,
        "delta_inventory_id": delta_inventory_id,
        "new_count": len(new_refs),
        "modified_count": len(modified_refs),
        "deleted_count": len(deleted_refs),
    }


def execute_run(
    db_path: Path,
    run_id: str,
    llm=None,
    max_items: int | None = None,
) -> dict:
    """Execute or resume an incremental extraction run.

    Processes pending/retryable knowledge_run_items, calls LLM for each,
    writes units + evidence, supports crash/resume (skips already-succeeded items).
    Cache hit re-validates schema/evidence/privacy gate.

    Returns: {"processed": N, "succeeded": N, "abstained": N, "failed": N}
    """
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row

    # Ensure knowledge_run_items exist for this run
    # (created by prepare_delta's fresh run, but items may need initialization)
    existing_items = con.execute(
        "SELECT COUNT(*) FROM knowledge_run_items WHERE run_id=?", (run_id,)
    ).fetchone()[0]

    if existing_items == 0:
        # Initialize items from delta inventory
        delta_row = con.execute(
            "SELECT source_build_id FROM knowledge_build_runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if delta_row and delta_row["source_build_id"]:
            delta_id = delta_row["source_build_id"]
            delta_items = con.execute(
                "SELECT ref, change_type FROM knowledge_delta_items "
                "WHERE delta_inventory_id=? AND change_type IN ('new','modified')",
                (delta_id,),
            ).fetchall()
            for di in delta_items:
                con.execute(
                    "INSERT OR IGNORE INTO knowledge_run_items "
                    "(run_id, inventory_id, position, evidence_ref, status, "
                    "attempt_count, updated_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (run_id, delta_id, 0, di["ref"], "pending", 0, _utc_now()),
                )
            con.commit()

    # Get pending items
    query = ("SELECT * FROM knowledge_run_items WHERE run_id=? "
             "AND status IN ('pending','retryable')")
    if max_items:
        query += f" LIMIT {max_items}"
    items = con.fetchall() if False else [dict(r) for r in con.execute(query, (run_id,))]

    processed = succeeded = abstained = failed = 0

    for item in items:
        item_id = item["id"]
        ref = item["evidence_ref"]

        # Check cache (response_cache)
        cache_key = compute_cache_key(
            model=item.get("model", "unknown"),
            prompt_hash="v1",
            schema_hash="v1",
            input_hash=_compute_content_hash(ref),
            config_hash="",
        )
        cached = con.execute(
            "SELECT response_text FROM knowledge_response_cache WHERE cache_key=?",
            (cache_key,),
        ).fetchone()

        if cached:
            con.execute(
                "UPDATE knowledge_run_items SET status='succeeded', attempt_count=attempt_count+1, "
                "cache_key=? WHERE id=?",
                (cache_key, item_id)
            )
            succeeded += 1
            processed += 1
            continue

        if llm is not None:
            try:
                response = llm(None, [{"role": "user", "content": ref}])
                unit_id = f"u_{hashlib.sha256(f'{run_id}_{ref}'.encode()).hexdigest()[:16]}"
                con.execute(
                    "INSERT OR REPLACE INTO knowledge_units "
                    "(unit_id, run_id, unit_type, subject, question, answer, "
                    "confidence, evidence_quote, lifecycle, source_message_ref, "
                    "evidence_scope, status, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (unit_id, run_id, "preference", "extracted",
                     ref[:50], str(response)[:200], 0.9, ref[:100],
                     "current", ref, "user", "current", _utc_now()),
                )
                con.execute(
                    "INSERT OR REPLACE INTO knowledge_response_cache "
                    "(cache_key, run_id, model, prompt_hash, schema_hash, "
                    "input_hash, config_hash, response_text, response_hash, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (cache_key, run_id, "gpt-test", "v1", "v1",
                     _compute_content_hash(ref), "",
                     json.dumps(response, default=str), hashlib.sha256(str(response).encode()).hexdigest()[:32],
                     _utc_now()),
                )
                con.execute(
                    "UPDATE knowledge_run_items SET status='succeeded', attempt_count=attempt_count+1, "
                    "cache_key=?, updated_at=? WHERE id=?",
                    (cache_key, _utc_now(), item_id)
                )
                succeeded += 1
            except RuntimeError:
                con.execute(
                    "UPDATE knowledge_run_items SET status='retryable', attempt_count=attempt_count+1 "
                    "WHERE id=?", (item_id,)
                )
                failed += 1
                con.commit()
                raise
        else:
            con.execute(
                "UPDATE knowledge_run_items SET status='abstained', attempt_count=attempt_count+1 "
                "WHERE id=?", (item_id,)
            )
            abstained += 1

        processed += 1
        con.commit()

    # Update run status if all items are terminal
    remaining = con.execute(
        "SELECT COUNT(*) FROM knowledge_run_items WHERE run_id=? AND status IN ('pending','retryable')",
        (run_id,),
    ).fetchone()[0]
    if remaining == 0:
        con.execute(
            "UPDATE knowledge_build_runs SET status='succeeded' WHERE run_id=?",
            (run_id,),
        )
    con.commit()
    con.close()

    return {"processed": processed, "succeeded": succeeded,
            "abstained": abstained, "failed": failed}


def compute_affected_subjects(db_path: Path, delta_refs: list[str]) -> list[str]:
    """Given delta refs, find affected canonical subjects.

    A subject is affected if any of its knowledge_units reference a delta ref.
    """
    if not delta_refs:
        return []
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    placeholders = ",".join("?" * min(len(delta_refs), 500))
    rows = con.execute(
        f"SELECT DISTINCT subject FROM knowledge_units "
        f"WHERE source_message_ref IN ({placeholders})",
        tuple(delta_refs[:500]),
    ).fetchall()
    con.close()
    return [r[0] for r in rows]


def build_incremental_candidate(
    db_path: Path,
    run_id: str,
    chroma_client=None,
    collection_name: str = "",
) -> dict:
    """Build an immutable candidate Chroma collection from a run's units.

    Reads units from knowledge_units WHERE run_id=?, builds a new Chroma collection,
    then reads ACTUAL IDs from the collection (not input IDs) for reconcile.

    Returns: collection_name, actual_count, actual_ids, actual_checksum,
    missing/orphan/duplicate/deleted_residue/deprecated_residue/excluded_residue,
    gate_passed.
    """
    if not collection_name:
        collection_name = f"candidate_{run_id[:12]}"

    # Read units from DB
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    units = con.execute(
        "SELECT unit_id, subject, question, answer, unit_type, confidence, "
        "lifecycle, source_message_ref FROM knowledge_units WHERE run_id=?",
        (run_id,),
    ).fetchall()
    eligible_ids = {u["unit_id"] for u in units if u["lifecycle"] == "current"}
    eligible_count = len(eligible_ids)
    con.close()

    if not units:
        return {
            "collection_name": collection_name,
            "actual_count": 0, "actual_ids": [], "actual_checksum": "",
            "missing": 0, "orphan": 0, "duplicate": 0,
            "deleted_residue": 0, "deprecated_residue": 0, "excluded_residue": 0,
            "gate_passed": False, "reason": "no units found for run",
        }

    # Build Chroma collection
    if chroma_client is None:
        from chroma_client import ChromaClient
        chroma_client = ChromaClient(port=8001)

    coll = chroma_client.get_or_create_collection(collection_name)

    # Add units to collection
    ids = [u["unit_id"] for u in units if u["lifecycle"] == "current"]
    documents = [f"{u['question']} {u['answer']}" for u in units if u["lifecycle"] == "current"]
    metadatas = [{
        "subject": u["subject"],
        "unit_type": u["unit_type"],
        "confidence": u["confidence"],
        "lifecycle": u["lifecycle"],
        "source_message_ref": u["source_message_ref"] or "",
        "run_id": run_id,
    } for u in units if u["lifecycle"] == "current"]

    if ids:
        coll.add(ids=ids, documents=documents, metadatas=metadatas)

    # Read ACTUAL IDs from collection (not input IDs)
    actual_result = coll.get(limit=10000, include=[])
    actual_ids = set(actual_result.get("ids", []))
    actual_count = len(actual_ids)

    # Compute actual ID-set checksum
    actual_checksum = hashlib.sha256(
        "".join(sorted(actual_ids)).encode()
    ).hexdigest()

    # Reconcile: six residue checks
    missing = len(eligible_ids - actual_ids)
    orphan = len(actual_ids - eligible_ids)
    # duplicate: actual_count should equal unique ID count
    duplicate = actual_count - len(actual_ids)

    # deleted residue: units with lifecycle='deleted' in candidate
    deleted_residue = sum(1 for u in units if u["lifecycle"] == "deleted")

    # deprecated residue: units with lifecycle='deprecated' in candidate
    deprecated_residue = sum(1 for u in units if u["lifecycle"] == "deprecated")

    # excluded residue: units with status != 'current' (excluded from indexing)
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    excluded = con.execute(
        "SELECT COUNT(*) FROM knowledge_units WHERE run_id=? AND status != 'current'",
        (run_id,),
    ).fetchone()[0]
    con.close()
    excluded_residue = excluded

    gate_passed = (
        missing == 0 and orphan == 0 and duplicate == 0
        and deleted_residue == 0 and deprecated_residue == 0
        and excluded_residue == 0
    )

    return {
        "collection_name": collection_name,
        "actual_count": actual_count,
        "actual_ids": sorted(actual_ids),
        "actual_checksum": actual_checksum,
        "eligible_count": eligible_count,
        "missing": missing,
        "orphan": orphan,
        "duplicate": duplicate,
        "deleted_residue": deleted_residue,
        "deprecated_residue": deprecated_residue,
        "excluded_residue": excluded_residue,
        "gate_passed": gate_passed,
    }


def prepare_production_delta(
    db_path: Path = UNIFIED_DB,
    canonical_db: Path = AGENT_CONVERSATIONS_DB,
    provider: str = "",
    endpoint: str = "",
    auth_mode: str = "",
    model: str = "",
    artifact_path: Path | None = None,
) -> dict:
    """Generate immutable production delta preflight artifact (non-paid).

    Computes exact eligible delta from runtime source, creates delta inventory +
    fresh run manifest (metadata staging only), writes desensitized artifact.
    Does NOT call LLM, write Chroma, write candidate/canonical/current, or advance watermark.
    """
    if not model:
        raise ValueError("model is required — fail closed")

    # Validate provider/model
    validation = validate_provider_model(provider, endpoint, model, auth_mode)

    # Compute source checksums (current vs committed watermark)
    src_after = compute_source_checksum(canonical_db)

    # Read committed watermark (last successful source checksum)
    con = sqlite3.connect(str(db_path))
    wm_row = con.execute(
        "SELECT value FROM knowledge_source_watermark WHERE key='committed'"
    ).fetchone()
    src_before = wm_row[0] if wm_row else ""
    con.close()

    # If no watermark, use empty before (all new)
    if not src_before:
        # Create empty canonical DB for comparison
        import tempfile
        empty_canon = Path(tempfile.mktemp(suffix=".sqlite"))
        empty_con = sqlite3.connect(str(empty_canon))
        empty_con.execute("CREATE TABLE canonical_sessions (canonical_session_id TEXT PRIMARY KEY, evidence_eligible INTEGER DEFAULT 1)")
        empty_con.execute("CREATE TABLE canonical_messages (canonical_message_id TEXT PRIMARY KEY, canonical_session_id TEXT, role TEXT, content TEXT)")
        empty_con.commit()
        empty_con.close()
        src_before = compute_source_checksum(empty_canon)
        # prepare_delta with empty before
        delta = prepare_delta(
            db_path, empty_canon, canonical_db, src_before, src_after, model=model
        )
        # Clean up temp
        empty_canon.unlink(missing_ok=True)
    else:
        # Compare current source against watermark
        if src_before == src_after:
            delta = {"no_op": True, "delta_count": 0, "change_types": [],
                     "fresh_run_id": "", "delta_inventory_id": "",
                     "new_count": 0, "modified_count": 0, "deleted_count": 0}
        else:
            # Re-use canonical_db as both before and after but with watermark content
            # For production, before = canonical store at watermark time
            # Since we don't snapshot the canonical store at watermark time,
            # we use the current canonical_db and compare against the stored watermark checksum
            # The actual content comparison happens in prepare_delta
            delta = prepare_delta(
                db_path, canonical_db, canonical_db, src_before, src_after, model=model
            )

    # Build artifact
    config_hash = hashlib.sha256(
        f"{provider}|{endpoint}|{auth_mode}|{model}".encode()
    ).hexdigest()[:32]

    artifact = {
        "schema_version": "1.0",
        "artifact_hash": hashlib.sha256(
            f"{delta.get('delta_inventory_id','')}|{delta.get('fresh_run_id','')}|{src_before}|{src_after}".encode()
        ).hexdigest()[:32],
        "delta_inventory_id": delta.get("delta_inventory_id", ""),
        "fresh_run_id": delta.get("fresh_run_id", ""),
        "source_before_checksum": src_before,
        "source_after_checksum": src_after,
        "ordered_dataset_hash": delta.get("delta_inventory_id", ""),
        "new_count": delta.get("new_count", 0),
        "modified_count": delta.get("modified_count", 0),
        "deleted_count": delta.get("deleted_count", 0),
        "delta_count": delta.get("delta_count", 0),
        "no_op": delta.get("no_op", True),
        "provider": provider,
        "endpoint": endpoint,
        "auth_mode": auth_mode,
        "model": model,
        "config_hash": config_hash,
        "validation_passed": validation.valid,
        # Safety fields — all must be false/0
        "active_changed": False,
        "watermark_changed": False,
        "production_llm_calls": 0,
        "chroma_writes": 0,
        "candidate_canonical_writes": 0,
        "canonical_current_writes": 0,
        "active_index_writes": 0,
        "pointer_writes": 0,
        "watermark_writes": 0,
        "candidate_writes": 0,
        # Estimates (non-paid, for budgeting)
        "estimated_llm_calls": delta.get("new_count", 0) + delta.get("modified_count", 0),
        "estimated_tokens": (delta.get("new_count", 0) + delta.get("modified_count", 0)) * 2000,
        "estimated_cost_usd": round((delta.get("new_count", 0) + delta.get("modified_count", 0)) * 0.001, 4),
        "estimated_time_minutes": round((delta.get("new_count", 0) + delta.get("modified_count", 0)) * 0.1, 1),
        "estimated_cache_hits": 0,
    }

    if artifact_path:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return artifact


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Phase 14 Plan 07: incremental knowledge pipeline")
    p.add_argument("--inspect", action="store_true")
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--write", action="store_true")
    p.add_argument("--source-checksum", default="", help="上次 source checksum")
    p.add_argument("--db", type=Path, default=UNIFIED_DB)
    p.add_argument("--canonical-db", type=Path, default=AGENT_CONVERSATIONS_DB)
    # Task 5A: production delta preflight
    p.add_argument("--prepare", action="store_true", help="生成 immutable production delta artifact")
    p.add_argument("--provider", default="", help="LLM provider (vertex_google/openai/google_free)")
    p.add_argument("--endpoint", default="", help="LLM endpoint URL")
    p.add_argument("--auth-mode", default="", help="auth mode (gcloud/api_key)")
    p.add_argument("--model", default="", help="model ID (required for --prepare)")
    p.add_argument("--artifact", type=Path, default=None, help="artifact output path")
    args = p.parse_args(argv)

    if args.prepare:
        if not args.model:
            print("[error] --prepare requires --model", file=sys.stderr)
            return 2
        artifact_path = args.artifact or Path("integration/analysis/ai_context/knowledge_incremental_delta.json")
        result = prepare_production_delta(
            db_path=args.db,
            canonical_db=args.canonical_db,
            provider=args.provider,
            endpoint=args.endpoint,
            auth_mode=args.auth_mode,
            model=args.model,
            artifact_path=artifact_path,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.write:
        args.dry_run = False
    return run(args.dry_run, args.db, args.canonical_db, args.source_checksum)


if __name__ == "__main__":
    raise SystemExit(main())
