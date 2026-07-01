"""GPT 对话叙述压缩(Wave 7 扩展)。

把 GPT 对话按 turn 压缩成高密度叙述摘要,与 Agent 的 build_conversation_summary 同构。
GPT 数据已有 turn_number 字段,结构比 Agent 简单(无需去重/工具调用/role 归一化)。

数据来源:GPT/structured/db/chatgpt_data.db 的 messages 表。
输出格式:与 conversation_summaries.json 相同,可合并到同一文件。

用法:
  python build_gpt_conversation_summary.py --dry-run       # 只打印统计
  python build_gpt_conversation_summary.py --write --limit 10  # 小样本生成
  python build_gpt_conversation_summary.py --write              # 全量生成
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path

import build_conversation_summary as agent_summary_mod

ROOT = Path(__file__).resolve().parents[2]
GPT_DB = ROOT / "GPT" / "structured" / "db" / "chatgpt_data.db"
AGENT_SUMMARIES = ROOT / "integration" / "analysis" / "ai_context" / "conversation_summaries.json"
# GPT 输出合并到同文件(与 Agent 同构),或单独文件
OUT_JSON = AGENT_SUMMARIES  # 合并:GPT + Agent 同文件
OUT_MD = ROOT / "integration" / "analysis" / "ai_context" / "conversation_summaries.md"

DEFAULT_LIMIT = 10
MAX_CHARS_PER_CALL = 6000
TOOL_OUTPUT_MAX = 300  # GPT 无工具调用,此参数预留
DEFAULT_WORKERS = 3
PROMPT_VERSION = agent_summary_mod.PROMPT_VERSION


@dataclass
class TurnSummary:
    turn_id: str | None
    narrative: str
    message_count: int = 0
    tools_used: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)


@dataclass
class SessionSummary:
    session_id: str
    main_topic: str
    turn_summaries: list[TurnSummary]
    meta: dict


def load_gpt_messages(con, conversation_id: str) -> list[dict]:
    """加载 GPT 对话的 user+assistant 消息,按 turn_number 排序。"""
    rows = con.execute(
        "select id, conversation_id, turn_number, role, content, timestamp "
        "from messages where conversation_id=? and role in ('user','assistant') "
        "order by turn_number, id",
        (conversation_id,),
    ).fetchall()
    return [
        {
            "msg_id": f"gpt:{r[0]}",
            "turn_number": r[2],
            "role": r[3],
            "text": r[4] or "",
            "timestamp": r[5] or "",
            "raw_file": f"GPT/chatgpt_data.db:messages/{r[0]}",
            "line_no": r[0],
        }
        for r in rows
    ]


def assemble_turns(messages: list[dict]) -> list[dict]:
    """把 GPT 消息按 turn_number 分组为 turn 列表。

    每个 turn 含该 turn_number 下的所有 user 和 assistant 消息(同一 turn 内可能有
    多条 assistant 消息,GPT 会在同一 turn 内多次回复)。
    """
    if not messages:
        return []
    turns: list[dict] = []
    turn_map: dict[int, dict] = {}
    for m in messages:
        tn = m["turn_number"]
        if tn not in turn_map:
            t = {"turn_id": str(tn), "messages": [], "tools": [], "source_refs": []}
            turn_map[tn] = t
            turns.append(t)
        turn_map[tn]["messages"].append(m)
        turn_map[tn]["source_refs"].append(m["raw_file"])
    return turns


def render_turn_text(turn: dict, turn_no: int) -> str:
    """把一个 turn 渲染成喂给 LLM 的纯文本。"""
    lines = [f"--- Turn {turn_no} ---"]
    for m in turn["messages"]:
        role_label = {"user": "用户", "assistant": "助手", "system": "系统"}.get(
            m["role"], m["role"]
        )
        lines.append(f"[{role_label}] {m['text']}")
    return "\n".join(lines)


def chunk_turns(turn_texts: list[str], max_chars: int) -> list[list[str]]:
    """把 turn 文本列表按 max_chars 滑动窗口分批。"""
    if not turn_texts:
        return []
    chunks: list[list[str]] = []
    cur: list[str] = []
    cur_len = 0
    for t in turn_texts:
        tlen = len(t)
        if cur and cur_len + tlen > max_chars:
            chunks.append(cur)
            cur, cur_len = [], 0
        cur.append(t)
        cur_len += tlen
    if cur:
        chunks.append(cur)
    return chunks


# 复用 Agent 的 prompt 模板(同一套压缩逻辑)
SUMMARY_SYSTEM_PROMPT = agent_summary_mod.SUMMARY_SYSTEM_PROMPT
SUMMARY_USER_PROMPT_TEMPLATE = agent_summary_mod.SUMMARY_USER_PROMPT_TEMPLATE


def make_llm_client():
    return agent_summary_mod.make_llm_client()


def summarize_chunk(client, model: str, chunk_text: str, start_no: int,
                    turn_count: int, max_attempts: int = 2) -> str:
    return agent_summary_mod.summarize_chunk(
        client, model, chunk_text, start_no, turn_count, max_attempts
    )


def parse_turn_summaries(raw: str, turn_count: int) -> list[str]:
    return agent_summary_mod.parse_turn_summaries(raw, turn_count)


def summarize_session(conversation_id: str, turns: list[dict], client, model: str,
                      max_chars: int) -> tuple[list[TurnSummary], int]:
    turn_texts = [render_turn_text(t, i + 1) for i, t in enumerate(turns)]
    chunks = chunk_turns(turn_texts, max_chars)
    turns_per_chunk = [len(c) for c in chunks]
    start_nos = []
    acc = 1
    for n in turns_per_chunk:
        start_nos.append(acc)
        acc += n

    all_narratives: list[str] = []
    failed = 0
    for chunk, start_no in zip(chunks, start_nos):
        chunk_text = "\n\n".join(chunk)
        try:
            raw = summarize_chunk(client, model, chunk_text, start_no, len(chunk))
            parts = parse_turn_summaries(raw, len(chunk))
            if len(parts) == len(chunk):
                all_narratives.extend(parts)
            elif len(parts) > len(chunk):
                all_narratives.extend(parts[:len(chunk)])
            else:
                all_narratives.extend(parts)
                missing = len(chunk) - len(parts)
                all_narratives.extend([t.split("\n", 1)[0] for t in chunk[-missing:]])
        except Exception as exc:
            failed += 1
            if failed <= 2:
                print(f"[warn] LLM 摘要失败({failed}, conv={conversation_id[:24]}..): "
                      f"{type(exc).__name__}: {str(exc)[:100]}", file=sys.stderr)
            all_narratives.extend([t.split("\n", 1)[0] for t in chunk])

    result = []
    for i, t in enumerate(turns):
        narrative = all_narratives[i] if i < len(all_narratives) else "(摘要缺失)"
        result.append(TurnSummary(
            turn_id=t["turn_id"] or f"gpt-turn-{i+1:03d}",
            narrative=narrative,
            message_count=len(t["messages"]),
            tools_used=[],
            source_refs=list(dict.fromkeys(t["source_refs"]))[:3],
        ))
    return result, len(chunks)


def guess_main_topic(client, model: str, turn_summaries: list[TurnSummary]) -> str:
    if not turn_summaries:
        return ""
    combined = "\n".join(f"Turn{i+1}: {t.narrative[:100]}" for i, t in enumerate(turn_summaries))
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "用一句中文概括这个对话的主要话题,不超过20字,只输出话题本身。"},
                {"role": "user", "content": combined},
            ],
            temperature=0.2,
            max_tokens=200,
        )
        topic = resp.choices[0].message.content.strip().strip("。.")
        return topic if topic else turn_summaries[0].narrative[:20]
    except Exception:
        return turn_summaries[0].narrative[:20]


def run(dry_run: bool, write: bool, limit: int | None, max_chars: int,
        resume: bool = False, workers: int = DEFAULT_WORKERS) -> int:
    if not GPT_DB.exists():
        print(f"[error] 缺少 GPT 数据库: {GPT_DB.relative_to(ROOT)}")
        return 1

    con = sqlite3.connect(GPT_DB)

    conv_rows = con.execute(
        "select conversation_id, count(*) c from messages "
        "where role in ('user','assistant') group by conversation_id "
        "having c between 5 and 200 order by conversation_id"
    ).fetchall()

    if resume and OUT_JSON.exists():
        try:
            existing = json.loads(OUT_JSON.read_text(encoding="utf-8"))
            done_ids = {s["session_id"] for s in existing}
            before = len(conv_rows)
            conv_rows = [r for r in conv_rows if r[0] not in done_ids]
            if before > len(conv_rows):
                print(f"[resume] 跳过 {before - len(conv_rows)} 个已完成 conversation,"
                      f" 剩余 {len(conv_rows)}")
        except (json.JSONDecodeError, KeyError):
            pass

    if limit:
        conv_rows = conv_rows[:limit]
    if not conv_rows:
        print("[warn] 没有符合条件的 GPT conversation")
        return 0

    prepared = []
    for idx, (conv_id, _msg_count) in enumerate(conv_rows, 1):
        messages = load_gpt_messages(con, conv_id)
        turns = assemble_turns(messages)
        prepared.append({
            "idx": idx,
            "conversation_id": conv_id,
            "messages": messages,
            "turns": turns,
        })
    con.close()

    if dry_run:
        for p in prepared[:2]:
            print_session_assembly(p["conversation_id"], p["messages"], p["turns"])
        return 0

    if not write:
        for p in prepared:
            print(f"[{p['idx']}/{len(prepared)}] {p['conversation_id'][:30]}.. "
                  f"消息 {len(p['messages'])} -> {len(p['turns'])} turns (dry, 未调 LLM)")
        print(f"\n[dry] 共 {len(prepared)} 个 conversation,未生成摘要。加 --write 调 LLM 生成。")
        return 0

    client = make_llm_client()
    model = os.environ.get("MEM0_LLM_MODEL", "gpt-4o-mini")
    total = len(prepared)
    workers = max(1, min(workers, total))
    print(f"[start] {total} GPT conversation | 并发 {workers} 路 | 模型 {model}")
    t_start = time.time()

    def _process_one(p: dict) -> tuple[dict, SessionSummary, int]:
        conv_id = p["conversation_id"]
        turn_sums, calls = summarize_session(conv_id, p["turns"], client, model, max_chars)
        main_topic = guess_main_topic(client, model, turn_sums)
        summary = SessionSummary(
            session_id=conv_id,
            main_topic=main_topic,
            turn_summaries=turn_sums,
            meta={
                "raw_messages": len(p["messages"]),
                "deduped_messages": len(p["messages"]),
                "turn_count": len(p["turns"]),
                "tool_call_count": 0,
                "llm_calls": calls + 1,
                "source": "GPT",
                "model": model,
                "prompt_version": PROMPT_VERSION,
            },
        )
        return p, summary, calls + 1

    summaries: list[SessionSummary] = []
    total_llm_calls = 0
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_process_one, p): p for p in prepared}
        for fut in as_completed(futures):
            p, summary, calls = fut.result()
            summaries.append(summary)
            total_llm_calls += calls
            done += 1
            print(f"[{done}/{total}] {p['conversation_id'][:30]}.. "
                  f"{len(p['turns'])} turns, {calls} 次调用 "
                  f"(累计 {time.time()-t_start:.0f}s)", flush=True)
            if summaries:
                _incremental_write(summaries)

    elapsed = time.time() - t_start
    summaries.sort(key=lambda s: s.session_id)
    write_outputs(summaries)
    print(f"\n已生成 {len(summaries)} 个 GPT conversation 的叙述摘要,"
          f"LLM 调用 {total_llm_calls} 次,耗时 {elapsed:.0f}s "
          f"(平均 {elapsed/max(len(summaries),1):.1f}s/conversation)。")
    return 0

def print_session_assembly(conv_id: str, messages, turns: list[dict]) -> None:
    print("=" * 70)
    print(f"DRY-RUN: GPT conversation {conv_id[:40]}..")
    print("=" * 70)
    print(f"消息: {len(messages)} -> {len(turns)} turns")
    print()
    print("--- 消息时序(turn_number | role | text前60) ---")
    for m in messages[:10]:
        print(f"  turn={m['turn_number']:3d} | {m['role']:10s} | {m['text'][:60]!r}")
    if len(messages) > 10:
        print(f"  ... 还有 {len(messages) - 10} 条")
    print()
    print("--- turn 渲染样例(喂给 LLM 的文本) ---")
    if turns:
        print(render_turn_text(turns[0], 1)[:500])


def _incremental_write(summaries: list[SessionSummary]) -> None:
    """增量保存:按 session_id 合并,新结果覆盖旧结果。"""
    existing = []
    if OUT_JSON.exists():
        try:
            existing = json.loads(OUT_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = []
    new_entries = {s.session_id: asdict(s) for s in summaries}
    merged_by_id: dict[str, dict] = {s["session_id"]: s for s in existing}
    merged_by_id.update(new_entries)
    merged = [merged_by_id[k] for k in sorted(merged_by_id.keys())]
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSON.open("w", encoding="utf-8") as fh:
        json.dump(merged, fh, ensure_ascii=False, indent=2)


def write_outputs(summaries: list[SessionSummary]) -> None:
    """最终写 JSON + Markdown(全量)。"""
    _incremental_write(summaries)
    merged = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    OUT_MD.write_text(agent_summary_mod._render_markdown_from_entries(merged), encoding="utf-8")
    print(f"  {OUT_JSON.relative_to(ROOT)} ({len(merged)} sessions)")
    print(f"  {OUT_MD.relative_to(ROOT)}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="GPT 对话叙述压缩 (Wave 7 扩展)")
    p.add_argument("--dry-run", action="store_true",
                   help="只打印 2 个 conversation 的统计,不调 LLM")
    p.add_argument("--write", action="store_true", help="调 LLM 生成摘要并落盘")
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                   help=f"只处理前 N 个 conversation(默认 {DEFAULT_LIMIT})")
    p.add_argument("--max-chars", type=int, default=MAX_CHARS_PER_CALL,
                   help=f"单次 LLM 输入阈值,超长分批(默认 {MAX_CHARS_PER_CALL})")
    p.add_argument("--resume", action="store_true",
                   help="跳过已有 conversation(增量续跑)")
    p.add_argument("--workers", type=int, default=None,
                   help=f"并发 conversation 数(默认 {DEFAULT_WORKERS})")
    args = p.parse_args(argv)
    if args.dry_run and args.write:
        print("[error] --dry-run 与 --write 互斥", file=sys.stderr)
        return 2
    workers = args.workers if args.workers is not None else int(
        os.environ.get("SUMMARY_WORKERS", DEFAULT_WORKERS))
    return run(args.dry_run, args.write, args.limit, args.max_chars, args.resume, workers)


if __name__ == "__main__":
    raise SystemExit(main())