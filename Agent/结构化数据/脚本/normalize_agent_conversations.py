"""Phase 07 Wave 1/2: Agent 对话规范化解析器。

把 Codex rollout jsonl 拆成 session -> turn -> message/tool/event 的可追溯结构。
其他 Agent 源(Claude/WorkBuddy/Hermes)目前只发现并计数,标记 unsupported,
后续 Wave 再补。设计依据见 .gsd/phases/07_agent_conversation_normalization_mem0_spike/。

输出维度(每条记录都带证据链 raw_file + line_no):
  - turns        : 每个 turn_id 一行
  - messages     : user/assistant/developer/system 文本(只提取可解释文本)
  - tool_calls   : function_call / custom_tool_call / *_call
  - tool_outputs : function_call_output / *_output,按 call_id 关联
  - lifecycle    : task_started / task_complete / turn_aborted 等
  - usage        : token_count 等指标

用法:
  python normalize_agent_conversations.py --dry-run --limit-files 5
  python normalize_agent_conversations.py --write
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[3]
AGENT_RAW = ROOT / "Agent" / "原始数据"
DB = ROOT / "Agent" / "结构化数据" / "SQLite数据库" / "agent_data.sqlite"

# 目前深度解析的源;其余只计数标记 unsupported。
SUPPORTED_SOURCES = {"Codex"}

# response_item.payload.type -> 归类
RESPONSE_ITEM_KIND = {
    "message": "message",
    "function_call": "tool_call",
    "custom_tool_call": "tool_call",
    "image_generation_call": "tool_call",
    "function_call_output": "tool_output",
    "custom_tool_call_output": "tool_output",
    "reasoning": "reasoning",  # 默认不进用户想法输入
}

# event_msg.payload.type -> 归类
EVENT_MSG_KIND = {
    "user_message": "message",
    "agent_message": "message",
    "task_started": "lifecycle",
    "task_complete": "lifecycle",
    "turn_aborted": "lifecycle",
    "token_count": "usage",
    "exec_command_end": "lifecycle",
    "patch_apply_end": "lifecycle",
    "web_search_end": "lifecycle",
    "image_generation_end": "lifecycle",
}

# 默认排除出用户想法候选输入的 role / type。
EXCLUDE_FROM_USER_THOUGHT = {"developer", "system", "reasoning"}


@dataclass
class ParseStats:
    files_total: int = 0
    files_supported: int = 0
    files_unsupported: int = 0
    lines: int = 0
    parse_errors: int = 0
    by_raw_type: Counter = field(default_factory=Counter)
    by_payload_type: Counter = field(default_factory=Counter)
    by_kind: Counter = field(default_factory=Counter)
    unsupported_sources: Counter = field(default_factory=Counter)
    error_samples: list = field(default_factory=list)


@dataclass
class Records:
    """收集到的规范化记录,供 dry-run 打印或 --write 入库。"""
    turns: list[dict] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    tool_outputs: list[dict] = field(default_factory=list)
    lifecycle: list[dict] = field(default_factory=list)
    usage: list[dict] = field(default_factory=list)
    sessions_meta: list[dict] = field(default_factory=list)


def discover_jsonl_files(limit_files: int | None = None) -> list[tuple[str, Path]]:
    """发现 Agent/原始数据 下所有 jsonl,返回 (source, path)。

    source 取 Agent/原始数据 的直接子目录名(Codex/Claude/...)。
    """
    out: list[tuple[str, Path]] = []
    if not AGENT_RAW.exists():
        return out
    for src_dir in sorted(AGENT_RAW.iterdir()):
        if not src_dir.is_dir():
            continue
        for jf in sorted(src_dir.rglob("*.jsonl")):
            out.append((src_dir.name, jf))
    if limit_files is not None:
        # supported 源优先排前,保证 --limit-files 能优先看到解析结果(Codex 排在 Claude 前)
        out.sort(key=lambda sp: 0 if sp[0] in SUPPORTED_SOURCES else 1)
        out = out[:limit_files]
    return out


def extract_text(content: Any) -> str:
    """从 message payload.content 提取可解释文本。

    content 可能是字符串,也可能是 [{"type":"input_text","text":"..."}] 列表。
    只拼接 text 字段,忽略非文本块。
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for blk in content:
            if isinstance(blk, dict):
                t = blk.get("text") or blk.get("content") or ""
                if isinstance(t, str) and t.strip():
                    parts.append(t)
        return "\n".join(parts)
    return ""


def classify(top_type: str, payload_type: str) -> str:
    """把 (顶层类型, payload 类型) 归到 6 类之一或 'skip'。"""
    if top_type == "response_item":
        return RESPONSE_ITEM_KIND.get(payload_type, "skip")
    if top_type == "event_msg":
        return EVENT_MSG_KIND.get(payload_type, "skip")
    return "skip"


def parse_codex_file(
    path: Path,
    source: str,
    stats: ParseStats,
    records: Records,
) -> None:
    """解析单个 Codex rollout jsonl,填充 records 和 stats。

    解析失败的行计入 stats.parse_errors 并记录样本,不中断整个文件。
    """
    seen_turns: set[str] = set()
    session_id = path.stem  # 文件名即 session 标识
    event_index = 0
    last_turn_id: str | None = None  # 前向填充:event_msg 可能不带 turn_id,用最近的 turn 归属
    with path.open(encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            stats.lines += 1
            event_index += 1
            raw = raw.strip()
            if not raw:
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                stats.parse_errors += 1
                if len(stats.error_samples) < 5:
                    stats.error_samples.append(
                        {"file": str(path), "line_no": line_no, "reason": "json_decode"}
                    )
                continue

            top_type = rec.get("type", "?")
            stats.by_raw_type[top_type] += 1
            payload = rec.get("payload", {})
            payload_type = (
                payload.get("type", "(no_type)") if isinstance(payload, dict) else "(no_payload)"
            )
            stats.by_payload_type[payload_type] += 1
            timestamp = payload.get("timestamp") or rec.get("timestamp") or ""
            raw_turn_id = payload.get("turn_id") if isinstance(payload, dict) else None
            # turn_context 是 turn 权威边界;event_msg 可能缺 turn_id,前向填充
            if top_type == "turn_context" and isinstance(payload, dict) and "turn_id" in payload:
                last_turn_id = payload.get("turn_id")
            turn_id = raw_turn_id or last_turn_id

            # session_meta 单独存
            if top_type == "session_meta":
                records.sessions_meta.append({
                    "session_id": session_id,
                    "source": source,
                    "family": "Codex",
                    "raw_file": str(path.relative_to(ROOT)),
                    "line_no": line_no,
                    "timestamp": payload.get("timestamp", ""),
                    "cwd": payload.get("cwd", ""),
                    "model": payload.get("model_provider", ""),
                    "originator": payload.get("originator", ""),
                })
                continue

            kind = classify(top_type, payload_type)
            stats.by_kind[kind] += 1

            # turn 边界:每个 turn_id 首次出现时登记一次
            if turn_id and turn_id not in seen_turns:
                seen_turns.add(turn_id)
                records.turns.append({
                    "session_id": session_id,
                    "source": source,
                    "family": "Codex",
                    "turn_id": turn_id,
                    "first_raw_file": str(path.relative_to(ROOT)),
                    "first_line_no": line_no,
                    "first_timestamp": timestamp,
                })

            base = {
                "session_id": session_id,
                "source": source,
                "family": "Codex",
                "turn_id": turn_id,
                "event_index": event_index,
                "timestamp": timestamp,
                "raw_type": top_type,
                "payload_type": payload_type,
                "raw_file": str(path.relative_to(ROOT)),
                "line_no": line_no,
            }

            if kind == "message":
                # role 归一化:event_msg.user_message/agent_message -> user/assistant,
                # 其余(response_item.message.role)直接采用 payload 里的 role。
                role = payload.get("role", "")
                if not role:
                    role = {"user_message": "user", "agent_message": "assistant"}.get(
                        payload_type, payload_type
                    )
                text = extract_text(payload.get("content"))
                # event_msg 的 user_message/agent_message 正文在 message 字段
                if not text and payload_type in {"user_message", "agent_message"}:
                    text = payload.get("message") or payload.get("last_agent_message") or ""
                records.messages.append({**base, "role": role, "text": text})
            elif kind == "tool_call":
                records.tool_calls.append({
                    **base,
                    "call_id": payload.get("call_id") or payload.get("id") or "",
                    "tool_name": payload.get("name", ""),
                    "arguments": _truncate(str(payload.get("arguments", payload.get("input", "")))),
                    "status": payload.get("status", ""),
                })
            elif kind == "tool_output":
                records.tool_outputs.append({
                    **base,
                    "call_id": payload.get("call_id", ""),
                    "output": _truncate(str(payload.get("output", ""))),
                })
            elif kind == "lifecycle":
                records.lifecycle.append({**base, "detail": _truncate(
                    str(payload.get("message") or payload.get("last_agent_message") or "")
                )})
            elif kind == "usage":
                records.usage.append({**base, "metrics": json.dumps(
                    {k: v for k, v in payload.items() if k not in {"type", "turn_id"}},
                    ensure_ascii=False,
                )})
            # reasoning / skip 不进 records(默认排除)


def _truncate(s: str, limit: int = 2000) -> str:
    """工具输出可能极长,入库前截断,原文回源文件即可。"""
    return s if len(s) <= limit else s[:limit] + f"...[truncated {len(s) - limit} chars]"


def run(dry_run: bool, write: bool, limit_files: int | None) -> int:
    if dry_run and write:
        print("[error] --dry-run 与 --write 互斥", file=sys.stderr)
        return 2
    files = discover_jsonl_files(limit_files)
    if not files:
        print("[warn] 未发现任何 jsonl 文件,检查 Agent/原始数据/ 是否存在")
        return 0

    stats = ParseStats()
    records = Records()
    for source, path in files:
        stats.files_total += 1
        if source not in SUPPORTED_SOURCES:
            stats.files_unsupported += 1
            stats.unsupported_sources[source] += 1
            continue
        stats.files_supported += 1
        try:
            parse_codex_file(path, source, stats, records)
        except Exception as exc:  # 单文件失败不中断整体
            stats.parse_errors += 1
            if len(stats.error_samples) < 5:
                stats.error_samples.append(
                    {"file": str(path), "reason": f"file_error: {exc}"}
                )

    print_stats(stats, records)

    if write:
        write_tables(records)
    elif not dry_run:
        # 没给 flag 时默认只统计,提示用法
        print("\n[dry] 未指定 --write,仅统计未入库。加 --write 写入 v2 表。")
    return 0


def print_stats(stats: ParseStats, records: Records) -> None:
    print("=" * 60)
    print("Agent 对话规范化解析统计")
    print("=" * 60)
    print(f"扫描文件: {stats.files_total} (supported={stats.files_supported}, "
          f"unsupported={stats.files_unsupported})")
    print(f"扫描行数: {stats.lines}, 解析失败: {stats.parse_errors}")
    if stats.unsupported_sources:
        print("未深度解析的源(仅计数):")
        for src, n in stats.unsupported_sources.most_common():
            print(f"  {src}: {n} 个文件")
    print("\n顶层类型 (raw_type) 分布:")
    for k, v in stats.by_raw_type.most_common():
        print(f"  {k:24s} {v}")
    print("\npayload.type 分布:")
    for k, v in stats.by_payload_type.most_common():
        print(f"  {k:24s} {v}")
    print("\n归类 (kind) 分布:")
    for k, v in stats.by_kind.most_common():
        print(f"  {k:24s} {v}")
    print("\n规范化记录数:")
    print(f"  sessions_meta : {len(records.sessions_meta)}")
    print(f"  turns         : {len(records.turns)}")
    print(f"  messages      : {len(records.messages)}")
    print(f"  tool_calls    : {len(records.tool_calls)}")
    print(f"  tool_outputs  : {len(records.tool_outputs)}")
    print(f"  lifecycle     : {len(records.lifecycle)}")
    print(f"  usage         : {len(records.usage)}")
    if stats.error_samples:
        print("\n失败样本(最多5条):")
        for s in stats.error_samples:
            print(f"  {s}")


V2_TABLES = {
    "agent_turns": [
        ("session_id", "TEXT"), ("source", "TEXT"), ("family", "TEXT"),
        ("turn_id", "TEXT"), ("first_raw_file", "TEXT"), ("first_line_no", "INTEGER"),
        ("first_timestamp", "TEXT"),
    ],
    "agent_messages": [
        ("session_id", "TEXT"), ("source", "TEXT"), ("family", "TEXT"),
        ("turn_id", "TEXT"), ("event_index", "INTEGER"), ("timestamp", "TEXT"),
        ("raw_type", "TEXT"), ("payload_type", "TEXT"), ("role", "TEXT"),
        ("text", "TEXT"), ("raw_file", "TEXT"), ("line_no", "INTEGER"),
    ],
    "agent_tool_calls": [
        ("session_id", "TEXT"), ("source", "TEXT"), ("family", "TEXT"),
        ("turn_id", "TEXT"), ("event_index", "INTEGER"), ("timestamp", "TEXT"),
        ("raw_type", "TEXT"), ("payload_type", "TEXT"), ("call_id", "TEXT"),
        ("tool_name", "TEXT"), ("arguments", "TEXT"), ("status", "TEXT"),
        ("raw_file", "TEXT"), ("line_no", "INTEGER"),
    ],
    "agent_tool_outputs": [
        ("session_id", "TEXT"), ("source", "TEXT"), ("family", "TEXT"),
        ("turn_id", "TEXT"), ("event_index", "INTEGER"), ("timestamp", "TEXT"),
        ("raw_type", "TEXT"), ("payload_type", "TEXT"), ("call_id", "TEXT"),
        ("output", "TEXT"), ("raw_file", "TEXT"), ("line_no", "INTEGER"),
    ],
    "agent_lifecycle_events": [
        ("session_id", "TEXT"), ("source", "TEXT"), ("family", "TEXT"),
        ("turn_id", "TEXT"), ("event_index", "INTEGER"), ("timestamp", "TEXT"),
        ("raw_type", "TEXT"), ("payload_type", "TEXT"), ("detail", "TEXT"),
        ("raw_file", "TEXT"), ("line_no", "INTEGER"),
    ],
    "agent_usage_metrics": [
        ("session_id", "TEXT"), ("source", "TEXT"), ("family", "TEXT"),
        ("turn_id", "TEXT"), ("event_index", "INTEGER"), ("timestamp", "TEXT"),
        ("raw_type", "TEXT"), ("payload_type", "TEXT"), ("metrics", "TEXT"),
        ("raw_file", "TEXT"), ("line_no", "INTEGER"),
    ],
    "agent_sessions_meta": [
        ("session_id", "TEXT"), ("source", "TEXT"), ("family", "TEXT"),
        ("raw_file", "TEXT"), ("line_no", "INTEGER"), ("timestamp", "TEXT"),
        ("cwd", "TEXT"), ("model", "TEXT"), ("originator", "TEXT"),
    ],
}

RECORDS_TO_TABLE = {
    "agent_turns": "turns",
    "agent_messages": "messages",
    "agent_tool_calls": "tool_calls",
    "agent_tool_outputs": "tool_outputs",
    "agent_lifecycle_events": "lifecycle",
    "agent_usage_metrics": "usage",
    "agent_sessions_meta": "sessions_meta",
}

INDEXES = [
    ("idx_agent_turns_sid", "agent_turns", "session_id, turn_id"),
    ("idx_agent_messages_sid", "agent_messages", "session_id, turn_id"),
    ("idx_agent_messages_role", "agent_messages", "role"),
    ("idx_agent_tool_calls_cid", "agent_tool_calls", "call_id"),
    ("idx_agent_tool_outputs_cid", "agent_tool_outputs", "call_id"),
    ("idx_agent_lifecycle_sid", "agent_lifecycle_events", "session_id"),
    ("idx_agent_usage_sid", "agent_usage_metrics", "session_id"),
    ("idx_agent_meta_sid", "agent_sessions_meta", "session_id"),
]


def write_tables(records: Records) -> None:
    """写入 v2 旁路表。幂等:先 DROP 再 CREATE 再 INSERT。"""
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    cur = con.cursor()
    try:
        for table, cols in V2_TABLES.items():
            cur.execute(f"DROP TABLE IF EXISTS {table}")
            col_def = ", ".join(f"{c} {t}" for c, t in cols)
            cur.execute(f"CREATE TABLE {table} ({col_def})")
        for idx_name, table, _cols in INDEXES:
            cur.execute(f"DROP INDEX IF EXISTS {idx_name}")
            cur.execute(f"CREATE INDEX {idx_name} ON {table} ({_cols})")

        inserted = {}
        for table, attr in RECORDS_TO_TABLE.items():
            rows = getattr(records, attr)
            cols = [c for c, _ in V2_TABLES[table]]
            placeholders = ", ".join("?" for _ in cols)
            col_list = ", ".join(cols)
            sql = f"INSERT INTO {table} ({col_list}) VALUES ({placeholders})"
            data = [tuple(row.get(c) for c in cols) for row in rows]
            if data:
                cur.executemany(sql, data)
            inserted[table] = len(data)
        con.commit()
        print("\n" + "=" * 60)
        print(f"已写入 v2 表到 {DB}")
        print("=" * 60)
        for t, n in inserted.items():
            print(f"  {t:28s} {n} rows")
    finally:
        con.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Agent 对话规范化解析器 (Phase 07)")
    p.add_argument("--dry-run", action="store_true", help="只统计不写入")
    p.add_argument("--write", action="store_true", help="写入 v2 旁路表")
    p.add_argument("--limit-files", type=int, default=None, help="只处理前 N 个文件(调试用)")
    args = p.parse_args(argv)
    return run(args.dry_run, args.write, args.limit_files)


if __name__ == "__main__":
    raise SystemExit(main())
