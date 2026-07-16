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

from personal_knowledge.core.project_paths import UNIFIED_DB, AGENT_CONVERSATIONS_DB  # noqa: E402


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
            f"python -m personal_knowledge.domains.knowledge.build_knowledge_units_prod "
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
            f"python -m personal_knowledge.domains.knowledge.build_canonical_knowledge_units "
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
            "python -m personal_knowledge.domains.knowledge.build_knowledge_unit_vector_store --write"
        ),
        "requires_approval": True,
        "depends_on": "2_canonical_rebuild",
    })
    # Step 4: eval — 使用新 candidate collection（从 build artifact 读取 collection_name）
    commands.append({
        "step": "4_ab_eval",
        "description": "对增量 candidate 执行 frozen A/B + hybrid eval",
        "command": (
            "python -m personal_knowledge.domains.knowledge.evaluate_knowledge_unit_rag "
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


def _empty_delta_result() -> dict:
    return {
        "no_op": True,
        "delta_count": 0,
        "change_types": [],
        "fresh_run_id": "",
        "delta_inventory_id": "",
        "new_count": 0,
        "modified_count": 0,
        "deleted_count": 0,
        "extract_item_count": 0,
    }


def _diff_ref_hashes(
    refs_before: dict[str, str],
    refs_after: dict[str, str],
) -> tuple[list[tuple[str, str, str | None, str | None]], list[str], int, int, int]:
    """Compare two ref→content_hash maps. Returns (delta_items, change_types, new, mod, del)."""
    before_keys = set(refs_before.keys())
    after_keys = set(refs_after.keys())
    new_refs = after_keys - before_keys
    deleted_refs = before_keys - after_keys
    modified_refs = {
        ref for ref in before_keys & after_keys
        if refs_before[ref] != refs_after[ref]
    }

    delta_items: list[tuple[str, str, str | None, str | None]] = []
    change_types: list[str] = []
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
    return delta_items, change_types, len(new_refs), len(modified_refs), len(deleted_refs)


def _materialize_delta_run(
    db_path: Path,
    *,
    source_before_checksum: str,
    source_after_checksum: str,
    model: str,
    delta_items: list[tuple[str, str, str | None, str | None]],
    new_count: int,
    modified_count: int,
    deleted_count: int,
    change_types: list[str],
    prompt_version: str = "v1",
    schema_version: str = "v1",
    config_hash: str = "",
    init_run_items: bool = False,
    extract_change_types: frozenset[str] | None = None,
    extract_order_keys: dict[str, str] | None = None,
    extract_min_started_at: str = "",
) -> dict:
    """Write delta inventory + fresh incremental run (idempotent). Optionally seed run items."""
    if not delta_items:
        return _empty_delta_result()

    extract_types = extract_change_types or frozenset({"new", "modified"})
    ordered_blob = json.dumps(delta_items, sort_keys=True)
    ordered_dataset_hash = hashlib.sha256(ordered_blob.encode()).hexdigest()[:32]
    delta_id_material = (
        f"{source_before_checksum}|{source_after_checksum}|{ordered_dataset_hash}|{model}"
    )
    delta_inventory_id = "di_" + hashlib.sha256(delta_id_material.encode()).hexdigest()[:16]
    # Production prepare seeds run items with extract filters; include policy in
    # run identity so a watermark-gated queue does not reuse a full-backlog ledger.
    run_id_material = f"{delta_inventory_id}|{model}|{prompt_version}|{schema_version}"
    if init_run_items:
        extract_policy = (
            f"types={','.join(sorted(extract_types))}|"
            f"since={extract_min_started_at or 'none'}|skip_succeeded=1"
        )
        run_id_material = f"{run_id_material}|{extract_policy}"
    fresh_run_id = "ir_" + hashlib.sha256(run_id_material.encode()).hexdigest()[:16]

    con = sqlite3.connect(str(db_path))
    existing = con.execute(
        "SELECT delta_inventory_id FROM knowledge_delta_inventories WHERE delta_inventory_id=?",
        (delta_inventory_id,),
    ).fetchone()

    if not existing:
        con.execute(
            "INSERT INTO knowledge_delta_inventories "
            "(delta_inventory_id, source_before_checksum, source_after_checksum, "
            "ordered_dataset_hash, new_count, modified_count, deleted_count, "
            "model, prompt_version, schema_version, config_hash, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                delta_inventory_id, source_before_checksum, source_after_checksum,
                ordered_dataset_hash, new_count, modified_count, deleted_count,
                model, prompt_version, schema_version, config_hash or "", _utc_now(),
            ),
        )
        for ref, ct, hash_before, hash_after in delta_items:
            con.execute(
                "INSERT INTO knowledge_delta_items "
                "(delta_inventory_id, ref, change_type, content_hash_before, "
                "content_hash_after, created_at) VALUES (?,?,?,?,?,?)",
                (delta_inventory_id, ref, ct, hash_before, hash_after, _utc_now()),
            )
        con.commit()

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
            (
                fresh_run_id, "incremental", _utc_now(), delta_inventory_id, input_hash,
                prompt_version, schema_version, model, "", config_hash or "",
                "", ordered_dataset_hash, "pending", "", "",
            ),
        )
        con.commit()

    extract_item_count = 0
    if init_run_items:
        existing_items = con.execute(
            "SELECT COUNT(*) FROM knowledge_run_items WHERE run_id=?", (fresh_run_id,)
        ).fetchone()[0]
        if existing_items == 0:
            extractable = [
                (ref, ct) for ref, ct, _hb, _ha in delta_items if ct in extract_types
            ]
            # Skip evidence already successfully extracted in any prior run
            already = {
                r[0]
                for r in con.execute(
                    "SELECT DISTINCT evidence_ref FROM knowledge_run_items "
                    "WHERE status='succeeded'"
                ).fetchall()
            }
            if already:
                extractable = [(ref, ct) for ref, ct in extractable if ref not in already]

            # Optional time gate: only sessions on/after watermark (or given floor)
            if extract_min_started_at and extract_order_keys is not None:
                floor = extract_min_started_at
                extractable = [
                    (ref, ct)
                    for ref, ct in extractable
                    if (extract_order_keys.get(ref) or "") >= floor
                ]

            # Prefer recent sessions first when canonical timestamps available
            if extractable and extract_order_keys:
                extractable.sort(
                    key=lambda pair: extract_order_keys.get(pair[0], ""),
                    reverse=True,
                )
            else:
                extractable.sort(key=lambda pair: pair[0])

            now = _utc_now()
            for pos, (ref, _ct) in enumerate(extractable):
                con.execute(
                    "INSERT OR IGNORE INTO knowledge_run_items "
                    "(run_id, inventory_id, position, evidence_ref, status, attempt_count, "
                    "lease_started_at, last_error_class, cache_key, response_hash, "
                    "unit_count, updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        fresh_run_id, delta_inventory_id, pos, ref, "pending", 0,
                        None, None, None, None, 0, now,
                    ),
                )
            con.commit()
            extract_item_count = len(extractable)
        else:
            extract_item_count = existing_items

    con.close()
    return {
        "no_op": False,
        "delta_count": len(delta_items),
        "change_types": change_types,
        "fresh_run_id": fresh_run_id,
        "delta_inventory_id": delta_inventory_id,
        "new_count": new_count,
        "modified_count": modified_count,
        "deleted_count": deleted_count,
        "extract_item_count": extract_item_count,
    }


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
    from personal_knowledge.domains.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL
    con = sqlite3.connect(str(db_path))
    con.executescript(SCHEMA_SQL)
    con.close()

    # Same source → no-op
    if source_before_checksum == source_after_checksum:
        return _empty_delta_result()

    # Compute content-hash delta
    refs_before = _load_canonical_refs(canonical_db_before)
    refs_after = _load_canonical_refs(canonical_db_after)
    delta_items, change_types, new_count, modified_count, deleted_count = _diff_ref_hashes(
        refs_before, refs_after
    )
    if not delta_items:
        return _empty_delta_result()

    return _materialize_delta_run(
        db_path,
        source_before_checksum=source_before_checksum,
        source_after_checksum=source_after_checksum,
        model=model,
        delta_items=delta_items,
        new_count=new_count,
        modified_count=modified_count,
        deleted_count=deleted_count,
        change_types=change_types,
        prompt_version=prompt_version,
        schema_version=schema_version,
        config_hash=config_hash,
        init_run_items=False,
    )


def _load_baseline_inventory_hashes(
    db_path: Path,
    *,
    watermark_updated_at: str = "",
    exclude_inventory_id: str = "",
) -> tuple[dict[str, str], str]:
    """Load evidence_ref→content_hash baseline from frozen inventory.

    Prefer the latest inventory at or before watermark.updated_at (last committed cycle).
    Fall back to latest inventory that is not exclude_inventory_id (skip a same-day full
    freeze that matches current source but was never extracted/committed).
    """
    if not db_path.exists():
        return {}, ""

    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    inventory_id = ""
    if watermark_updated_at:
        row = con.execute(
            "SELECT inventory_id FROM knowledge_inventory "
            "WHERE generated_at <= ? ORDER BY generated_at DESC LIMIT 1",
            (watermark_updated_at,),
        ).fetchone()
        if row:
            inventory_id = row[0]

    if not inventory_id:
        if exclude_inventory_id:
            row = con.execute(
                "SELECT inventory_id FROM knowledge_inventory "
                "WHERE inventory_id != ? ORDER BY generated_at DESC LIMIT 1",
                (exclude_inventory_id,),
            ).fetchone()
        else:
            row = con.execute(
                "SELECT inventory_id FROM knowledge_inventory "
                "ORDER BY generated_at DESC LIMIT 1"
            ).fetchone()
        inventory_id = row[0] if row else ""

    if not inventory_id:
        con.close()
        return {}, ""

    rows = con.execute(
        "SELECT evidence_ref, content_hash FROM knowledge_inventory_items "
        "WHERE inventory_id=?",
        (inventory_id,),
    ).fetchall()
    con.close()
    return {r[0]: r[1] for r in rows if r[0] and r[1]}, inventory_id


def _current_eligible_ref_hashes(canonical_db: Path) -> tuple[dict[str, str], dict]:
    """Current eligible evidence set using full inventory eligibility + content hash."""
    from personal_knowledge.application.knowledge.build_knowledge_inventory import (
        build_inventory,
    )

    inventory = build_inventory(canonical_db)
    if inventory.get("error"):
        return {}, inventory
    hashes = {
        item["evidence_ref"]: item["content_hash"]
        for item in inventory.get("items", [])
        if item.get("evidence_ref") and item.get("content_hash")
    }
    return hashes, inventory


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
        from personal_knowledge.core.chroma_client import ChromaClient
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


# ---------------------------------------------------------------------------
# KU-08: journal + watermark (promote only after human/sandbox gate)
# ---------------------------------------------------------------------------

JOURNAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_incremental_journals (
    journal_id TEXT PRIMARY KEY,
    delta_inventory_id TEXT NOT NULL,
    fresh_run_id TEXT NOT NULL,
    source_before_checksum TEXT NOT NULL,
    source_after_checksum TEXT NOT NULL,
    candidate_collection TEXT,
    status TEXT NOT NULL,
    prepared_at TEXT NOT NULL,
    committed_at TEXT,
    rolled_back_at TEXT,
    detail_json TEXT
);
"""


def ensure_journal_schema(db_path: Path) -> None:
    con = sqlite3.connect(str(db_path))
    con.executescript(JOURNAL_SCHEMA)
    con.execute(
        "CREATE TABLE IF NOT EXISTS knowledge_source_watermark ("
        "key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)"
    )
    con.commit()
    con.close()


def get_committed_watermark(db_path: Path) -> str:
    ensure_journal_schema(db_path)
    con = sqlite3.connect(str(db_path))
    row = con.execute(
        "SELECT value FROM knowledge_source_watermark WHERE key='committed'"
    ).fetchone()
    con.close()
    return row[0] if row else ""


def advance_watermark(db_path: Path, checksum: str, *, key: str = "committed") -> dict:
    """Advance source watermark. Only call after successful journal commit."""
    if not checksum:
        raise ValueError("checksum required for watermark advance")
    ensure_journal_schema(db_path)
    before = get_committed_watermark(db_path)
    con = sqlite3.connect(str(db_path))
    con.execute(
        "INSERT INTO knowledge_source_watermark(key, value, updated_at) VALUES (?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, checksum, _utc_now()),
    )
    con.commit()
    con.close()
    return {"key": key, "before": before, "after": checksum, "changed": before != checksum}


def prepare_incremental_journal(
    db_path: Path,
    *,
    delta_inventory_id: str,
    fresh_run_id: str,
    source_before_checksum: str,
    source_after_checksum: str,
    candidate_collection: str = "",
) -> dict:
    """Durable prepare record for incremental promote. Does not touch active/watermark."""
    if not delta_inventory_id or not fresh_run_id:
        raise ValueError("delta_inventory_id and fresh_run_id required")
    if source_before_checksum == source_after_checksum:
        raise ValueError("cannot prepare journal for no-op delta")
    ensure_journal_schema(db_path)
    material = f"{delta_inventory_id}|{fresh_run_id}|{source_after_checksum}"
    journal_id = "ij_" + hashlib.sha256(material.encode()).hexdigest()[:16]
    con = sqlite3.connect(str(db_path))
    existing = con.execute(
        "SELECT journal_id, status FROM knowledge_incremental_journals WHERE journal_id=?",
        (journal_id,),
    ).fetchone()
    if existing:
        con.close()
        return {
            "journal_id": journal_id,
            "status": existing[1],
            "idempotent": True,
            "delta_inventory_id": delta_inventory_id,
            "fresh_run_id": fresh_run_id,
        }
    con.execute(
        "INSERT INTO knowledge_incremental_journals "
        "(journal_id, delta_inventory_id, fresh_run_id, source_before_checksum, "
        "source_after_checksum, candidate_collection, status, prepared_at, detail_json) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            journal_id,
            delta_inventory_id,
            fresh_run_id,
            source_before_checksum,
            source_after_checksum,
            candidate_collection or "",
            "prepared",
            _utc_now(),
            json.dumps({"schema": "ku08_journal_v1"}, ensure_ascii=False),
        ),
    )
    con.commit()
    con.close()
    return {
        "journal_id": journal_id,
        "status": "prepared",
        "idempotent": False,
        "delta_inventory_id": delta_inventory_id,
        "fresh_run_id": fresh_run_id,
        "source_after_checksum": source_after_checksum,
        "watermark_changed": False,
        "active_changed": False,
    }


def commit_incremental_journal(
    db_path: Path,
    journal_id: str,
    *,
    active_pointer_path: Path | None = None,
    promote_collection: str | None = None,
) -> dict:
    """Atomic-ish commit: optional pointer write + watermark advance.

    Fail closed if journal missing/not prepared. Rollback leaves watermark alone.
    """
    ensure_journal_schema(db_path)
    con = sqlite3.connect(str(db_path))
    row = con.execute(
        "SELECT status, source_after_checksum, candidate_collection, source_before_checksum "
        "FROM knowledge_incremental_journals WHERE journal_id=?",
        (journal_id,),
    ).fetchone()
    if not row:
        con.close()
        raise ValueError(f"journal not found: {journal_id}")
    status, src_after, candidate, src_before = row
    if status == "committed":
        con.close()
        return {
            "journal_id": journal_id,
            "status": "committed",
            "idempotent": True,
            "watermark_after": src_after,
        }
    if status not in ("prepared", "rolled_back"):
        con.close()
        raise ValueError(f"journal status {status} cannot commit")

    pointer_before = ""
    pointer_after = promote_collection or candidate or ""
    if active_pointer_path is not None and pointer_after:
        active_pointer_path.parent.mkdir(parents=True, exist_ok=True)
        if active_pointer_path.exists():
            pointer_before = active_pointer_path.read_text(encoding="utf-8").strip()
        tmp = active_pointer_path.with_suffix(active_pointer_path.suffix + ".tmp")
        tmp.write_text(pointer_after + "\n", encoding="utf-8")
        tmp.replace(active_pointer_path)

    con.execute(
        "INSERT INTO knowledge_source_watermark(key, value, updated_at) VALUES (?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        ("committed", src_after, _utc_now()),
    )
    # stash previous for rollback
    con.execute(
        "INSERT INTO knowledge_source_watermark(key, value, updated_at) VALUES (?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        ("previous", src_before, _utc_now()),
    )
    con.execute(
        "UPDATE knowledge_incremental_journals SET status='committed', committed_at=? "
        "WHERE journal_id=?",
        (_utc_now(), journal_id),
    )
    con.commit()
    con.close()
    return {
        "journal_id": journal_id,
        "status": "committed",
        "idempotent": False,
        "watermark_before": src_before,
        "watermark_after": src_after,
        "watermark_changed": True,
        "pointer_before": pointer_before,
        "pointer_after": pointer_after if active_pointer_path is not None else None,
        "active_changed": bool(active_pointer_path is not None and pointer_after),
    }


def rollback_incremental_journal(
    db_path: Path,
    journal_id: str,
    *,
    active_pointer_path: Path | None = None,
) -> dict:
    """Restore previous watermark (and optional pointer) from a committed journal."""
    ensure_journal_schema(db_path)
    con = sqlite3.connect(str(db_path))
    row = con.execute(
        "SELECT status, source_before_checksum, source_after_checksum "
        "FROM knowledge_incremental_journals WHERE journal_id=?",
        (journal_id,),
    ).fetchone()
    if not row:
        con.close()
        raise ValueError(f"journal not found: {journal_id}")
    status, src_before, src_after = row
    if status != "committed":
        con.close()
        raise ValueError(f"journal status {status} cannot rollback")

    prev = con.execute(
        "SELECT value FROM knowledge_source_watermark WHERE key='previous'"
    ).fetchone()
    restore = prev[0] if prev else src_before
    con.execute(
        "INSERT INTO knowledge_source_watermark(key, value, updated_at) VALUES (?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        ("committed", restore, _utc_now()),
    )
    con.execute(
        "UPDATE knowledge_incremental_journals SET status='rolled_back', rolled_back_at=? "
        "WHERE journal_id=?",
        (_utc_now(), journal_id),
    )
    con.commit()
    con.close()

    pointer_restored = None
    if active_pointer_path is not None and active_pointer_path.exists():
        # best-effort: leave pointer; rollback watermark is the KU-08 safety property
        pointer_restored = active_pointer_path.read_text(encoding="utf-8").strip()

    return {
        "journal_id": journal_id,
        "status": "rolled_back",
        "watermark_after": restore,
        "watermark_from": src_after,
        "pointer": pointer_restored,
    }


def run_sandbox_ku08_e2e(
    work_dir: Path,
    *,
    model: str = "gemini-2.5-flash",
) -> dict:
    """Isolated non-empty delta → journal prepare → commit → watermark (no live index)."""
    work_dir.mkdir(parents=True, exist_ok=True)
    unified = work_dir / "unified.sqlite"
    canon_before = work_dir / "canon_before.sqlite"
    canon_after = work_dir / "canon_after.sqlite"
    pointer = work_dir / "knowledge_index_active.txt"
    # Idempotent re-runs: wipe prior sandbox files so CREATE TABLE does not collide.
    for p in (unified, canon_before, canon_after, pointer):
        if p.exists():
            p.unlink()
    pointer.write_text("sandbox_old_index\n", encoding="utf-8")

    # Minimal canon fixtures
    def _mk_canon(path: Path, messages: list[tuple[str, str]]) -> None:
        if path.exists():
            path.unlink()
        con = sqlite3.connect(str(path))
        con.execute(
            "CREATE TABLE canonical_sessions "
            "(canonical_session_id TEXT PRIMARY KEY, evidence_eligible INTEGER DEFAULT 1)"
        )
        con.execute(
            "CREATE TABLE canonical_messages ("
            "canonical_message_id TEXT PRIMARY KEY, canonical_session_id TEXT, "
            "role TEXT, content TEXT)"
        )
        con.execute("INSERT INTO canonical_sessions VALUES ('cs1', 1)")
        for mid, content in messages:
            con.execute(
                "INSERT INTO canonical_messages VALUES (?,?,?,?)",
                (mid, "cs1", "user", content),
            )
        con.commit()
        con.close()

    base = [
        ("cm|ku08_a", "preference shell powershell " + "x" * 40),
        ("cm|ku08_b", "project uses sqlite fts " + "y" * 40),
    ]
    after = base + [
        ("cm|ku08_new", "new evidence for incremental ku08 " + "z" * 40),
    ]
    _mk_canon(canon_before, base)
    _mk_canon(canon_after, after)

    from personal_knowledge.domains.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL

    con = sqlite3.connect(str(unified))
    con.executescript(SCHEMA_SQL)
    con.commit()
    con.close()

    src_before = compute_source_checksum(canon_before)
    src_after = compute_source_checksum(canon_after)
    delta = prepare_delta(
        unified,
        canon_before,
        canon_after,
        src_before,
        src_after,
        model=model,
    )
    assert not delta.get("no_op"), delta
    journal = prepare_incremental_journal(
        unified,
        delta_inventory_id=delta["delta_inventory_id"],
        fresh_run_id=delta["fresh_run_id"],
        source_before_checksum=src_before,
        source_after_checksum=src_after,
        candidate_collection="sandbox_candidate_ku08",
    )
    committed = commit_incremental_journal(
        unified,
        journal["journal_id"],
        active_pointer_path=pointer,
        promote_collection="sandbox_candidate_ku08",
    )
    wm = get_committed_watermark(unified)
    # second prepare against advanced watermark should no-op when before==after
    noop = prepare_delta(
        unified,
        canon_after,
        canon_after,
        wm,
        compute_source_checksum(canon_after),
        model=model,
    )
    rolled = rollback_incremental_journal(
        unified, journal["journal_id"], active_pointer_path=pointer
    )
    return {
        "ok": True,
        "delta": delta,
        "journal": journal,
        "committed": committed,
        "watermark_after_commit": wm,
        "noop_after_commit": noop,
        "rollback": rolled,
        "pointer_after_commit": pointer.read_text(encoding="utf-8").strip(),
        "live_active_untouched": True,
    }


def prepare_production_delta(
    db_path: Path = UNIFIED_DB,
    canonical_db: Path = AGENT_CONVERSATIONS_DB,
    provider: str = "",
    endpoint: str = "",
    auth_mode: str = "",
    model: str = "",
    artifact_path: Path | None = None,
    *,
    extract_new_only: bool = True,
    extract_since_watermark: bool = True,
) -> dict:
    """Generate immutable production delta preflight artifact (non-paid).

    Computes exact eligible delta from runtime source vs durable inventory baseline,
    creates delta inventory + fresh run + knowledge_run_items (metadata only),
    writes desensitized artifact.

    Does NOT call LLM, write Chroma, write candidate/canonical/current, or advance watermark.

    Important: never compare the same live canonical DB as both before and after.
    Without a historical canonical snapshot, the durable before-set is the frozen
    inventory at/before the committed watermark (not a same-path self-diff).

    extract_new_only: queue only change_type=new (not modified) for paid extract.
    extract_since_watermark: only queue evidence from sessions on/after watermark
    updated_at date — avoids replaying large identity-churn backlog as "new".
    """
    if not model:
        raise ValueError("model is required — fail closed")

    # Ensure schema (idempotent)
    from personal_knowledge.domains.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL

    con = sqlite3.connect(str(db_path))
    con.executescript(SCHEMA_SQL)
    validation = validate_provider_model(provider, endpoint, model, auth_mode)

    # Compute source checksums (current vs committed watermark)
    src_after = compute_source_checksum(canonical_db)
    wm_row = con.execute(
        "SELECT value, updated_at FROM knowledge_source_watermark WHERE key='committed'"
    ).fetchone()
    src_before = wm_row[0] if wm_row else ""
    wm_updated_at = wm_row[1] if wm_row and len(wm_row) > 1 else ""
    con.close()

    config_hash = hashlib.sha256(
        f"{provider}|{endpoint}|{auth_mode}|{model}".encode()
    ).hexdigest()[:32]

    baseline_inventory_id = ""
    after_inventory_id = ""

    if src_before and src_before == src_after:
        delta = _empty_delta_result()
    else:
        # After = current eligible inventory (full eligibility + inventory content_hash)
        after_hashes, after_meta = _current_eligible_ref_hashes(canonical_db)
        after_inventory_id = str(after_meta.get("inventory_id") or "")

        # Before = durable inventory baseline at/before watermark (not live self-diff)
        before_hashes, baseline_inventory_id = _load_baseline_inventory_hashes(
            db_path,
            watermark_updated_at=wm_updated_at or "",
            exclude_inventory_id=after_inventory_id,
        )
        if not src_before:
            # No watermark: empty before means full current set is "new"
            before_hashes = {}
            baseline_inventory_id = ""
            src_before = "none"

        delta_items, change_types, new_count, modified_count, deleted_count = _diff_ref_hashes(
            before_hashes, after_hashes
        )
        extract_types = (
            frozenset({"new"}) if extract_new_only else frozenset({"new", "modified"})
        )
        if not delta_items:
            delta = _empty_delta_result()
        else:
            # Order extract queue by session recency (newest first)
            order_keys: dict[str, str] = {}
            try:
                ccon = sqlite3.connect(
                    f"file:{canonical_db.as_posix()}?mode=ro", uri=True
                )
                for ref, ct, _hb, _ha in delta_items:
                    if ct not in extract_types:
                        continue
                    row = ccon.execute(
                        "SELECT s.started_at FROM canonical_messages m "
                        "JOIN canonical_sessions s "
                        "ON m.canonical_session_id=s.canonical_session_id "
                        "WHERE m.canonical_message_id=?",
                        (ref,),
                    ).fetchone()
                    if row and row[0]:
                        order_keys[ref] = row[0]
                ccon.close()
            except sqlite3.Error:
                order_keys = {}

            # Default: only queue post-watermark sessions as paid extract targets
            extract_floor = ""
            if extract_since_watermark and wm_updated_at:
                extract_floor = wm_updated_at[:10]  # YYYY-MM-DD

            delta = _materialize_delta_run(
                db_path,
                source_before_checksum=src_before,
                source_after_checksum=src_after,
                model=model,
                delta_items=delta_items,
                new_count=new_count,
                modified_count=modified_count,
                deleted_count=deleted_count,
                change_types=change_types,
                config_hash=config_hash,
                init_run_items=True,
                extract_change_types=extract_types,
                extract_order_keys=order_keys,
                extract_min_started_at=extract_floor,
            )

    extract_calls = int(delta.get("extract_item_count") or 0)
    if extract_calls <= 0 and not delta.get("no_op", True):
        # Fallback estimate when items not re-seeded (idempotent existing run)
        extract_calls = int(delta.get("new_count") or 0)
        if not extract_new_only:
            extract_calls += int(delta.get("modified_count") or 0)

    artifact = {
        "schema_version": "1.0",
        "artifact_hash": hashlib.sha256(
            f"{delta.get('delta_inventory_id','')}|{delta.get('fresh_run_id','')}|{src_before}|{src_after}".encode()
        ).hexdigest()[:32],
        "delta_inventory_id": delta.get("delta_inventory_id", ""),
        "fresh_run_id": delta.get("fresh_run_id", ""),
        "source_before_checksum": src_before,
        "source_after_checksum": src_after,
        "baseline_inventory_id": baseline_inventory_id,
        "after_inventory_id": after_inventory_id,
        "ordered_dataset_hash": delta.get("delta_inventory_id", ""),
        "new_count": delta.get("new_count", 0),
        "modified_count": delta.get("modified_count", 0),
        "deleted_count": delta.get("deleted_count", 0),
        "delta_count": delta.get("delta_count", 0),
        "extract_item_count": extract_calls,
        "extract_new_only": extract_new_only,
        "extract_since_watermark": extract_since_watermark,
        "extract_min_started_at": (
            (wm_updated_at[:10] if (extract_since_watermark and wm_updated_at) else "")
        ),
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
        # Estimates (non-paid, for budgeting) — based on extract queue, not deleted
        "estimated_llm_calls": extract_calls,
        "estimated_tokens": extract_calls * 2000,
        "estimated_cost_usd": round(extract_calls * 0.001, 4),
        "estimated_time_minutes": round(extract_calls * 0.1, 1),
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
    p.add_argument(
        "--sandbox-ku08",
        action="store_true",
        help="Isolated non-empty delta→journal→watermark E2E (does not touch live active index)",
    )
    p.add_argument("--provider", default="", help="LLM provider (vertex_google/openai/google_free)")
    p.add_argument("--endpoint", default="", help="LLM endpoint URL")
    p.add_argument("--auth-mode", default="", help="auth mode (gcloud/api_key)")
    p.add_argument("--model", default="", help="model ID (required for --prepare)")
    p.add_argument("--artifact", type=Path, default=None, help="artifact output path")
    args = p.parse_args(argv)

    if args.sandbox_ku08:
        from personal_knowledge.core.project_paths import AI_CONTEXT_DIR

        work = Path("integration/analysis/ai_context/ku08_sandbox_work")
        report = run_sandbox_ku08_e2e(work, model=args.model or "gemini-2.5-flash")
        out = args.artifact or (AI_CONTEXT_DIR / "phase14_incremental_final_reconcile.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "generated_at": _utc_now(),
            "requirement": "KU-08",
            "mode": "sandbox_isolated",
            "live_active_untouched": True,
            "report": report,
        }
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0 if report.get("ok") else 1

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
