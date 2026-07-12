"""Phase 14 Plan 02 Task 1：冻结 production inventory。

从 canonical conversation store 生成权威有序 inventory，记录每条 evidence 的
evidence_ref、content_hash、session/source/agent/time bucket、eligibility、position。
inventory hash 由完整有序 content hash 派生，用于 resume 时 drift 检测。

输出隐私安全报告（只含 count/hash，不含原文）。

用法::

    python build_knowledge_inventory.py --inspect
    python build_knowledge_inventory.py --write
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
_THIS_DIR = _SCRIPTS_DIR  # legacy alias: scripts root for resource paths

from core.project_paths import UNIFIED_DB, AGENT_CONVERSATIONS_DB, AI_CONTEXT_DIR  # noqa: E402

INVENTORY_JSON = AI_CONTEXT_DIR / "knowledge_unit_inventory.json"
INVENTORY_MD = AI_CONTEXT_DIR / "knowledge_unit_inventory.md"

# system-reminder 预处理（与 build_knowledge_units.py 一致）
SYSTEM_INJECTION_PATTERNS = [
    re.compile(r"<system-reminder[^>]*>.*?</system-reminder>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<recommended_plugins>.*?</recommended_plugins>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<environment_context>.*?</environment_context>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<additional_data>.*?</additional_data>", re.DOTALL | re.IGNORECASE),
    re.compile(r"<user_info>.*?</user_info>", re.DOTALL | re.IGNORECASE),
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _strip_injections(text: str) -> str:
    for pat in SYSTEM_INJECTION_PATTERNS:
        text = pat.sub("", text)
    return text.strip()


def _content_hash(text: str) -> str:
    normalized = " ".join(text.split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def _source_checksum(db_path: Path) -> str:
    """canonical DB 的 schema hash + count 校验值。"""
    con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    # schema hash
    ddl = con.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE '%fts%' ESCAPE '\\' ORDER BY name"
    ).fetchall()
    schema_text = "\n;;;".join(sql or "" for _name, sql in ddl)
    schema_hash = hashlib.sha256(schema_text.encode("utf-8")).hexdigest()[:16]
    # counts
    session_count = con.execute("SELECT COUNT(*) FROM canonical_sessions").fetchone()[0]
    message_count = con.execute("SELECT COUNT(*) FROM canonical_messages").fetchone()[0]
    con.close()
    payload = f"{schema_hash}|{session_count}|{message_count}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def build_inventory(canonical_db: Path = AGENT_CONVERSATIONS_DB) -> dict:
    """构建冻结 inventory（不写 DB，只返回数据结构）。"""
    if not canonical_db.exists():
        return {"error": f"canonical DB 不存在: {canonical_db}"}

    source_checksum = _source_checksum(canonical_db)
    con = sqlite3.connect(f"file:{canonical_db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row

    # 粗筛：eligible user message > 20 字 + eligible assistant message > 20 字
    # assistant 消息需额外排除工具命令模式
    coarse_rows = con.execute(
        "SELECT m.canonical_message_id, m.canonical_session_id, m.content, "
        "m.source, m.role, s.agent, s.started_at, s.evidence_eligible "
        "FROM canonical_messages m JOIN canonical_sessions s "
        "ON m.canonical_session_id=s.canonical_session_id "
        "WHERE s.evidence_eligible=1 "
        "AND m.content IS NOT NULL AND length(m.content) > 20 "
        "AND m.role IN ('user','assistant') "
        "ORDER BY s.started_at DESC, m.canonical_message_id"
    ).fetchall()
    coarse_count = len(coarse_rows)

    # 清洗 + 去重 + 过滤
    items: list[dict] = []
    seen_hashes: set[str] = set()
    excluded_short = 0
    excluded_injection_only = 0
    excluded_dup = 0
    excluded_tool = 0

    # assistant 消息工具命令排除模式
    import re as _re
    _tool_patterns = [
        _re.compile(r'^\[Bash\]', _re.DOTALL),
        _re.compile(r'^\[Tool:', _re.DOTALL),
        _re.compile(r'^\[Thinking\]', _re.DOTALL),
        _re.compile(r'^\[Read\]', _re.DOTALL),
        _re.compile(r'^\[Edit\]', _re.DOTALL),
        _re.compile(r'^\[Write\]', _re.DOTALL),
        _re.compile(r'^\[Grep\]', _re.DOTALL),
        _re.compile(r'^\[Glob\]', _re.DOTALL),
        _re.compile(r'^\[TodoWrite\]', _re.DOTALL),
        _re.compile(r'^\[Agent\]', _re.DOTALL),
        _re.compile(r'^\[WebFetch\]', _re.DOTALL),
        _re.compile(r'^\[WebSearch\]', _re.DOTALL),
        _re.compile(r'^\[Skill\]', _re.DOTALL),
    ]

    for row in coarse_rows:
        raw_content = row["content"]
        cleaned = _strip_injections(raw_content)
        has_injection = cleaned != raw_content.strip()

        # assistant 工具命令排除
        if row["role"] == "assistant":
            if any(p.match(cleaned) for p in _tool_patterns):
                excluded_tool += 1
                continue

        # 清洗后太短
        if len(cleaned) <= 30:
            excluded_short += 1
            continue

        chash = _content_hash(cleaned)
        if chash in seen_hashes:
            excluded_dup += 1
            continue
        seen_hashes.add(chash)

        # 只有注入内容（清洗后虽然 >30 但全是系统文本）也排除
        if has_injection and len(cleaned.replace("<", "").replace(">", "").strip()) <= 30:
            excluded_injection_only += 1
            continue

        started = row["started_at"] or ""
        time_bucket = started[:7] if started else "unknown"
        clen = len(cleaned)
        if clen < 100:
            length_bucket = "short"
        elif clen < 500:
            length_bucket = "mid"
        else:
            length_bucket = "long"

        items.append({
            "evidence_ref": row["canonical_message_id"],
            "content_hash": chash,
            "session_id": row["canonical_session_id"],
            "source": row["source"],
            "agent": row["agent"] or "unknown",
            "time_bucket": time_bucket,
            "length_bucket": length_bucket,
            "has_injection": int(has_injection),
            "eligibility": "eligible",
        })

    con.close()

    # 有序 dataset hash（Merkle-like：所有 content_hash 的有序拼接）
    ordered_hashes = "|".join(item["content_hash"] for item in items)
    dataset_hash = hashlib.sha256(ordered_hashes.encode("utf-8")).hexdigest()[:32]
    inventory_id = hashlib.sha256(
        f"{source_checksum}|{dataset_hash}".encode("utf-8")
    ).hexdigest()[:32]

    # 时间范围
    time_min = min((item["time_bucket"] for item in items if item["time_bucket"] != "unknown"), default="")
    time_max = max((item["time_bucket"] for item in items if item["time_bucket"] != "unknown"), default="")

    # 统计（隐私安全，无原文）
    by_agent: dict[str, int] = {}
    by_length: dict[str, int] = {"short": 0, "mid": 0, "long": 0}
    by_source: dict[str, int] = {}
    injection_count = 0
    for item in items:
        by_agent[item["agent"]] = by_agent.get(item["agent"], 0) + 1
        by_length[item["length_bucket"]] += 1
        by_source[item["source"]] = by_source.get(item["source"], 0) + 1
        injection_count += item["has_injection"]

    return {
        "inventory_id": inventory_id,
        "source_db_path": str(canonical_db),
        "source_checksum": source_checksum,
        "coarse_count": coarse_count,
        "authoritative_count": len(items),
        "dataset_hash": dataset_hash,
        "time_range_min": time_min,
        "time_range_max": time_max,
        "excluded": {
            "short_after_cleaning": excluded_short,
            "duplicate_content_hash": excluded_dup,
            "injection_only": excluded_injection_only,
        },
        "stats": {
            "by_agent": dict(sorted(by_agent.items(), key=lambda x: -x[1])),
            "by_length": by_length,
            "by_source": by_source,
            "with_injection": injection_count,
        },
        "items": items,
    }


def write_inventory_to_db(inventory: dict, db_path: Path = UNIFIED_DB) -> None:
    """把 inventory 写入 knowledge_inventory + knowledge_inventory_items 表。"""
    con = sqlite3.connect(str(db_path))
    try:
        con.execute(
            "INSERT OR REPLACE INTO knowledge_inventory VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                inventory["inventory_id"],
                _utc_now(),
                inventory["source_db_path"],
                inventory["source_checksum"],
                inventory["authoritative_count"],
                inventory["coarse_count"],
                inventory["dataset_hash"],
                inventory["time_range_min"],
                inventory["time_range_max"],
                json.dumps({
                    "excluded": inventory["excluded"],
                    "stats": inventory["stats"],
                }, ensure_ascii=False),
            ),
        )
        for pos, item in enumerate(inventory["items"]):
            con.execute(
                "INSERT OR REPLACE INTO knowledge_inventory_items VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    None,  # autoincrement
                    inventory["inventory_id"],
                    pos,
                    item["evidence_ref"],
                    item["content_hash"],
                    item["session_id"],
                    item["source"],
                    item["agent"],
                    item["time_bucket"],
                    item["length_bucket"],
                    item["has_injection"],
                    item["eligibility"],
                ),
            )
        con.commit()
    finally:
        con.close()


def write_report(inventory: dict, json_path: Path = INVENTORY_JSON, md_path: Path = INVENTORY_MD) -> None:
    """写隐私安全报告（不含原文）。"""
    json_path.parent.mkdir(parents=True, exist_ok=True)

    # JSON：不含 items 的 evidence_ref 映射到原文（只含 hash）
    report = {k: v for k, v in inventory.items() if k != "items"}
    report["item_count"] = len(inventory["items"])
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # Markdown
    lines = [
        "# Knowledge Unit Production Inventory",
        "",
        f"- 生成时间: {_utc_now()}",
        f"- inventory_id: `{inventory['inventory_id']}`",
        f"- source: `{inventory['source_db_path']}`",
        f"- source_checksum: `{inventory['source_checksum']}`",
        f"- dataset_hash: `{inventory['dataset_hash']}`",
        "",
        "## Count 解释",
        "",
        f"| 阶段 | Count |",
        f"|------|-------|",
        f"| SQL 粗筛 (eligible user >20字) | {inventory['coarse_count']} |",
        f"| 清洗去重后 (authoritative) | **{inventory['authoritative_count']}** |",
        f"| 排除-清洗后过短 | {inventory['excluded']['short_after_cleaning']} |",
        f"| 排除-content_hash 重复 | {inventory['excluded']['duplicate_content_hash']} |",
        f"| 排除-仅注入内容 | {inventory['excluded']['injection_only']} |",
        "",
        "> 报告不含 message content、evidence quote、token 或完整 prompt。",
        "",
        "## 分布统计",
        "",
        "### 按 agent",
        "",
        "| Agent | Count |",
        "|-------|-------|",
    ]
    for agent, count in inventory["stats"]["by_agent"].items():
        lines.append(f"| {agent} | {count} |")
    lines += [
        "",
        "### 按长度",
        "",
        "| Bucket | Count |",
        "|--------|-------|",
    ]
    for bucket, count in inventory["stats"]["by_length"].items():
        lines.append(f"| {bucket} | {count} |")
    lines += [
        "",
        f"### 含系统注入: {inventory['stats']['with_injection']}",
        "",
        f"### 时间范围: {inventory['time_range_min']} → {inventory['time_range_max']}",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")


def run(canonical_db: Path = AGENT_CONVERSATIONS_DB, db_path: Path = UNIFIED_DB,
        write: bool = False) -> int:
    inventory = build_inventory(canonical_db)
    if "error" in inventory:
        print(f"[error] {inventory['error']}")
        return 1

    write_report(inventory)

    print("=" * 60)
    print("Phase 14 Plan 02 Task 1: Production Inventory")
    print("=" * 60)
    print(f"inventory_id:       {inventory['inventory_id']}")
    print(f"source_checksum:    {inventory['source_checksum']}")
    print(f"dataset_hash:       {inventory['dataset_hash']}")
    print(f"coarse count:       {inventory['coarse_count']}")
    print(f"authoritative:      {inventory['authoritative_count']}")
    print(f"excluded short:     {inventory['excluded']['short_after_cleaning']}")
    print(f"excluded dup:       {inventory['excluded']['duplicate_content_hash']}")
    print(f"excluded injection: {inventory['excluded']['injection_only']}")
    print(f"time range:         {inventory['time_range_min']} → {inventory['time_range_max']}")
    print(f"with injection:     {inventory['stats']['with_injection']}")
    print()
    print(f"报告: {INVENTORY_MD}")

    if write:
        write_inventory_to_db(inventory, db_path)
        print(f"[ok] inventory 已写入 DB ({inventory['authoritative_count']} items)")
    else:
        print("[dry-run] 未写入 DB，加 --write 写入")

    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Phase 14 Plan 02 Task 1: freeze production inventory")
    p.add_argument("--inspect", action="store_true", help="只报告不写")
    p.add_argument("--write", action="store_true", help="写入 DB")
    p.add_argument("--canonical-db", type=Path, default=AGENT_CONVERSATIONS_DB)
    p.add_argument("--db", type=Path, default=UNIFIED_DB)
    args = p.parse_args(argv)
    return run(args.canonical_db, args.db, write=args.write)


if __name__ == "__main__":
    raise SystemExit(main())
