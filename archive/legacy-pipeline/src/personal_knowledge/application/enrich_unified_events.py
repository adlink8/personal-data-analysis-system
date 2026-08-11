# =============================================================================
# DEPRECATED — 死代码（PDA-2 旧管线关闭）
# -----------------------------------------------------------------------------
# Phase 20 迁移已删除 Agent/ 目录，本模块引用的
# ROOT/"Agent"/"structured"/"db"/"agent_data.sqlite" 已不存在，运行即报错。
# 新管道（pk-sync conversations）走 ~/.agentsview/sessions.db，不使用本模块；
# 输出表 unified_events_rich 仅被 legacy 集成链消费（均 table_exists 门控，可容忍缺失）。
# 已归档至 archive/legacy-pipeline/，仅备查，勿调用。
# =============================================================================

"""语义增强层(阶段1核心)。

在统合库 personal_system.sqlite 新增 3 张增强表,修复 4 个数据质量缺陷:

A. unified_events_rich  —— 补真实文本
   Agent session 事件的 content 当前是 uuid/时间戳(无语义)。
   本表联接 agent_data.sqlite.session_messages,聚合真实对话进 content_rich。
   GPT/Google/skill/memory 的 content 已有真实文本,直接透传。

B. event_categories_v2  —— 重做分类(剥离元数据污染)
   用 rules.PURE_TOPIC_RULES 只对 title + content_rich 分类,
   不拼入 service/source_table/category,修复 Agent 99.9% 自我命中。
   保留 category_v1 做对照。

C. entity_links_v2  —— 真实跨模块连接
   重写连接逻辑(放弃原 build_entity_links 的死代码类型B),
   用三种真实信号:共享域名、共享项目名、时序链路(搜索→提问→执行)。

设计原则:
- 不改原始数据,不改现有 9 张统合表(只新增增强表,向后兼容)
- 幂等:重复运行结果一致(先 DROP IF EXISTS 再建)
- 依赖 build_integrated_system.py 已生成 personal_system.sqlite

运行: python integration\\scripts\\enrich_unified_events.py
"""

from __future__ import annotations

import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# 让scripts可被 streamlit 或直接 python 运行
sys.path.insert(0, str(Path(__file__).resolve().parent))

from personal_knowledge.core import common
from personal_knowledge.core import rules
# === 路径 ===
ROOT = Path(__file__).resolve().parents[3]
UNIFIED_DB = ROOT / "integration" / "db" / "personal_system.sqlite"
AGENT_DB = ROOT / "Agent" / "structured" / "db" / "agent_data.sqlite"


# === Agent session 文本清洗 ===

# ISO 时间戳前缀,如 "2026-05-06T12:01:05.283Z 真实内容"
TS_PREFIX_RE = re.compile(r"^\s*\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[.\d]*Z?\s*")

# 系统指令/权限噪声模式(出现在 user/developer role 里)
NOISE_PATTERNS = [
    re.compile(r"^#\s*AGENTS?\.?md", re.IGNORECASE),
    re.compile(r"<permissions?\s", re.IGNORECASE),
    re.compile(r"<INSTRUCTIONS?>", re.IGNORECASE),
    re.compile(r"^Capabilities from the ", re.IGNORECASE),
    re.compile(r"^Filesystem sandboxing", re.IGNORECASE),
]

# 噪声文本特征
WIN_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")
UNIX_PATH_RE = re.compile(r"^/[a-z]")
UUID_PREFIX_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-")
ROLLOUT_PREFIX_RE = re.compile(r"^rollout-\d")

# Windows/Unix 路径片段(用于从内容里抽取项目名)
PATH_SEGMENT_RE = re.compile(r"[A-Za-z]:[\\/][^\s\"'<>|]+|/[a-z][\w\-/.]+")


def strip_noise(text: str) -> str:
    """剥离时间戳前缀,返回剩余文本。"""
    return TS_PREFIX_RE.sub("", text or "").strip()


def is_noise(text: str) -> bool:
    """判断清洗后的文本是否为噪声(系统指令/路径/uuid/极短)。"""
    if not text or len(text) < 6:
        return True
    for pat in NOISE_PATTERNS:
        if pat.search(text):
            return True
    if UUID_PREFIX_RE.match(text):
        return True
    if ROLLOUT_PREFIX_RE.match(text):
        return True
    # 纯 Windows/Unix 路径(整条都是路径,没有对话)
    if (WIN_PATH_RE.match(text) or UNIX_PATH_RE.match(text)) and len(text) < 80:
        return True
    # 纯时间戳残留
    if re.fullmatch(r"[\d\-:.TZ\s]+", text):
        return True
    return False


def clean_message(role: str, text: str) -> str:
    """清洗单条消息,返回可用文本或空串(表示应丢弃)。"""
    body = strip_noise(text)
    if role == "developer":  # developer role 全是权限指令噪声
        return ""
    if is_noise(body):
        return ""
    return body


def build_session_content_rich(agent_con: sqlite3.Connection, session_id_col: str) -> dict[str, str]:
    """对每个 Agent session,聚合真实对话进 content_rich。

    返回 {session_id: content_rich}。
    策略:
    - 优先取 user 提问(代表用户意图,信息密度高)
    - 补充 assistant 开头几句(代表实际做了什么)
    - 同 session 内去重(系统指令常重复)
    - 每条截断到合理长度,总长不超过 1200 字符
    """
    # 按 session 聚合消息
    sessions: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for row in agent_con.execute(
        f"SELECT session_id, message_index, role, text_excerpt FROM session_messages "
        f"WHERE session_id IN (SELECT DISTINCT {session_id_col} FROM sessions WHERE {session_id_col} != '') "
        f"ORDER BY session_id, message_index"
    ):
        sid, idx, role, text = row
        cleaned = clean_message(role, text)
        if cleaned:
            sessions[sid].append((idx, role, cleaned))

    result: dict[str, str] = {}
    PER_MSG_LIMIT = 200
    TOTAL_LIMIT = 1200
    USER_FIRST = 4   # 优先取前 4 条 user
    ASST_FIRST = 3   # 补充前 3 条 assistant

    for sid, msgs in sessions.items():
        # 按 message_index 排序,保证对话顺序
        msgs.sort(key=lambda x: x[0])
        seen: set[str] = set()
        picked: list[str] = []

        # 先取 user 提问(意图最关键)
        user_count = 0
        for _idx, role, body in msgs:
            if role != "user":
                continue
            key = body[:80]  # 去重键
            if key in seen:
                continue
            seen.add(key)
            picked.append(f"[问] {body[:PER_MSG_LIMIT]}")
            user_count += 1
            if user_count >= USER_FIRST:
                break

        # 再取 assistant 开头(实际做了什么)
        asst_count = 0
        for _idx, role, body in msgs:
            if role != "assistant":
                continue
            key = body[:80]
            if key in seen:
                continue
            seen.add(key)
            picked.append(f"[答] {body[:PER_MSG_LIMIT]}")
            asst_count += 1
            if asst_count >= ASST_FIRST:
                break

        content_rich = " | ".join(picked)
        if len(content_rich) > TOTAL_LIMIT:
            content_rich = content_rich[:TOTAL_LIMIT] + "…"
        if content_rich:
            result[sid] = content_rich
    return result


# === 分类 v2(剥离元数据)===

def classify_v2(title: str, content_rich: str) -> str:
    """纯净分类:只对 title + content_rich,不拼入 service/source_table。"""
    text = f"{title or ''} {content_rich or ''}".lower()
    for topic, keys in rules.PURE_TOPIC_RULES:
        if any(k.lower() in text for k in keys):
            return topic
    return rules.PURE_TOPIC_DEFAULT


# === 跨模块链接 v2 ===

# 从文本/路径抽取候选项目关键词(用于跨模块匹配)
PROJECT_KEYWORDS = [
    "obsidian", "vault", "数据分析", "个人系统", "画像", "统合",
    "论文", "ppt", "课程", "linux", "python", "题库", "ocr",
    "巡检", "产线", "工业", "anki", "gsd", "agent", "memory",
]

def extract_project_terms(event: dict) -> set[str]:
    """从事件的 title/content/file_name 抽取项目关键词。"""
    text = f"{event.get('title','')} {event.get('content_rich','') or event.get('content','')} {event.get('file_name','')}".lower()
    terms = set()
    for kw in PROJECT_KEYWORDS:
        if kw in text:
            terms.add(kw)
    # 从路径抽取目录名(去扩展名)
    fname = (event.get("file_name") or "").lower()
    if fname:
        base = re.sub(r"\.[a-z0-9]+$", "", fname)
        for seg in re.split(r"[\s_\-.,]+", base):
            if len(seg) >= 4 and seg.isascii() and seg.isalpha():
                terms.add(seg)
    return terms


def build_entity_links_v2(con: sqlite3.Connection) -> list[dict]:
    """三种真实信号建跨模块连接。

    1. 共享域名:三模块出现相同 domain(非空)
    2. 共享项目名:三模块事件含相同项目关键词
    3. 时序链路:时间窗内 Google搜索→GPT提问→Agent执行
    """
    events = []
    con.row_factory = sqlite3.Row
    for r in con.execute(
        "SELECT event_id, source, event_type, service, event_time, month, "
        "title, content, url, domain, file_name FROM unified_events"
    ):
        events.append(dict(r))

    links = []
    seen_links: set[str] = set()

    def add_link(from_id: str, to_id: str, relation: str, strength: float, evidence: str, term: str = ""):
        # 自环跳过,同对去重
        if from_id == to_id:
            return
        key = tuple(sorted([from_id, to_id])) + (relation,) + (term,)
        if key in seen_links:
            return
        seen_links.add(key)
        links.append({
            "link_id": common.sha256_text(f"v2|{relation}|{from_id}|{to_id}|{term}"),
            "from_event_id": from_id,
            "to_event_id": to_id,
            "relation": relation,
            "strength": strength,
            "evidence": evidence,
            "matched_term": term,
        })

    # --- 信号1: 共享域名(只在 Google 内有意义,但记录跨模块同 domain 共现)---
    by_domain: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        d = (e.get("domain") or "").strip().lower()
        if d and d not in ("", "localhost"):
            by_domain[d].append(e)
    for d, evs in by_domain.items():
        if len(evs) < 2:
            continue
        sources = {e["source"] for e in evs}
        # 同域名跨模块,或同模块内同域名多次访问也建链(强度按共现次数)
        for i in range(len(evs)):
            for j in range(i + 1, min(i + 6, len(evs))):  # 每个域名最多连5对,防爆
                add_link(
                    evs[i]["event_id"], evs[j]["event_id"],
                    "shared_domain" if len(sources) >= 2 else "same_domain_repeat",
                    float(len(evs)),
                    f"domain={d}",
                    d,
                )

    # --- 信号2: 共享项目名 ---
    # 先给每个事件算 terms
    for e in events:
        e["_terms"] = extract_project_terms(e)
    by_term: dict[str, list[dict]] = defaultdict(list)
    for e in events:
        for t in e["_terms"]:
            by_term[t].append(e)
    for term, evs in by_term.items():
        if len(evs) < 2:
            continue
        sources = {e["source"] for e in evs}
        if len(sources) < 2:
            continue  # 只记录跨模块的项目名
        # 跨模块同项目名:每个模块各取代表性事件连一条
        per_source: dict[str, dict] = {}
        for e in evs:
            s = e["source"]
            if s not in per_source:
                per_source[s] = e
        src_list = list(per_source.values())
        for i in range(len(src_list)):
            for j in range(i + 1, len(src_list)):
                add_link(
                    src_list[i]["event_id"], src_list[j]["event_id"],
                    "shared_project_term",
                    float(len(evs)),
                    f"term={term}; sources={','.join(sorted(sources))}",
                    term,
                )

    # --- 信号3: 时序链路(Google 搜索/活动 → GPT 提问 → Agent 执行)---
    # 按时间排序,在时间窗内找 Google→GPT→Agent 的链。
    # 注意:三源时间戳无时区且可能跨年(GPT 是 2024,Google/Agent 是 2026),
    # 必须严格同年同月才比较,避免跨年误连。
    def parse_time(t):
        if not t:
            return None
        # 兼容 "2026-06-06T12:16:36" 和 "2024-03-24 18:30:46" 两种格式
        t = t.replace(" ", "T")
        try:
            return datetime.fromisoformat(t[:19])
        except (ValueError, TypeError):
            return None

    timed = []
    for e in events:
        t = parse_time(e.get("event_time"))
        if t:
            e["_time"] = t
            e["_ym"] = (t.year, t.month)  # 用于严格同年同月过滤
            timed.append(e)
    timed.sort(key=lambda x: x["_time"])

    WINDOW_HOURS = 6
    google_events = [e for e in timed if e["source"] == "Google"]
    gpt_events = [e for e in timed if e["source"] == "GPT"]
    agent_events = [e for e in timed if e["source"] == "Agent"]

    def within_window(a, b, hours):
        """严格同年同月 + 时间差在 hours 小时内。"""
        if a["_ym"] != b["_ym"]:
            return False
        return abs((a["_time"] - b["_time"]).total_seconds()) <= hours * 3600

    for g in google_events:
        # 找同年同月、窗口内的 GPT 提问
        nearby_gpt = [p for p in gpt_events if within_window(g, p, WINDOW_HOURS)]
        if not nearby_gpt:
            continue
        for p in nearby_gpt[:3]:
            # 找窗口内的 Agent 执行
            nearby_agent = [a for a in agent_events if within_window(p, a, WINDOW_HOURS)]
            if nearby_agent:
                # 完整链 Google→GPT→Agent
                a = nearby_agent[0]
                gap_min_ga = int(abs((a["_time"] - g["_time"]).total_seconds()) / 60)
                add_link(
                    g["event_id"], a["event_id"],
                    "search_to_execute_chain",
                    3.0,
                    f"Google({g['event_time'][:16]}) -> GPT({p['event_time'][:16]}) -> Agent({a['event_time'][:16]}); span={gap_min_ga}min",
                    "timeline",
                )
            else:
                # 半链 Google→GPT
                gap_min_gp = int(abs((p["_time"] - g["_time"]).total_seconds()) / 60)
                add_link(
                    g["event_id"], p["event_id"],
                    "search_to_ask_chain",
                    2.0,
                    f"Google({g['event_time'][:16]}) -> GPT({p['event_time'][:16]}); span={gap_min_gp}min",
                    "timeline",
                )

    return links


# === 主流程 ===

def enrich(unified_db: Path = UNIFIED_DB, agent_db: Path = AGENT_DB) -> dict:
    """主入口:生成 3 张增强表。返回统计信息。"""
    if not unified_db.exists():
        raise FileNotFoundError(f"统合库不存在,请先运行 build_integrated_system.py: {unified_db}")

    con = sqlite3.connect(unified_db)
    con.row_factory = sqlite3.Row

    stats = {}

    # --- A. unified_events_rich ---
    print("[1/3] 构建 unified_events_rich(补真实文本)...")

    # 先准备 Agent session 的 content_rich 映射
    agent_rich: dict[str, str] = {}  # session_id -> content_rich
    # 需要从统合库的 source_id(=sessions.id)反查 sessions.session_id
    sessions_map: dict[int, str] = {}  # sessions.id -> session_id
    if agent_db.exists():
        ac = sqlite3.connect(agent_db)
        ac.row_factory = sqlite3.Row
        for r in ac.execute("SELECT id, session_id FROM sessions WHERE session_id != ''"):
            sessions_map[r["id"]] = r["session_id"]
        agent_rich = build_session_content_rich(ac, "session_id")
        ac.close()

    rich_rows = []
    for r in con.execute(
        "SELECT event_id, source, source_table, source_id, title, content FROM unified_events"
    ):
        source = r["source"]
        source_table = r["source_table"]
        source_id = r["source_id"]
        title = r["title"] or ""
        old_content = r["content"] or ""

        content_rich = old_content  # 默认透传

        if source == "Agent" and source_table == "sessions":
            # 用 source_id(=sessions.id) 找 session_id, 再查 agent_rich
            try:
                sid_int = int(source_id)
            except (ValueError, TypeError):
                sid_int = None
            session_id = sessions_map.get(sid_int, "") if sid_int is not None else ""
            if session_id and session_id in agent_rich:
                content_rich = agent_rich[session_id]
            # 如果没找到真实对话,保留旧 content(可能是 import 元数据)

        rich_rows.append({
            "event_id": r["event_id"],
            "content_rich": common.short(content_rich, 1500),
            "content_rich_source": "agent_session_messages" if (source == "Agent" and source_table == "sessions" and source_id) else "passthrough",
        })

    # 建表
    con.execute("DROP TABLE IF EXISTS unified_events_rich")
    con.execute(
        "CREATE TABLE unified_events_rich ("
        "event_id TEXT PRIMARY KEY, "
        "content_rich TEXT, "
        "content_rich_source TEXT)"
    )
    con.executemany(
        "INSERT INTO unified_events_rich (event_id, content_rich, content_rich_source) VALUES (:event_id, :content_rich, :content_rich_source)",
        rich_rows,
    )
    con.execute("CREATE INDEX idx_rich_event ON unified_events_rich(event_id)")
    stats["rich_total"] = len(rich_rows)
    stats["rich_from_agent_sessions"] = sum(1 for r in rich_rows if r["content_rich_source"] == "agent_session_messages")
    print(f"    完成: {stats['rich_total']} 条, 其中 {stats['rich_from_agent_sessions']} 条来自 Agent session 消息抽取")

    # --- B. event_categories_v2 ---
    print("[2/3] 构建 event_categories_v2(纯净分类)...")
    # 需要 content_rich
    rich_map = {r["event_id"]: r["content_rich"] for r in rich_rows}
    cat_rows = []
    for r in con.execute("SELECT event_id, source, source_table, title, content FROM unified_events"):
        eid = r["event_id"]
        content_rich = rich_map.get(eid, r["content"] or "")
        cat_v1 = ""  # category_v1 在画像阶段再算对照,这里只存 v2
        cat_v2 = classify_v2(r["title"], content_rich)
        cat_rows.append({
            "event_id": eid,
            "category_v1": cat_v1,
            "category_v2": cat_v2,
        })

    con.execute("DROP TABLE IF EXISTS event_categories_v2")
    con.execute(
        "CREATE TABLE event_categories_v2 ("
        "event_id TEXT PRIMARY KEY, "
        "category_v1 TEXT, "
        "category_v2 TEXT)"
    )
    con.executemany(
        "INSERT INTO event_categories_v2 (event_id, category_v1, category_v2) VALUES (:event_id, :category_v1, :category_v2)",
        cat_rows,
    )
    con.execute("CREATE INDEX idx_catv2_category ON event_categories_v2(category_v2)")

    # 分类分布统计(供验证)
    cat_dist = defaultdict(int)
    for cr in cat_rows:
        cat_dist[cr["category_v2"]] += 1
    stats["category_v2_distribution"] = dict(sorted(cat_dist.items(), key=lambda x: -x[1]))
    print(f"    完成: {len(cat_rows)} 条分类")

    # --- C. entity_links_v2 ---
    print("[3/3] 构建 entity_links_v2(真实跨模块连接)...")
    links = build_entity_links_v2(con)

    con.execute("DROP TABLE IF EXISTS entity_links_v2")
    con.execute(
        "CREATE TABLE entity_links_v2 ("
        "link_id TEXT PRIMARY KEY, "
        "from_event_id TEXT, "
        "to_event_id TEXT, "
        "relation TEXT, "
        "strength REAL, "
        "evidence TEXT, "
        "matched_term TEXT)"
    )
    con.executemany(
        "INSERT INTO entity_links_v2 (link_id, from_event_id, to_event_id, relation, strength, evidence, matched_term) "
        "VALUES (:link_id, :from_event_id, :to_event_id, :relation, :strength, :evidence, :matched_term)",
        links,
    )
    con.execute("CREATE INDEX idx_links_v2_relation ON entity_links_v2(relation)")
    con.execute("CREATE INDEX idx_links_v2_from ON entity_links_v2(from_event_id)")

    # 按关系类型统计
    rel_dist = defaultdict(int)
    for lk in links:
        rel_dist[lk["relation"]] += 1
    stats["links_v2_total"] = len(links)
    stats["links_v2_by_relation"] = dict(sorted(rel_dist.items(), key=lambda x: -x[1]))
    print(f"    完成: {len(links)} 条链接")

    con.commit()
    con.close()
    return stats


def main() -> None:
    print("=" * 60)
    print("语义增强层 enrich_unified_events.py")
    print("=" * 60)
    stats = enrich()
    print()
    print("=" * 60)
    print("增强完成。统计:")
    print(f"  unified_events_rich: {stats['rich_total']} 条")
    print(f"    其中 Agent session 抽取: {stats['rich_from_agent_sessions']} 条")
    print(f"  event_categories_v2 分布:")
    for cat, n in stats["category_v2_distribution"].items():
        print(f"    {cat}: {n}")
    print(f"  entity_links_v2: {stats['links_v2_total']} 条")
    for rel, n in stats["links_v2_by_relation"].items():
        print(f"    {rel}: {n}")
    print("=" * 60)


if __name__ == "__main__":
    main()
