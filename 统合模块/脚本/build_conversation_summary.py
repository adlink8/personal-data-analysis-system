"""Phase 07+: 对话结构化叙述摘要。

与 mem0 候选压缩(原子事实)不同,这个脚本的目标是**保留对话主干和分支**:
对每个 session 逐 turn 生成中文叙述摘要,还原"用户做了什么/为什么/得出什么"。

数据来源:agent_data.sqlite 的 agent_messages + agent_tool_calls + agent_tool_outputs。
杂活(去重、分组、时序还原、摘要生成)全部交给 LLM(小米 MiMo,OpenAI 兼容接口)。

设计依据见 .gsd/phases/07_agent_conversation_normalization_mem0_spike/。

用法:
  python build_conversation_summary.py --dry-run                # 验证去重和分组
  python build_conversation_summary.py --limit 10 --write       # 小样本生成
  OPENAI_API_KEY=... OPENAI_BASE_URL=... MEM0_LLM_MODEL=mimo-v2.5-pro \
    python build_conversation_summary.py --limit 10 --write
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT_DB = ROOT / "Agent" / "结构化数据" / "SQLite数据库" / "agent_data.sqlite"
OUT_JSON = ROOT / "统合模块" / "分析数据" / "ai_context" / "conversation_summaries.json"
OUT_MD = ROOT / "统合模块" / "分析数据" / "ai_context" / "conversation_summaries.md"

DEFAULT_LIMIT = 10          # 小样本验证默认数
MAX_CHARS_PER_CALL = 6000   # 单次喂给 LLM 的 turn 文本阈值,超长滑动窗口分批
TOOL_OUTPUT_MAX = 300       # 喂给 LLM 时 tool output 截断长度(原文回源文件)


@dataclass
class TurnSummary:
    turn_id: str | None
    narrative: str
    tools_used: list[str] = field(default_factory=list)
    source_refs: list[str] = field(default_factory=list)


@dataclass
class SessionSummary:
    session_id: str
    main_topic: str
    turn_summaries: list[TurnSummary]
    meta: dict


def dedup_messages(rows: list[tuple]) -> list[dict]:
    """去重:消除同一 turn 内 message/agent_message 的镜像重复。

    真实数据里每条消息在同一 turn 内连续出现两次(response_item.message +
    event_msg.agent_message,event_index 相邻),只在 turn_id 范围内去重,保留首次出现。

    关键:必须 per-turn 去重,不能全局去重。用户在不同 turn 里可能重复发送同一句
    话(例如上一个 turn 没得到回复又问了一次),这是真实的两个 turn,跨 turn 去重会
    把后一个 turn 的 user 消息丢掉但留下它的 assistant 回复,导致因果链断裂。
    """
    seen: set[tuple] = set()
    out: list[dict] = []
    for r in rows:
        # r = (event_index, turn_id, role, text, payload_type, raw_file, line_no)
        event_index, turn_id, role, text, payload_type, raw_file, line_no = r
        if not text or not text.strip():
            continue
        # turn_id 纳入 key:不同 turn 的相同文本各自保留
        key = (turn_id, role, text[:120])
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "event_index": event_index,
            "turn_id": turn_id,
            "role": role,
            "text": text,
            "payload_type": payload_type,
            "raw_file": raw_file,
            "line_no": line_no,
        })
    return out


def load_tool_calls(con, session_id: str) -> dict[int, dict]:
    """加载 session 的 tool_calls,按 event_index 索引。"""
    rows = con.execute(
        "select event_index, turn_id, call_id, tool_name, arguments, status, "
        "raw_file, line_no from agent_tool_calls where session_id=?",
        (session_id,),
    ).fetchall()
    return {r[0]: {
        "turn_id": r[1], "call_id": r[2], "tool_name": r[3],
        "arguments": r[4], "status": r[5], "raw_file": r[6], "line_no": r[7],
    } for r in rows}


def load_tool_outputs(con, session_id: str) -> dict[str, str]:
    """加载 session 的 tool_outputs,按 call_id 索引(取截断摘要)。"""
    rows = con.execute(
        "select call_id, output from agent_tool_outputs where session_id=?",
        (session_id,),
    ).fetchall()
    return {r[0]: (r[1][:TOOL_OUTPUT_MAX] if r[1] else "") for r in rows}


def assemble_turns(messages: list[dict], tool_calls: dict, tool_outputs: dict) -> list[dict]:
    """把去重后的消息 + tool 调用组装成 turn 列表,保留时序。

    turn_id 为空的归入"序言"(通常含开场 user 指令)。每个 turn 含该范围内的
    所有 message 和 tool 调用链,按 event_index 排序。

    turn_id 为 NULL 的"序言"(Codex 早期会话无 turn_context 标记)按 user 消息
    切分成多个虚拟 turn,避免把整个开场塞成一段。
    """
    if not messages:
        return []
    # 第一遍:按 turn_id 分组(None 先作为一个池子)
    turns: list[dict] = []
    turn_map: dict[str, dict] = {}
    null_pool: list[dict] = []  # turn_id=NULL 的消息池,稍后按 user 切分
    for m in messages:
        tid = m["turn_id"]
        if tid is None:
            null_pool.append(m)
            continue
        if tid not in turn_map:
            t = {"turn_id": tid, "messages": [], "tools": [], "source_refs": []}
            turn_map[tid] = t
            turns.append(t)
        turn_map[tid]["messages"].append(m)
        turn_map[tid]["source_refs"].append(f"{m['raw_file']}:{m['line_no']}")

    # 序言池按 user 消息切分:每个 user 开启一个新虚拟 turn,跟到下一个 user 前的所有 assistant
    null_turns = _split_null_pool_by_user(null_pool)
    # 序言 turn 排在前面(开场对话先发生)
    turns = null_turns + turns

    # 把 tool_calls 按 turn_id 归入对应 turn;无 turn_id 的 tool 归入最近的虚拟序言 turn
    for ev_idx, tc in sorted(tool_calls.items()):
        tid = tc["turn_id"]
        tool_entry = {
            "tool_name": tc["tool_name"],
            "call_id": tc["call_id"],
            "arguments": tc["arguments"],
            "output": tool_outputs.get(tc["call_id"], ""),
            "status": tc["status"],
            "raw_file": tc["raw_file"],
            "line_no": tc["line_no"],
        }
        if tid is not None and tid in turn_map:
            turn_map[tid]["tools"].append(tool_entry)
        elif null_turns:
            # 无 turn_id 的 tool:按 event_index 找它之前最近的虚拟序言 turn
            _attach_tool_to_nearest_turn(tool_entry, ev_idx, null_turns)
        elif turns:
            turns[0]["tools"].append(tool_entry)
    return turns


def _split_null_pool_by_user(pool: list[dict]) -> list[dict]:
    """把 turn_id=NULL 的消息池按 user 消息切分成多个虚拟 turn。

    每个 user 消息开启一个新 turn,其后的 assistant 消息(直到下一个 user)归入该 turn。
    开头的 developer/system 消息归入第一个 turn。
    """
    if not pool:
        return []
    turns: list[dict] = []
    cur = {"turn_id": None, "messages": [], "tools": [], "source_refs": []}
    turns.append(cur)
    for m in pool:
        # 新 user 消息开启新 turn(但第一个 turn 为空时直接用)
        if m["role"] == "user" and cur["messages"]:
            cur = {"turn_id": None, "messages": [], "tools": [], "source_refs": []}
            turns.append(cur)
        cur["messages"].append(m)
        cur["source_refs"].append(f"{m['raw_file']}:{m['line_no']}")
    return turns


def _attach_tool_to_nearest_turn(tool: dict, ev_idx: int, turns: list[dict]) -> None:
    """把无 turn_id 的 tool 按它的 event_index 归入最近的虚拟序言 turn。

    用该 turn 内最后一条消息的 event_index 比较,归入 ev_idx 不超过该 turn 的最大 turn。
    """
    for t in reversed(turns):
        if t["messages"] and t["messages"][-1]["event_index"] <= ev_idx:
            t["tools"].append(tool)
            return
    # 兜底:归入第一个 turn
    turns[0]["tools"].append(tool)


def render_turn_text(turn: dict, turn_no: int) -> str:
    """把一个 turn 渲染成喂给 LLM 的纯文本(保留角色和因果)。"""
    lines = [f"--- Turn {turn_no} ---"]
    for m in turn["messages"]:
        role_label = {"user": "用户", "assistant": "助手", "developer": "系统"}.get(
            m["role"], m["role"]
        )
        lines.append(f"[{role_label}] {m['text']}")
    for t in turn["tools"]:
        out = t["output"]
        out_preview = (out[:200] + "...") if len(out) > 200 else out
        lines.append(
            f"[工具调用] {t['tool_name']}(参数: {t['arguments'][:150]}) "
            f"-> {out_preview or '(无输出)'}"
        )
    return "\n".join(lines)


def chunk_turns(turn_texts: list[str], max_chars: int) -> list[list[str]]:
    """把 turn 文本列表按 max_chars 滑动窗口分批(每批不超阈值)。"""
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


SUMMARY_SYSTEM_PROMPT = """你是对话结构化摘要助手。你的任务是把一段 Agent(Codex)对话还原成**逐 turn 的中文叙述摘要**,目标是保留对话的主干和分支因果,而不是压缩成零散事实。

要求:
1. 每个 Turn 输出一段中文叙述,描述:用户提出了什么/想做什么、助手如何回应、用了什么工具、得出了什么结论或做了什么决策。
2. 保留因果关系和关键措辞(如用户的具体要求、偏好的表述),不要过度压缩。
3. 区分"稳定的偏好/事实"和"一次性的操作指令",但对一次性指令也要简要记录它发生了什么。
4. 工具调用只需记录"调了什么工具、做了什么",不要复述完整输出。
5. 只输出摘要本身,按 `Turn N:` 分段,不要加额外解释。"""


SUMMARY_USER_PROMPT_TEMPLATE = """下面是一个 Agent 会话的多个 turn(已按时间顺序排列)。请生成逐 turn 的中文叙述摘要。

{turns_text}

请按 `Turn {start_no}:` 的格式逐 turn 输出叙述摘要。"""


def make_llm_client():
    """构造 OpenAI 兼容 client,配置全走环境变量。"""
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("[error] 未安装 openai 库,请运行: pip install openai")
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("MEM0_API_KEY")
    if not api_key:
        sys.exit("[error] 未设置 OPENAI_API_KEY / MEM0_API_KEY")
    return OpenAI()  # 自动读 OPENAI_API_KEY / OPENAI_BASE_URL


def summarize_chunk(client, model: str, chunk_text: str, start_no: int) -> str:
    """调用 LLM 对一批 turn 生成叙述摘要,返回摘要文本。"""
    user_prompt = SUMMARY_USER_PROMPT_TEMPLATE.format(
        turns_text=chunk_text, start_no=start_no
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


def parse_turn_summaries(raw: str, turn_count: int) -> list[str]:
    """把 LLM 返回的 `Turn N: ...` 文本拆成每 turn 一段的列表。"""
    import re
    # 按 "Turn N:" 切分
    parts = re.split(r"\n*Turn\s+\d+\s*[:：]\s*", raw)
    parts = [p.strip() for p in parts if p.strip()]
    return parts[:turn_count] if len(parts) >= turn_count else parts


def summarize_session(session_id: str, turns: list[dict], client, model: str,
                      max_chars: int) -> tuple[list[TurnSummary], int]:
    """对单个 session 生成逐 turn 摘要。返回 (turn摘要列表, LLM调用次数)。"""
    turn_texts = [render_turn_text(t, i + 1) for i, t in enumerate(turns)]
    chunks = chunk_turns(turn_texts, max_chars)
    turns_per_chunk = [len(c) for c in chunks]
    # 每批的起始 turn 编号
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
            raw = summarize_chunk(client, model, chunk_text, start_no)
            parts = parse_turn_summaries(raw, len(chunk))
            all_narratives.extend(parts)
        except Exception as exc:
            failed += 1
            if failed <= 2:
                print(f"[warn] LLM 摘要失败({failed}, session={session_id[:24]}..): "
                      f"{type(exc).__name__}: {str(exc)[:100]}", file=sys.stderr)
            # 失败时用原始 turn 文本兜底
            all_narratives.extend([t.split("\n", 1)[0] for t in chunk])

    # 组装 TurnSummary
    result = []
    for i, t in enumerate(turns):
        narrative = all_narratives[i] if i < len(all_narratives) else "(摘要缺失)"
        result.append(TurnSummary(
            turn_id=t["turn_id"],
            narrative=narrative,
            tools_used=list({tool["tool_name"] for tool in t["tools"]}),
            source_refs=t["source_refs"][:3],  # 每个保留前3个证据引用
        ))
    return result, len(chunks)


def guess_main_topic(client, model: str, turn_summaries: list[TurnSummary]) -> str:
    """从 turn 摘要提取 session 主题(一次轻量 LLM 调用)。"""
    if not turn_summaries:
        return ""
    combined = "\n".join(f"Turn{i+1}: {t.narrative[:100]}" for i, t in enumerate(turn_summaries))
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "用一句中文概括这个会话的主要话题,不超过20字,只输出话题本身。"},
                {"role": "user", "content": combined},
            ],
            temperature=0.2,
            max_tokens=200,  # MiMo 是推理模型,reasoning tokens 占配额,需放宽
        )
        topic = resp.choices[0].message.content.strip().strip("。.")
        # 防止 reasoning 占满导致空输出:兜底用第一个 turn 摘要前 20 字
        return topic if topic else turn_summaries[0].narrative[:20]
    except Exception:
        return turn_summaries[0].narrative[:20]


def run(dry_run: bool, write: bool, limit: int | None, max_chars: int) -> int:
    if not AGENT_DB.exists():
        print(f"[error] 缺少数据库: {AGENT_DB.relative_to(ROOT)}")
        return 1

    import sqlite3
    con = sqlite3.connect(AGENT_DB)

    # 选 session:优先选消息量适中(10-200条)的,验证更有代表性
    session_rows = con.execute(
        "select session_id, count(*) c from agent_messages group by session_id "
        "having c between 10 and 200 order by session_id"
    ).fetchall()
    if limit:
        session_rows = session_rows[:limit]
    if not session_rows:
        print("[warn] 没有符合条件的 session")
        return 0

    use_llm = write and not dry_run
    client = make_llm_client() if use_llm else None
    model = os.environ.get("MEM0_LLM_MODEL", "gpt-4o-mini")

    summaries: list[SessionSummary] = []
    total_llm_calls = 0

    for idx, (session_id, _msg_count) in enumerate(session_rows, 1):
        # 加载并去重消息
        raw_msgs = con.execute(
            "select event_index, turn_id, role, text, payload_type, raw_file, line_no "
            "from agent_messages where session_id=? and role in ('user','assistant') "
            "order by event_index",
            (session_id,),
        ).fetchall()
        messages = dedup_messages(raw_msgs)
        tool_calls = load_tool_calls(con, session_id)
        tool_outputs = load_tool_outputs(con, session_id)
        turns = assemble_turns(messages, tool_calls, tool_outputs)

        if dry_run:
            print_session_assembly(session_id, raw_msgs, messages, turns)
            if idx >= 1:  # dry-run 只看 1 个 session
                break
            continue

        if not use_llm:
            print(f"[{idx}/{len(session_rows)}] {session_id[:30]}.. "
                  f"消息 {len(raw_msgs)} -> 去重 {len(messages)} -> {len(turns)} turns "
                  f"(dry, 未调 LLM)")
            continue

        print(f"[{idx}/{len(session_rows)}] {session_id[:30]}.. "
              f"消息 {len(raw_msgs)} -> 去重 {len(messages)} -> {len(turns)} turns, "
              f"生成摘要...", end=" ", flush=True)
        turn_sums, calls = summarize_session(session_id, turns, client, model, max_chars)
        main_topic = guess_main_topic(client, model, turn_sums)
        total_llm_calls += calls + 1
        summaries.append(SessionSummary(
            session_id=session_id,
            main_topic=main_topic,
            turn_summaries=turn_sums,
            meta={
                "raw_messages": len(raw_msgs),
                "deduped_messages": len(messages),
                "turn_count": len(turns),
                "tool_call_count": len(tool_calls),
                "llm_calls": calls + 1,
                "source": "Agent",
            },
        ))
        print(f"{calls + 1} 次调用")

    con.close()

    if dry_run:
        return 0

    if not write or not summaries:
        print(f"\n[dry] 共 {len(session_rows)} 个 session,未生成摘要。加 --write 调 LLM 生成。")
        return 0

    write_outputs(summaries)
    print(f"\n已生成 {len(summaries)} 个 session 的叙述摘要,LLM 调用 {total_llm_calls} 次。")
    return 0


def print_session_assembly(session_id: str, raw_msgs, messages: list[dict],
                           turns: list[dict]) -> None:
    """dry-run:打印单个 session 的去重和分组结果。"""
    print("=" * 70)
    print(f"DRY-RUN: session {session_id[:40]}..")
    print("=" * 70)
    print(f"原始消息: {len(raw_msgs)} -> 去重后: {len(messages)} "
          f"(冗余 {len(raw_msgs) - len(messages)})")
    print(f"turn 分组: {len(turns)} 个 turn")
    print()
    print("--- 去重后消息时序(event_index | turn | role | text前50) ---")
    for m in messages[:15]:
        tid = (m["turn_id"] or "无")[:12]
        print(f"  {m['event_index']:5d} | {tid:12s} | {m['role']:10s} | "
              f"{m['text'][:50]!r}")
    if len(messages) > 15:
        print(f"  ... 还有 {len(messages) - 15} 条")
    print()
    print("--- turn 分组结构 ---")
    for i, t in enumerate(turns[:5], 1):
        tid = (t["turn_id"] or "序言")[:12]
        print(f"  Turn{i} ({tid}): {len(t['messages'])} 条消息, {len(t['tools'])} 个工具调用")
    if len(turns) > 5:
        print(f"  ... 还有 {len(turns) - 5} 个 turn")
    print()
    print("--- 单个 turn 渲染样例(喂给 LLM 的文本) ---")
    if turns:
        print(render_turn_text(turns[0], 1)[:500])


def write_outputs(summaries: list[SessionSummary]) -> None:
    """写 JSON + Markdown。"""
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with OUT_JSON.open("w", encoding="utf-8") as fh:
        json.dump([asdict(s) for s in summaries], fh, ensure_ascii=False, indent=2)

    lines = ["# 对话结构化叙述摘要", "",
             f"共 {len(summaries)} 个 session,逐 turn 叙述,保留主干与分支因果。", ""]
    for s in summaries:
        lines.append(f"## {s.main_topic}")
        lines.append(f"*session: `{s.session_id}` | "
                     f"{s.meta['turn_count']} turns, "
                     f"{s.meta['deduped_messages']} 条消息(去重后)*")
        lines.append("")
        for i, t in enumerate(s.turn_summaries, 1):
            lines.append(f"**Turn {i}:**")
            lines.append(t.narrative)
            if t.tools_used:
                lines.append(f"*工具: {', '.join(t.tools_used)}*")
            lines.append("")
        lines.append("---\n")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"  {OUT_JSON.relative_to(ROOT)}")
    print(f"  {OUT_MD.relative_to(ROOT)}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="对话结构化叙述摘要 (Phase 07+)")
    p.add_argument("--dry-run", action="store_true",
                   help="只打印 1 个 session 的去重和分组结果,不调 LLM")
    p.add_argument("--write", action="store_true", help="调 LLM 生成摘要并落盘")
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                   help=f"只处理前 N 个 session(默认 {DEFAULT_LIMIT})")
    p.add_argument("--max-chars", type=int, default=MAX_CHARS_PER_CALL,
                   help=f"单次 LLM 输入阈值,超长分批(默认 {MAX_CHARS_PER_CALL})")
    args = p.parse_args(argv)
    if dry_run_and_write := (args.dry_run and args.write):
        print("[error] --dry-run 与 --write 互斥", file=sys.stderr)
        return 2
    return run(args.dry_run, args.write, args.limit, args.max_chars)


if __name__ == "__main__":
    raise SystemExit(main())
