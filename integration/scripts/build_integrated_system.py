from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path.cwd().resolve()
INTEGRATED = ROOT / "integration"
INPUT_INDEX = INTEGRATED / "raw_index"
STRUCTURED = INTEGRATED / "structured"
ANALYSIS = INTEGRATED / "analysis"
DB_DIR = INTEGRATED / "db"
SCRIPTS = INTEGRATED / "scripts"
OUT_DB = DB_DIR / "personal_system.sqlite"

GOOGLE_DB = ROOT / "Google" / "structured" / "db" / "google_data.sqlite"
GPT_DB = ROOT / "GPT" / "structured" / "db" / "chatgpt_data.db"
AGENT_DB = ROOT / "Agent" / "structured" / "db" / "agent_data.sqlite"

SOURCE_DBS = {
    "Google": GOOGLE_DB,
    "GPT": GPT_DB,
    "Agent": AGENT_DB,
}

SOURCE_DB_LABELS = {
    "Google": "Google/structured/sqlite/google_data.sqlite",
    "GPT": "GPT/structured/sqlite/chatgpt_data.db",
    "Agent": "Agent/structured/sqlite/agent_data.sqlite",
}

TOPIC_RULES = [
    ("AI / Agent / 模型", ["ai", "agent", "gpt", "gemini", "codex", "claude", "hermes", "模型", "智能体", "提示词", "mcp"]),
    ("编程 / 调试 / 工具", ["python", "sqlite", "数据库", "代码", "scripts", "debug", "bug", "报错", "接口", "api", "docker"]),
    ("数据分析 / 个人系统", ["数据分析", "takeout", "sqlite", "画像", "统合", "结构化", "分析", "数据库"]),
    ("课程 / 学习 / 文档", ["课程", "学习", "考试", "ppt", "文档", "报告", "论文", "教材"]),
    ("项目 / 工作流", ["项目", "workflow", "工作流", "gsd", "roadmap", "计划", "milestone"]),
    ("地图 / 地点", ["地图", "地点", "location", "maps", "地址"]),
    ("娱乐 / 生活", ["youtube", "视频", "游戏", "音乐", "娱乐", "生活"]),
]

TOOL_NAMES = [
    "Codex",
    "ChatGPT",
    "GPT",
    "Gemini",
    "Claude",
    "Hermes",
    "WorkBuddy",
    "Cline",
    "Cursor",
    "Ollama",
    "Google",
    "YouTube",
    "Chrome",
    "SQLite",
    "GSD",
]


def ensure_dirs() -> None:
    for path in [INPUT_INDEX, STRUCTURED, ANALYSIS, DB_DIR, SCRIPTS]:
        path.mkdir(parents=True, exist_ok=True)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def norm(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def short(value: object, limit: int = 2000) -> str:
    return norm(value)[:limit]


def event_id(source: str, source_table: str, source_id: object) -> str:
    return sha256_text(f"{source}|{source_table}|{source_id}")


def entity_id(entity_type: str, name: str) -> str:
    return sha256_text(f"{entity_type}|{norm(name).lower()}")


def classify_topic(text: str) -> str:
    low = text.lower()
    for topic, keys in TOPIC_RULES:
        if any(k.lower() in low for k in keys):
            return topic
    return "其他 / 未分类"


def extract_domain(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    return parsed.netloc.lower()


def extract_tools(text: str) -> list[str]:
    low = text.lower()
    found = []
    for tool in TOOL_NAMES:
        if tool.lower() in low:
            found.append(tool)
    return sorted(set(found))


def add_entity(entities: dict[str, dict], entity_type: str, name: str, source: str = "", evidence: str = "") -> str:
    name = norm(name)
    if not name:
        return ""
    eid = entity_id(entity_type, name)
    current = entities.get(eid)
    if not current:
        entities[eid] = {
            "entity_id": eid,
            "entity_type": entity_type,
            "name": name,
            "source_count": 1 if source else 0,
            "event_count": 0,
            "first_source": source,
            "evidence": short(evidence, 500),
        }
    else:
        if source and source not in (current.get("first_source") or ""):
            current["source_count"] = int(current["source_count"]) + 1
    return eid


def link_event(event_entities: list[dict], entities: dict[str, dict], eid: str, event: dict, relation: str) -> None:
    if not eid:
        return
    entities[eid]["event_count"] = int(entities[eid]["event_count"]) + 1
    event_entities.append(
        {
            "event_id": event["event_id"],
            "entity_id": eid,
            "relation": relation,
            "source": event["source"],
        }
    )


def connect_event_entities(event: dict, entities: dict[str, dict], event_entities: list[dict]) -> None:
    text = " ".join([event.get("title", ""), event.get("content", ""), event.get("category", ""), event.get("service", "")])
    category = event.get("category") or "未分类"
    link_event(event_entities, entities, add_entity(entities, "category", category, event["source"], text), event, "has_source_category")

    theme = classify_topic(text)
    link_event(event_entities, entities, add_entity(entities, "theme", theme, event["source"], text), event, "classified_as_theme")

    service = event.get("service", "")
    if service:
        link_event(event_entities, entities, add_entity(entities, "service", service, event["source"], text), event, "from_service")

    domain = event.get("domain", "")
    if domain:
        link_event(event_entities, entities, add_entity(entities, "domain", domain, event["source"], event.get("url", "")), event, "mentions_domain")

    for tool in extract_tools(text):
        link_event(event_entities, entities, add_entity(entities, "tool", tool, event["source"], text), event, "mentions_tool")

    file_name = event.get("file_name", "")
    if file_name:
        link_event(event_entities, entities, add_entity(entities, "file", file_name, event["source"], text), event, "references_file")

    session_id = event.get("session_id", "")
    if session_id:
        link_event(event_entities, entities, add_entity(entities, "session", session_id, event["source"], text), event, "belongs_to_session")


def connect_keywords(entities: dict[str, dict], event_entities: list[dict], event: dict, keywords: list[str]) -> None:
    for keyword in keywords:
        if not keyword:
            continue
        eid = add_entity(entities, "keyword", keyword, event["source"], event.get("title", ""))
        link_event(event_entities, entities, eid, event, "has_keyword")


def rows_from_google() -> tuple[list[dict], list[dict]]:
    con = sqlite3.connect(GOOGLE_DB)
    con.row_factory = sqlite3.Row
    events = []
    input_rows = []
    for r in con.execute("select * from activities"):
        title = norm(r["title_or_query"])
        content = short(r["raw_excerpt"])
        url = norm(r["url"])
        events.append(
            {
                "event_id": event_id("Google", "activities", r["id"]),
                "source": "Google",
                "source_table": "activities",
                "source_id": str(r["id"]),
                "event_type": "activity",
                "service": norm(r["service"]),
                "event_time": norm(r["event_at"]),
                "month": norm(r["month"]),
                "title": title,
                "content": content,
                "category": norm(r["category"]),
                "url": url,
                "domain": norm(r["domain"]) or extract_domain(url),
                "file_name": Path(url).name if url and "." in Path(url).name else "",
                "session_id": "",
                "weight": 1.0,
            }
        )
    for r in con.execute("select * from gemini_attachments"):
        events.append(
            {
                "event_id": event_id("Google", "gemini_attachments", r["id"]),
                "source": "Google",
                "source_table": "gemini_attachments",
                "source_id": str(r["id"]),
                "event_type": "attachment",
                "service": "Gemini Apps",
                "event_time": "",
                "month": "",
                "title": norm(r["file_name"]),
                "content": f"Gemini attachment {norm(r['extension'])} {norm(r['size_kb'])} KB",
                "category": norm(r["category"]),
                "url": "",
                "domain": "",
                "file_name": norm(r["file_name"]),
                "session_id": "",
                "weight": 0.25,
            }
        )
    for table in ["activities", "gemini_attachments", "map_details"]:
        count = con.execute(f'select count(*) from "{table}"').fetchone()[0]
        input_rows.append({"source": "Google", "database_path": SOURCE_DB_LABELS["Google"], "table_name": table, "row_count": count})
    con.close()
    return events, input_rows


def rows_from_gpt() -> tuple[list[dict], list[dict], dict[str, list[str]]]:
    con = sqlite3.connect(GPT_DB)
    con.row_factory = sqlite3.Row
    events = []
    keywords_by_conv: dict[str, list[str]] = defaultdict(list)
    for r in con.execute("select conversation_id, keyword from keywords"):
        keywords_by_conv[str(r["conversation_id"])].append(norm(r["keyword"]))

    for r in con.execute("select * from conversations"):
        conv_id = str(r["id"])
        events.append(
            {
                "event_id": event_id("GPT", "conversations", conv_id),
                "source": "GPT",
                "source_table": "conversations",
                "source_id": conv_id,
                "event_type": "conversation",
                "service": norm(r["model_name"]) or "ChatGPT",
                "event_time": norm(r["create_time"]),
                "month": f"{r['create_year']}-{int(r['create_month']):02d}" if str(r["create_year"]).isdigit() and str(r["create_month"]).isdigit() else "",
                "title": norm(r["title"]),
                "content": short(r["first_user_msg"]),
                "category": classify_topic(f"{r['title']} {r['first_user_msg']}"),
                "url": "",
                "domain": "",
                "file_name": "",
                "session_id": conv_id,
                "weight": float(r["total_msg_count"] or 1),
            }
        )
    for r in con.execute("select * from messages"):
        content = short(r["content"])
        events.append(
            {
                "event_id": event_id("GPT", "messages", r["id"]),
                "source": "GPT",
                "source_table": "messages",
                "source_id": str(r["id"]),
                "event_type": f"message:{norm(r['role'])}",
                "service": "ChatGPT",
                "event_time": norm(r["timestamp"]),
                "month": norm(r["timestamp"])[:7] if norm(r["timestamp"]) else "",
                "title": "",
                "content": content,
                "category": classify_topic(content),
                "url": "",
                "domain": "",
                "file_name": "",
                "session_id": str(r["conversation_id"]),
                "weight": 0.2,
            }
        )
    for r in con.execute("select * from artifacts"):
        events.append(
            {
                "event_id": event_id("GPT", "artifacts", r["id"]),
                "source": "GPT",
                "source_table": "artifacts",
                "source_id": str(r["id"]),
                "event_type": "artifact",
                "service": "ChatGPT",
                "event_time": "",
                "month": "",
                "title": norm(r["file_name"]),
                "content": short(f"{r['category']} {r['sub_category']} {r['context_snippet']}"),
                "category": norm(r["category"]),
                "url": "",
                "domain": "",
                "file_name": norm(r["file_name"]),
                "session_id": norm(r["conversation_id"]),
                "weight": 0.5,
            }
        )
    input_rows = []
    for table in ["conversations", "messages", "artifacts", "keywords"]:
        count = con.execute(f'select count(*) from "{table}"').fetchone()[0]
        input_rows.append({"source": "GPT", "database_path": SOURCE_DB_LABELS["GPT"], "table_name": table, "row_count": count})
    con.close()
    return events, input_rows, keywords_by_conv


def rows_from_agent() -> tuple[list[dict], list[dict]]:
    con = sqlite3.connect(AGENT_DB)
    con.row_factory = sqlite3.Row
    events = []
    for r in con.execute("select * from sessions"):
        events.append(
            {
                "event_id": event_id("Agent", "sessions", r["id"]),
                "source": "Agent",
                "source_table": "sessions",
                "source_id": str(r["id"]),
                "event_type": "agent_session",
                "service": norm(r["family"]),
                "event_time": norm(r["modified_at"]),
                "month": norm(r["modified_at"])[:7] if norm(r["modified_at"]) else "",
                "title": norm(r["session_id"]),
                "content": short(r["first_text_excerpt"]),
                "category": "Agent 会话",
                "url": "",
                "domain": "",
                "file_name": Path(norm(r["relative_path"])).name,
                "session_id": norm(r["session_id"]),
                "weight": float(r["message_count"] or 1),
            }
        )
    for r in con.execute("select * from skills"):
        events.append(
            {
                "event_id": event_id("Agent", "skills", r["id"]),
                "source": "Agent",
                "source_table": "skills",
                "source_id": str(r["id"]),
                "event_type": "skill",
                "service": norm(r["family"]),
                "event_time": "",
                "month": "",
                "title": norm(r["skill_name"]),
                "content": short(r["description"]),
                "category": "Agent Skill",
                "url": "",
                "domain": "",
                "file_name": Path(norm(r["copied_path"])).name,
                "session_id": "",
                "weight": 1.0,
            }
        )
    for r in con.execute("select * from memories"):
        events.append(
            {
                "event_id": event_id("Agent", "memories", r["id"]),
                "source": "Agent",
                "source_table": "memories",
                "source_id": str(r["id"]),
                "event_type": "memory",
                "service": norm(r["family"]),
                "event_time": norm(r["modified_at"]),
                "month": norm(r["modified_at"])[:7] if norm(r["modified_at"]) else "",
                "title": Path(norm(r["relative_path"])).name,
                "content": short(r["excerpt"]),
                "category": norm(r["memory_type"]) or "memory",
                "url": "",
                "domain": "",
                "file_name": Path(norm(r["relative_path"])).name,
                "session_id": "",
                "weight": 0.75,
            }
        )
    for r in con.execute("select * from source_files"):
        events.append(
            {
                "event_id": event_id("Agent", "source_files", r["id"]),
                "source": "Agent",
                "source_table": "source_files",
                "source_id": str(r["id"]),
                "event_type": "agent_file",
                "service": norm(r["family"]),
                "event_time": norm(r["modified_at"]),
                "month": norm(r["modified_at"])[:7] if norm(r["modified_at"]) else "",
                "title": Path(norm(r["relative_path"])).name,
                "content": short(f"{r['source']} {r['relative_path']} {r['extension']} {r['include_reason']}"),
                "category": "Agent 文件",
                "url": "",
                "domain": "",
                "file_name": Path(norm(r["relative_path"])).name,
                "session_id": "",
                "weight": 0.1,
            }
        )
    input_rows = []
    for table in ["source_files", "skills", "memories", "sessions", "session_messages", "database_tables"]:
        count = con.execute(f'select count(*) from "{table}"').fetchone()[0]
        input_rows.append({"source": "Agent", "database_path": SOURCE_DB_LABELS["Agent"], "table_name": table, "row_count": count})
    con.close()
    return events, input_rows


def build_entity_links(entities: dict[str, dict], event_entities: list[dict]) -> list[dict]:
    entity_sources: dict[str, set[str]] = defaultdict(set)
    entity_events: dict[str, set[str]] = defaultdict(set)
    for row in event_entities:
        entity_sources[row["entity_id"]].add(row["source"])
        entity_events[row["entity_id"]].add(row["event_id"])

    links = []
    for eid, sources in entity_sources.items():
        if len(sources) >= 2:
            links.append(
                {
                    "link_id": sha256_text(f"cross_module|{eid}"),
                    "from_entity_id": eid,
                    "to_entity_id": eid,
                    "relation": "appears_in_multiple_modules",
                    "strength": len(sources),
                    "evidence": ",".join(sorted(sources)),
                }
            )

    by_type_name: dict[tuple[str, str], list[str]] = defaultdict(list)
    for eid, entity in entities.items():
        by_type_name[(entity["entity_type"], entity["name"].lower())].append(eid)
    for (_, _), ids in by_type_name.items():
        if len(ids) > 1:
            for left in ids:
                for right in ids:
                    if left < right:
                        links.append(
                            {
                                "link_id": sha256_text(f"same_name|{left}|{right}"),
                                "from_entity_id": left,
                                "to_entity_id": right,
                                "relation": "same_normalized_name",
                                "strength": 1,
                                "evidence": entities[left]["name"],
                            }
                        )
    return links


def summarize(events: list[dict], entities: dict[str, dict], entity_links: list[dict]) -> tuple[list[dict], list[dict]]:
    by_source = Counter(e["source"] for e in events)
    by_source_weight = defaultdict(float)
    by_source_months: dict[str, set[str]] = defaultdict(set)
    for e in events:
        by_source_weight[e["source"]] += float(e["weight"])
        if e.get("month"):
            by_source_months[e["source"]].add(e["month"])

    summaries = []
    for source in sorted(by_source):
        summaries.append(
            {
                "source": source,
                "event_count": by_source[source],
                "weighted_activity": round(by_source_weight[source], 2),
                "active_months": len(by_source_months[source]),
            }
        )

    topic_counter = Counter()
    service_counter = Counter()
    for e in events:
        topic_counter[e.get("category") or classify_topic(f"{e.get('title','')} {e.get('content','')}")] += 1
        service_counter[e.get("service") or "(unknown)"] += 1

    cross_module_entities = []
    link_entity_ids = {l["from_entity_id"] for l in entity_links if l["relation"] == "appears_in_multiple_modules"}
    for eid in link_entity_ids:
        ent = entities[eid]
        cross_module_entities.append(f"{ent['entity_type']}:{ent['name']}")

    insights = [
        {
            "insight_type": "module_coverage",
            "title": "统合模块已接入三类核心数据源",
            "detail": f"统一事件 {len(events)} 条，实体 {len(entities)} 个，跨模块连接 {len(entity_links)} 条。",
            "evidence_count": len(events),
        },
        {
            "insight_type": "top_topics",
            "title": "最高频主题",
            "detail": json.dumps(topic_counter.most_common(10), ensure_ascii=False),
            "evidence_count": sum(topic_counter.values()),
        },
        {
            "insight_type": "top_services",
            "title": "最高频服务/工具",
            "detail": json.dumps(service_counter.most_common(12), ensure_ascii=False),
            "evidence_count": sum(service_counter.values()),
        },
        {
            "insight_type": "cross_module_entities",
            "title": "跨模块复现实体",
            "detail": json.dumps(cross_module_entities[:50], ensure_ascii=False),
            "evidence_count": len(cross_module_entities),
        },
    ]
    return summaries, insights


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def build_database(
    events: list[dict],
    entities: dict[str, dict],
    event_entities: list[dict],
    entity_links: list[dict],
    module_summaries: list[dict],
    insights: list[dict],
    input_rows: list[dict],
) -> None:
    if OUT_DB.exists():
        OUT_DB.unlink()
    con = sqlite3.connect(OUT_DB)
    try:
        con.executescript(
            """
            CREATE TABLE source_modules (
                source TEXT PRIMARY KEY,
                database_path TEXT NOT NULL,
                status TEXT NOT NULL,
                imported_at TEXT NOT NULL
            );
            CREATE TABLE input_tables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                database_path TEXT,
                table_name TEXT,
                row_count INTEGER
            );
            CREATE TABLE unified_events (
                event_id TEXT PRIMARY KEY,
                source TEXT,
                source_table TEXT,
                source_id TEXT,
                event_type TEXT,
                service TEXT,
                event_time TEXT,
                month TEXT,
                title TEXT,
                content TEXT,
                category TEXT,
                url TEXT,
                domain TEXT,
                file_name TEXT,
                session_id TEXT,
                weight REAL
            );
            CREATE TABLE entities (
                entity_id TEXT PRIMARY KEY,
                entity_type TEXT,
                name TEXT,
                source_count INTEGER,
                event_count INTEGER,
                first_source TEXT,
                evidence TEXT
            );
            CREATE TABLE event_entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT,
                entity_id TEXT,
                relation TEXT,
                source TEXT
            );
            CREATE TABLE entity_links (
                link_id TEXT PRIMARY KEY,
                from_entity_id TEXT,
                to_entity_id TEXT,
                relation TEXT,
                strength REAL,
                evidence TEXT
            );
            CREATE TABLE module_summaries (
                source TEXT PRIMARY KEY,
                event_count INTEGER,
                weighted_activity REAL,
                active_months INTEGER
            );
            CREATE TABLE cross_module_insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                insight_type TEXT,
                title TEXT,
                detail TEXT,
                evidence_count INTEGER
            );
            CREATE INDEX idx_events_source ON unified_events(source);
            CREATE INDEX idx_events_service ON unified_events(service);
            CREATE INDEX idx_events_month ON unified_events(month);
            CREATE INDEX idx_entities_type_name ON entities(entity_type, name);
            CREATE INDEX idx_event_entities_entity ON event_entities(entity_id);
            """
        )
        now = datetime.now().isoformat(timespec="seconds")
        con.executemany(
            "INSERT INTO source_modules (source, database_path, status, imported_at) VALUES (:source, :database_path, :status, :imported_at)",
            [{"source": s, "database_path": SOURCE_DB_LABELS[s], "status": "imported" if p.exists() else "missing", "imported_at": now} for s, p in SOURCE_DBS.items()],
        )

        def insert(table: str, rows: list[dict]) -> None:
            if not rows:
                return
            keys = list(rows[0].keys())
            con.executemany(
                f"INSERT INTO {table} ({','.join(keys)}) VALUES ({','.join(':'+k for k in keys)})",
                rows,
            )

        insert("input_tables", input_rows)
        insert("unified_events", events)
        insert("entities", list(entities.values()))
        insert("event_entities", event_entities)
        insert("entity_links", entity_links)
        insert("module_summaries", module_summaries)
        insert("cross_module_insights", insights)
        con.commit()
    finally:
        con.close()


def write_report(summary: dict, module_summaries: list[dict], insights: list[dict]) -> None:
    module_rows = "".join(
        f"<tr><td>{html.escape(r['source'])}</td><td>{r['event_count']}</td><td>{r['weighted_activity']}</td><td>{r['active_months']}</td></tr>"
        for r in module_summaries
    )
    insight_rows = "".join(
        f"<tr><td>{html.escape(r['title'])}</td><td>{html.escape(r['detail'])}</td><td>{r['evidence_count']}</td></tr>"
        for r in insights
    )
    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>个人系统统合分析报告</title>
  <style>
    body {{ font-family: "Microsoft YaHei", "Segoe UI", sans-serif; max-width: 1120px; margin: 32px auto; line-height: 1.65; color: #20242c; }}
    h1 {{ margin-bottom: 8px; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 20px 0; }}
    .kpi {{ border: 1px solid #d9dde5; padding: 14px; border-radius: 8px; background: #fff; }}
    .kpi b {{ display: block; font-size: 24px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 14px 0 28px; }}
    th, td {{ border: 1px solid #d9dde5; padding: 8px 10px; text-align: left; vertical-align: top; }}
    th {{ background: #f4f6f8; }}
  </style>
</head>
<body>
  <h1>个人系统统合分析报告</h1>
  <p>该报告由integration读取 Google、GPT、Agent 三个structured库生成。</p>
  <div class="grid">
    <div class="kpi"><b>{summary['event_count']}</b><span>统一事件</span></div>
    <div class="kpi"><b>{summary['entity_count']}</b><span>实体</span></div>
    <div class="kpi"><b>{summary['entity_link_count']}</b><span>实体连接</span></div>
    <div class="kpi"><b>{summary['input_table_count']}</b><span>输入表</span></div>
  </div>
  <h2>模块摘要</h2>
  <table><tr><th>模块</th><th>事件数</th><th>加权活动量</th><th>活跃月份数</th></tr>{module_rows}</table>
  <h2>综合洞察</h2>
  <table><tr><th>标题</th><th>内容</th><th>证据量</th></tr>{insight_rows}</table>
</body>
</html>
"""
    (ANALYSIS / "integrated_system_report.html").write_text(html_doc, encoding="utf-8")


def main() -> None:
    ensure_dirs()
    google_events, google_inputs = rows_from_google()
    gpt_events, gpt_inputs, keywords_by_conv = rows_from_gpt()
    agent_events, agent_inputs = rows_from_agent()
    events = google_events + gpt_events + agent_events
    input_rows = google_inputs + gpt_inputs + agent_inputs

    entities: dict[str, dict] = {}
    event_entities: list[dict] = []
    for event in events:
        connect_event_entities(event, entities, event_entities)
        if event["source"] == "GPT" and event["source_table"] == "conversations":
            connect_keywords(entities, event_entities, event, keywords_by_conv.get(event["source_id"], []))

    entity_links = build_entity_links(entities, event_entities)
    module_summaries, insights = summarize(events, entities, entity_links)

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "event_count": len(events),
        "entity_count": len(entities),
        "event_entity_count": len(event_entities),
        "entity_link_count": len(entity_links),
        "input_table_count": len(input_rows),
        "database": "integrated/sqlite/personal_system.sqlite",
    }

    build_database(events, entities, event_entities, entity_links, module_summaries, insights, input_rows)
    write_csv(INPUT_INDEX / "input_tables.csv", input_rows)
    write_csv(STRUCTURED / "unified_events.csv", events)
    write_csv(STRUCTURED / "entities.csv", list(entities.values()))
    write_csv(STRUCTURED / "event_entities.csv", event_entities)
    write_csv(STRUCTURED / "entity_links.csv", entity_links)
    write_csv(ANALYSIS / "module_summary.csv", module_summaries)
    write_csv(ANALYSIS / "cross_module_insights.csv", insights)
    (INTEGRATED / "classification_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(summary, module_summaries, insights)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
