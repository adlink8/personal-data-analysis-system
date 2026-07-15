"""Phase 07 Wave 3: 用户想法片段切分。

从清洗后的 Agent/GPT 对话中抽取"用户想法片段",解决一个对话多方向的问题。
这是 Wave 4 mem0 候选压缩的输入层。设计依据见
.gsd/phases/07_agent_conversation_normalization_mem0_spike/。

输入:
  - Agent: agent_data.sqlite 的 agent_messages (role=user,排除 developer/assistant)
  - GPT:   chatgpt_data.db 的 messages (role=user)

切分规则(确定性,不用 LLM):
  - 双换行 / 单换行后的列表项开头 (-, *, 数字., •)
  - 明显话题切换标记(如多个连续分隔符)
  - 单段长度上限 (MAX_SEGMENT_CHARS),超长再切

输出:
  - dry-run 打印样本
  - --write 写入 integration/analysis/ai_context/conversation_segments.json
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
AGENT_DB = ROOT / "Agent" / "structured" / "db" / "agent_data.sqlite"
GPT_DB = ROOT / "GPT" / "structured" / "db" / "chatgpt_data.db"
OUT_JSON = ROOT / "integration" / "analysis" / "ai_context" / "conversation_segments.json"

MAX_SEGMENT_CHARS = 600  # 单段上限,超长按句号/换行再切
MIN_SEGMENT_CHARS = 8    # 短于此当作噪声丢弃(如 "ok", "好的")

# 列表项开头: - * • 或 数字. 或 数字)
LIST_ITEM_RE = re.compile(r"^\s*([-*•]|\d+[.)])\s+")
# 话题切换: 连续 3 个以上同类分隔符
SPLITTER_RE = re.compile(r"\n{2,}")


@dataclass
class Segment:
    segment_id: str
    source: str
    conversation_id: str
    turn_id: str | None
    message_id: str
    segment_index: int
    text: str
    topic_hint: str
    intent_type: str
    source_ref: str


def split_text(text: str) -> list[str]:
    """把一条长用户消息切成多个候选片段。

    策略:先按双换行分块,块内若超长再按单换行/句号细切。返回去空去重后的片段。
    """
    text = text.strip()
    if not text:
        return []
    # 1. 按双换行分块
    blocks = [b.strip() for b in SPLITTER_RE.split(text) if b.strip()]
    out: list[str] = []
    for blk in blocks:
        # 列表项天然是多个并列想法,无论长度都先按列表项切开
        if LIST_ITEM_RE.search(blk):
            sub = re.split(r"(?=^\s*[-*•]\s+)|(?=^\s*\d+[.)]\s+)", blk, flags=re.MULTILINE)
        elif len(blk) <= MAX_SEGMENT_CHARS:
            out.append(blk)
            continue
        else:
            # 超长非列表块:按单换行再切
            sub = blk.split("\n")
        for s in sub:
            s = s.strip()
            if not s:
                continue
            if len(s) > MAX_SEGMENT_CHARS:
                # 还超长:按句号/问号硬切
                s2 = re.split(r"(?<=[。!?.!?])\s+", s)
                cur = ""
                for piece in s2:
                    if len(cur) + len(piece) <= MAX_SEGMENT_CHARS:
                        cur += piece
                    else:
                        if cur:
                            out.append(cur)
                        cur = piece
                if cur:
                    out.append(cur)
            else:
                out.append(s)
    # 去重保序,丢弃过短噪声
    seen = set()
    result = []
    for s in out:
        if len(s) < MIN_SEGMENT_CHARS:
            continue
        if s in seen:
            continue
        seen.add(s)
        result.append(s)
    return result


def guess_intent(text: str) -> str:
    """粗略判断意图类型(确定性规则,非 NLP)。"""
    t = text.lstrip()
    if t.startswith(("如何", "怎么", "怎样", "如何能", "怎么把", "怎么能")):
        return "question_howto"
    if t.startswith(("什么是", "什么叫", "为什么", "为何")):
        return "question_concept"
    if re.match(r"^(帮我|请|能不能|可以|给我|生成|创建|写一个|写个|做一个|做份)", t):
        return "request_task"
    if t.startswith(("- ", "* ", "• ")) or LIST_ITEM_RE.match(t):
        return "list_spec"
    if "?" in t or "？" in t:
        return "question"
    return "statement"


def guess_topic_hint(text: str) -> str:
    """从片段提取前若干字作为话题提示(不做语义分析)。"""
    t = text.replace("\n", " ").strip()
    return t[:40] + ("…" if len(t) > 40 else "")


def build_agent_segments(limit: int | None) -> list[Segment]:
    """从 agent_messages 抽取 role=user 的片段。"""
    if not AGENT_DB.exists():
        return []
    con = sqlite3.connect(AGENT_DB)
    segs: list[Segment] = []
    try:
        rows = con.execute(
            "select session_id, turn_id, rowid, text, raw_file, line_no "
            "from agent_messages where role='user' and text is not null and length(text)>=? "
            "order by rowid",
            (MIN_SEGMENT_CHARS,),
        ).fetchall()
        if limit:
            rows = rows[:limit]
        for session_id, turn_id, msg_rowid, text, raw_file, line_no in rows:
            parts = split_text(text)
            for idx, p in enumerate(parts):
                segs.append(Segment(
                    segment_id=f"agt:{msg_rowid}:{idx}",
                    source="Agent",
                    conversation_id=session_id,
                    turn_id=turn_id,
                    message_id=str(msg_rowid),
                    segment_index=idx,
                    text=p,
                    topic_hint=guess_topic_hint(p),
                    intent_type=guess_intent(p),
                    source_ref=f"{raw_file}:{line_no}",
                ))
    finally:
        con.close()
    return segs


def build_gpt_segments(limit: int | None) -> list[Segment]:
    """从 GPT messages 抽取 role=user 的片段。"""
    if not GPT_DB.exists():
        return []
    con = sqlite3.connect(GPT_DB)
    segs: list[Segment] = []
    try:
        rows = con.execute(
            "select id, conversation_id, turn_number, content "
            "from messages where role='user' and content is not null and length(content)>=? "
            "order by id",
            (MIN_SEGMENT_CHARS,),
        ).fetchall()
        if limit:
            rows = rows[:limit]
        for msg_id, conv_id, turn_no, content in rows:
            parts = split_text(content)
            for idx, p in enumerate(parts):
                segs.append(Segment(
                    segment_id=f"gpt:{msg_id}:{idx}",
                    source="GPT",
                    conversation_id=conv_id or "",
                    turn_id=str(turn_no) if turn_no is not None else None,
                    message_id=str(msg_id),
                    segment_index=idx,
                    text=p,
                    topic_hint=guess_topic_hint(p),
                    intent_type=guess_intent(p),
                    source_ref=f"chatgpt_data.db:messages:id={msg_id}",
                ))
    finally:
        con.close()
    return segs


def run(dry_run: bool, write: bool, source: str, limit: int | None) -> int:
    if dry_run and write:
        print("[error] --dry-run 与 --write 互斥", file=sys.stderr)
        return 2

    sources = ["Agent", "GPT"] if source == "all" else [source]
    all_segs: list[Segment] = []
    for src in sources:
        if src == "Agent":
            segs = build_agent_segments(limit)
        elif src == "GPT":
            segs = build_gpt_segments(limit)
        else:
            print(f"[warn] 未知 source: {src}", file=sys.stderr)
            continue
        print(f"[{src}] 抽取片段: {len(segs)}")
        all_segs.extend(segs)

    # 意图分布统计
    from collections import Counter
    intent_dist = Counter(s.intent_type for s in all_segs)
    print(f"\n总片段: {len(all_segs)}  意图分布:")
    for k, v in intent_dist.most_common():
        print(f"  {k:18s} {v}")

    if dry_run:
        print("\n--- dry-run 样本(前 20)---")
        for s in all_segs[:20]:
            print(f"[{s.source}] {s.intent_type:14s} | {s.topic_hint}")
        return 0

    if write:
        OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
        data = [s.__dict__ for s in all_segs]
        with OUT_JSON.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        print(f"\n已写入 {len(data)} 条片段到 {OUT_JSON.relative_to(ROOT)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="用户想法片段切分 (Phase 07 Wave 3)")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--write", action="store_true")
    p.add_argument("--source", choices=["Agent", "GPT", "all"], default="all")
    p.add_argument("--limit", type=int, default=None, help="只处理前 N 条源消息")
    args = p.parse_args(argv)
    return run(args.dry_run, args.write, args.source, args.limit)


if __name__ == "__main__":
    raise SystemExit(main())
