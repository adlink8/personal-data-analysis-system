from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sqlite3
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from personal_knowledge.core.common import sha256_text

ROOT = Path(__file__).resolve().parents[3]
IMPORTS = ROOT / "imports"
BATCHES = IMPORTS / "batches"
INCOMING = IMPORTS / "incoming"
QUARANTINE = IMPORTS / "duplicate_audit" / "quarantine"
GOOGLE_DB = ROOT / "Google" / "structured" / "db" / "google_data.sqlite"
GPT_DB = ROOT / "GPT" / "structured" / "db" / "chatgpt_data.db"

SUPPORTED_SOURCES = {"google", "gpt"}
GPT_CONVERSATIONS_RE = re.compile(r"^conversations(?:-\d+)?\.json$", re.IGNORECASE)
WEEKDAYS_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


@dataclass
class ParsedEvent:
    source: str
    service: str
    event_time: str | None
    title: str | None
    url: str | None
    content: str | None
    raw: dict[str, Any]
    source_file_id: str
    batch_id: str

    @property
    def record_hash(self) -> str:
        payload = {
            "source": self.source,
            "service": self.service,
            "event_time": self.event_time or "",
            "title": normalize_text(self.title),
            "url": normalize_text(self.url),
            "content": normalize_text(self.content),
        }
        return sha256_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def now_id() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def is_gpt_conversations_file(path: Path) -> bool:
    return bool(GPT_CONVERSATIONS_RE.match(path.name))


def timestamp_to_datetime(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value)
        except (OverflowError, OSError, ValueError):
            return None
    return None


def timestamp_to_text(value: Any) -> str:
    dt = timestamp_to_datetime(value)
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""


def timestamp_to_iso(value: Any) -> str | None:
    dt = timestamp_to_datetime(value)
    return dt.isoformat() if dt else None


def gpt_model_name(slug: str) -> str:
    low = (slug or "").lower()
    if not low or low == "unknown":
        return "Unknown"
    if "gpt-5" in low:
        return "GPT-5"
    if "gpt-4o" in low:
        return "GPT-4o"
    if "gpt-4" in low:
        return "GPT-4"
    if "gpt-3.5" in low or "text-davinci" in low:
        return "GPT-3.5"
    if "o4" in low:
        return "o4"
    if "o3" in low:
        return "o3"
    return slug


def gpt_content_text(content_obj: Any) -> str:
    if isinstance(content_obj, str):
        return content_obj
    if not isinstance(content_obj, dict):
        return ""
    parts = content_obj.get("parts")
    if isinstance(parts, list):
        texts: list[str] = []
        for part in parts:
            if isinstance(part, str):
                texts.append(part)
            elif isinstance(part, dict) and isinstance(part.get("text"), str):
                texts.append(part["text"])
            elif part not in (None, ""):
                texts.append(json.dumps(part, ensure_ascii=False, sort_keys=True))
        return "\n".join(texts)
    text = content_obj.get("text")
    if isinstance(text, str):
        return text
    return ""


def message_fingerprint(conversation_id: str, role: str, timestamp: str, content: str) -> str:
    content_hash = sha256_text(content or "")
    return sha256_text(f"{conversation_id}|{role}|{timestamp}|{content_hash}")


def ensure_layout() -> None:
    for path in [
        INCOMING / "google",
        INCOMING / "gpt",
        BATCHES,
        QUARANTINE,
        ROOT / "Google" / "analysis" / "reports_html",
        ROOT / "GPT" / "analysis" / "reports_html",
    ]:
        path.mkdir(parents=True, exist_ok=True)


def target_db(source: str) -> Path:
    if source == "google":
        return GOOGLE_DB
    if source == "gpt":
        return GPT_DB
    raise ValueError(f"Unsupported source: {source}")


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS import_batches (
                batch_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                raw_path TEXT NOT NULL,
                status TEXT NOT NULL,
                file_count INTEGER NOT NULL DEFAULT 0,
                inserted_records INTEGER NOT NULL DEFAULT 0,
                duplicate_records INTEGER NOT NULL DEFAULT 0,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS source_files (
                file_id TEXT PRIMARY KEY,
                batch_id TEXT NOT NULL,
                source TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                status TEXT NOT NULL,
                duplicate_of TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS normalized_events (
                event_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                service TEXT NOT NULL,
                event_time TEXT,
                title TEXT,
                url TEXT,
                domain TEXT,
                content TEXT,
                raw_json TEXT,
                record_hash TEXT NOT NULL UNIQUE,
                batch_id TEXT NOT NULL,
                source_file_id TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_import_batches_source ON import_batches(source);
            CREATE INDEX IF NOT EXISTS idx_source_files_sha256 ON source_files(sha256);
            CREATE INDEX IF NOT EXISTS idx_events_source_service ON normalized_events(source, service);
            CREATE INDEX IF NOT EXISTS idx_events_time ON normalized_events(event_time);
            CREATE INDEX IF NOT EXISTS idx_events_domain ON normalized_events(domain);
            """
        )


def table_exists(con: sqlite3.Connection, table: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone() is not None


def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    if not table_exists(con, table):
        return set()
    return {row[1] for row in con.execute(f'PRAGMA table_info("{table}")')}


def ensure_column(con: sqlite3.Connection, table: str, column_name: str, column_sql: str) -> None:
    if column_name not in table_columns(con, table):
        con.execute(f'ALTER TABLE "{table}" ADD COLUMN {column_sql}')


def ensure_gpt_core_schema(con: sqlite3.Connection) -> None:
    """Ensure the GPT tables consumed by integration exist and support idempotent import."""
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT,
            create_time TEXT,
            create_date TEXT,
            create_year INTEGER,
            create_month INTEGER,
            create_hour INTEGER,
            create_weekday TEXT,
            model_slug TEXT,
            model_name TEXT,
            is_archived INTEGER DEFAULT 0,
            user_msg_count INTEGER DEFAULT 0,
            assistant_msg_count INTEGER DEFAULT 0,
            total_msg_count INTEGER DEFAULT 0,
            total_chars INTEGER DEFAULT 0,
            has_code INTEGER DEFAULT 0,
            has_attachments INTEGER DEFAULT 0,
            first_user_msg TEXT
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            turn_number INTEGER,
            role TEXT NOT NULL,
            content TEXT,
            content_type TEXT,
            timestamp TEXT,
            char_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS artifacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            file_name TEXT,
            category TEXT,
            sub_category TEXT,
            file_ext TEXT,
            size_bytes INTEGER,
            size_kb REAL,
            conversation_id TEXT,
            conversation_title TEXT,
            message_id TEXT,
            role_in_context TEXT,
            context_snippet TEXT,
            asset_pointer TEXT,
            image_width INTEGER DEFAULT 0,
            image_height INTEGER DEFAULT 0,
            project_hash TEXT,
            is_generated INTEGER DEFAULT 0,
            is_user_upload INTEGER DEFAULT 0,
            purpose TEXT DEFAULT '',
            match_method TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id TEXT NOT NULL,
            keyword TEXT NOT NULL,
            weight REAL
        );
        """
    )
    ensure_column(con, "messages", "source_message_id", "source_message_id TEXT")
    ensure_column(con, "messages", "message_fingerprint", "message_fingerprint TEXT")
    con.execute("CREATE INDEX IF NOT EXISTS idx_messages_fingerprint ON messages(message_fingerprint)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_keywords_conversation ON keywords(conversation_id)")


def load_message_fingerprints(con: sqlite3.Connection, persist: bool) -> set[str]:
    if not table_exists(con, "messages"):
        return set()
    cols = table_columns(con, "messages")
    has_fingerprint = "message_fingerprint" in cols
    select_cols = "id, conversation_id, role, timestamp, content"
    if has_fingerprint:
        select_cols += ", message_fingerprint"
    existing: set[str] = set()
    updates: list[tuple[str, int]] = []
    for row in con.execute(f"SELECT {select_cols} FROM messages"):
        row_id, conversation_id, role, timestamp, content = row[:5]
        fingerprint = row[5] if has_fingerprint else None
        if not fingerprint:
            fingerprint = message_fingerprint(
                str(conversation_id or ""),
                str(role or ""),
                str(timestamp or ""),
                str(content or ""),
            )
            if persist and has_fingerprint:
                updates.append((fingerprint, int(row_id)))
        existing.add(str(fingerprint))
    if updates:
        con.executemany("UPDATE messages SET message_fingerprint=? WHERE id=?", updates)
    return existing


def init_all() -> None:
    ensure_layout()
    for source in SUPPORTED_SOURCES:
        init_db(target_db(source))


def existing_hashes() -> dict[str, str]:
    """Return one canonical path per hash outside imports and duplicate audit."""
    ignored = [IMPORTS.resolve(), (IMPORTS / "duplicate_audit").resolve()]
    hashes: dict[str, str] = {}
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if any(str(resolved).startswith(str(prefix)) for prefix in ignored):
            continue
        digest = sha256_file(path)
        hashes.setdefault(digest, str(path.relative_to(ROOT)))
    return hashes


def copy_input_to_batch(input_path: Path, batch_raw: Path) -> list[Path]:
    if not input_path.exists():
        return []
    copied: list[Path] = []
    if input_path.is_file():
        target = batch_raw / input_path.name
        shutil.copy2(input_path, target)
        copied.append(target)
        return copied
    for src in input_path.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(input_path)
        target = batch_raw / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        copied.append(target)
    return copied


def extract_archives(raw_files: Iterable[Path], extracted_dir: Path) -> list[Path]:
    extracted: list[Path] = []
    for path in raw_files:
        if path.suffix.lower() != ".zip":
            continue
        out_dir = extracted_dir / path.stem
        out_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path) as zf:
            zf.extractall(out_dir)
        extracted.extend([p for p in out_dir.rglob("*") if p.is_file()])
    return extracted


def file_id(source: str, batch_id: str, rel: str, digest: str) -> str:
    return sha256_text(f"{source}|{batch_id}|{rel}|{digest}")


def quarantine_file(path: Path, batch_dir: Path, digest: str) -> Path:
    rel = path.relative_to(batch_dir)
    target = QUARANTINE / "imports" / batch_dir.name / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target = target.with_name(f"{target.stem}.{digest[:12]}{target.suffix}")
    shutil.move(str(path), str(target))
    return target


def register_files(
    con: sqlite3.Connection,
    source: str,
    batch_id: str,
    batch_dir: Path,
    files: list[Path],
    known_hashes: dict[str, str],
    dry_run: bool,
) -> tuple[list[dict[str, Any]], list[Path]]:
    rows: list[dict[str, Any]] = []
    importable: list[Path] = []
    batch_hashes: dict[str, str] = {}

    for path in files:
        if not path.exists():
            continue
        digest = sha256_file(path)
        rel = str(path.relative_to(batch_dir))
        duplicate_of = known_hashes.get(digest) or batch_hashes.get(digest)
        status = "duplicate" if duplicate_of else "new"
        moved_to = None
        if duplicate_of:
            moved_to = str((QUARANTINE / "imports" / batch_id / rel).relative_to(ROOT))
            if not dry_run:
                moved_to = str(quarantine_file(path, batch_dir, digest).relative_to(ROOT))
        else:
            batch_hashes[digest] = rel
            importable.append(path)

        row = {
            "file_id": file_id(source, batch_id, rel, digest),
            "batch_id": batch_id,
            "source": source,
            "relative_path": rel,
            "sha256": digest,
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "status": status,
            "duplicate_of": duplicate_of,
            "moved_to": moved_to,
        }
        rows.append(row)

    if not dry_run:
        con.executemany(
            """
            INSERT OR REPLACE INTO source_files (
                file_id, batch_id, source, relative_path, sha256, size_bytes, status, duplicate_of
            ) VALUES (
                :file_id, :batch_id, :source, :relative_path, :sha256, :size_bytes, :status, :duplicate_of
            )
            """,
            rows,
        )
    return rows, importable


def read_json(path: Path) -> Any:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return json.loads(text)


def guess_google_service(path: Path, item: dict[str, Any]) -> str:
    text = " ".join([str(path), str(item.get("header", "")), str(item.get("title", ""))]).lower()
    if "youtube" in text:
        return "youtube"
    if "chrome" in text:
        return "chrome"
    if "gemini" in text or "bard" in text:
        return "gemini"
    if "maps" in text or "地图" in text:
        return "maps"
    if "search" in text or "搜索" in text:
        return "search"
    return "google"


def extract_subtitle(item: dict[str, Any]) -> str | None:
    subtitles = item.get("subtitles")
    if isinstance(subtitles, list):
        parts = []
        for sub in subtitles:
            if isinstance(sub, dict):
                parts.append(str(sub.get("name") or sub.get("title") or ""))
        return normalize_text(" ".join(parts)) or None
    return None


def parse_google_json(path: Path, source_file_id: str, batch_id: str) -> list[ParsedEvent]:
    data = read_json(path)
    if isinstance(data, dict) and isinstance(data.get("Browser History"), list):
        data = data["Browser History"]
    elif isinstance(data, dict) and isinstance(data.get("locations"), list):
        data = data["locations"]
    elif isinstance(data, dict):
        data = data.get("items") or data.get("events") or [data]
    if not isinstance(data, list):
        return []

    events: list[ParsedEvent] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        service = guess_google_service(path, item)
        title = item.get("title") or item.get("name") or item.get("page_title")
        url = item.get("titleUrl") or item.get("url") or item.get("page_url")
        event_time = item.get("time") or item.get("timestamp") or item.get("last_visit_time")
        content = item.get("description") or item.get("query") or extract_subtitle(item)
        events.append(
            ParsedEvent(
                source="google",
                service=service,
                event_time=normalize_text(event_time) or None,
                title=normalize_text(title) or None,
                url=normalize_text(url) or None,
                content=normalize_text(content) or None,
                raw=item,
                source_file_id=source_file_id,
                batch_id=batch_id,
            )
        )
    return events


def parse_csv_events(path: Path, source: str, source_file_id: str, batch_id: str) -> list[ParsedEvent]:
    events: list[ParsedEvent] = []
    with path.open("r", encoding="utf-8-sig", newline="", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            service = normalize_text(row.get("service") or row.get("Service") or source)
            title = row.get("title") or row.get("Title") or row.get("title_or_query") or row.get("query")
            url = row.get("url") or row.get("URL") or row.get("titleUrl")
            event_time = row.get("event_at") or row.get("datetime") or row.get("time") or row.get("create_date")
            content = row.get("content") or row.get("raw_excerpt") or row.get("first_user_msg")
            events.append(
                ParsedEvent(
                    source=source,
                    service=service.lower() or source,
                    event_time=normalize_text(event_time) or None,
                    title=normalize_text(title) or None,
                    url=normalize_text(url) or None,
                    content=normalize_text(content) or None,
                    raw=dict(row),
                    source_file_id=source_file_id,
                    batch_id=batch_id,
                )
            )
    return events


def iter_gpt_messages(node: dict[str, Any]) -> Iterable[dict[str, Any]]:
    message = node.get("message")
    if isinstance(message, dict):
        yield message


def parse_gpt_conversations(path: Path, source_file_id: str, batch_id: str) -> list[ParsedEvent]:
    data = read_json(path)
    if not isinstance(data, list):
        return []
    events: list[ParsedEvent] = []
    for conv in data:
        if not isinstance(conv, dict):
            continue
        conv_id = normalize_text(conv.get("id"))
        conv_title = normalize_text(conv.get("title")) or None
        mapping = conv.get("mapping") or {}
        if not isinstance(mapping, dict):
            continue
        for node_id, node in mapping.items():
            if not isinstance(node, dict):
                continue
            for msg in iter_gpt_messages(node):
                author = msg.get("author") or {}
                role = author.get("role") if isinstance(author, dict) else None
                content = gpt_content_text(msg.get("content") or {})
                create_time = msg.get("create_time") or conv.get("create_time")
                event_time = timestamp_to_iso(create_time)
                raw = {"conversation_id": conv_id, "node_id": node_id, "role": role, "title": conv_title}
                events.append(
                    ParsedEvent(
                        source="gpt",
                        service=f"chatgpt:{role or 'unknown'}",
                        event_time=event_time,
                        title=conv_title,
                        url=None,
                        content=normalize_text(content) or None,
                        raw=raw,
                        source_file_id=source_file_id,
                        batch_id=batch_id,
                    )
                )
    return events


def extract_gpt_keywords(text: str, limit: int = 8) -> list[tuple[str, float]]:
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_+.-]{2,}|[\u4e00-\u9fff]{2,}", text.lower())
    stop = {
        "the", "and", "for", "with", "this", "that", "from", "what", "how",
        "一个", "这个", "那个", "什么", "如何", "怎么", "需要", "可以", "然后", "查看",
    }
    counts = Counter(t for t in tokens if t not in stop and len(t) <= 32)
    total = sum(counts.values()) or 1
    return [(token, round(count / total, 4)) for token, count in counts.most_common(limit)]


def parse_gpt_core_file(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    data = read_json(path)
    if not isinstance(data, list):
        return [], [], []

    conversations: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []
    keywords: list[dict[str, Any]] = []

    for conv in data:
        if not isinstance(conv, dict):
            continue
        conversation_id = normalize_text(conv.get("id") or conv.get("conversation_id"))
        if not conversation_id:
            continue
        title = normalize_text(conv.get("title"))
        create_dt = timestamp_to_datetime(conv.get("create_time"))
        create_time = create_dt.strftime("%Y-%m-%d %H:%M:%S") if create_dt else ""
        model_slug = normalize_text(conv.get("default_model_slug") or conv.get("model_slug") or "unknown")
        mapping = conv.get("mapping") or {}
        raw_messages: list[dict[str, Any]] = []
        if isinstance(mapping, dict):
            for order, (node_id, node) in enumerate(mapping.items(), start=1):
                if not isinstance(node, dict):
                    continue
                msg = node.get("message")
                if not isinstance(msg, dict):
                    continue
                author = msg.get("author") or {}
                role = normalize_text(author.get("role") if isinstance(author, dict) else "")
                content_obj = msg.get("content") or {}
                content = gpt_content_text(content_obj)
                if not role or not content:
                    continue
                timestamp = timestamp_to_text(msg.get("create_time") or conv.get("create_time"))
                content_type = "text"
                if isinstance(content_obj, dict):
                    content_type = normalize_text(content_obj.get("content_type") or content_obj.get("type") or "text")
                raw_messages.append(
                    {
                        "conversation_id": conversation_id,
                        "source_message_id": normalize_text(msg.get("id") or node_id),
                        "role": role,
                        "content": content,
                        "content_type": content_type,
                        "timestamp": timestamp,
                        "char_count": len(content),
                        "_order": order,
                    }
                )

        raw_messages.sort(key=lambda row: (row["timestamp"] or create_time, row["_order"]))
        first_user_msg = ""
        has_code = 0
        has_attachments = 0
        role_counts = Counter()
        total_chars = 0
        for turn_number, row in enumerate(raw_messages, start=1):
            role_counts[row["role"]] += 1
            total_chars += int(row["char_count"] or 0)
            if row["role"] == "user" and not first_user_msg:
                first_user_msg = row["content"].strip()
            if "```" in row["content"] or "\ndef " in row["content"] or "\nclass " in row["content"]:
                has_code = 1
            if "file_" in row["content"] or "asset_pointer" in row["content"]:
                has_attachments = 1
            fingerprint = message_fingerprint(
                conversation_id,
                row["role"],
                row["timestamp"],
                row["content"],
            )
            messages.append(
                {
                    "conversation_id": conversation_id,
                    "turn_number": turn_number,
                    "role": row["role"],
                    "content": row["content"],
                    "content_type": row["content_type"],
                    "timestamp": row["timestamp"],
                    "char_count": row["char_count"],
                    "source_message_id": row["source_message_id"],
                    "message_fingerprint": fingerprint,
                }
            )

        conversations.append(
            {
                "id": conversation_id,
                "title": title,
                "create_time": create_time,
                "create_date": create_dt.strftime("%Y-%m-%d") if create_dt else "",
                "create_year": create_dt.year if create_dt else None,
                "create_month": create_dt.month if create_dt else None,
                "create_hour": create_dt.hour if create_dt else None,
                "create_weekday": WEEKDAYS_ZH[create_dt.weekday()] if create_dt else "",
                "model_slug": model_slug,
                "model_name": gpt_model_name(model_slug),
                "is_archived": 1 if conv.get("is_archived") else 0,
                "user_msg_count": role_counts.get("user", 0),
                "assistant_msg_count": role_counts.get("assistant", 0),
                "total_msg_count": len(raw_messages),
                "total_chars": total_chars,
                "has_code": has_code,
                "has_attachments": has_attachments,
                "first_user_msg": first_user_msg,
            }
        )
        for keyword, weight in extract_gpt_keywords(f"{title} {first_user_msg}"):
            keywords.append({"conversation_id": conversation_id, "keyword": keyword, "weight": weight})

    return conversations, messages, keywords


def upsert_gpt_core(con: sqlite3.Connection, files: list[Path], dry_run: bool) -> dict[str, Any]:
    conversation_files = [path for path in files if is_gpt_conversations_file(path)]
    stats = {
        "gpt_conversation_files": len(conversation_files),
        "gpt_conversations_seen": 0,
        "gpt_conversations_inserted": 0,
        "gpt_conversations_updated": 0,
        "gpt_messages_seen": 0,
        "gpt_messages_inserted": 0,
        "gpt_messages_duplicate": 0,
        "gpt_keywords_seen": 0,
        "gpt_keywords_inserted": 0,
        "gpt_parse_errors": 0,
    }
    if not conversation_files:
        return stats

    if not dry_run:
        ensure_gpt_core_schema(con)
    existing_conversations = (
        {str(row[0]) for row in con.execute("SELECT id FROM conversations")}
        if table_exists(con, "conversations")
        else set()
    )
    existing_fingerprints = load_message_fingerprints(con, persist=not dry_run)
    existing_keywords = (
        {(str(row[0]), str(row[1])) for row in con.execute("SELECT conversation_id, keyword FROM keywords")}
        if table_exists(con, "keywords")
        else set()
    )

    for path in conversation_files:
        try:
            conversations, messages, keywords = parse_gpt_core_file(path)
        except Exception:
            stats["gpt_parse_errors"] += 1
            continue

        stats["gpt_conversations_seen"] += len(conversations)
        stats["gpt_messages_seen"] += len(messages)
        stats["gpt_keywords_seen"] += len(keywords)

        for row in conversations:
            if row["id"] in existing_conversations:
                stats["gpt_conversations_updated"] += 1
                if not dry_run:
                    con.execute(
                        """
                        UPDATE conversations
                        SET title=:title, create_time=:create_time, create_date=:create_date,
                            create_year=:create_year, create_month=:create_month,
                            create_hour=:create_hour, create_weekday=:create_weekday,
                            model_slug=:model_slug, model_name=:model_name,
                            is_archived=:is_archived, user_msg_count=:user_msg_count,
                            assistant_msg_count=:assistant_msg_count,
                            total_msg_count=:total_msg_count, total_chars=:total_chars,
                            has_code=:has_code, has_attachments=:has_attachments,
                            first_user_msg=:first_user_msg
                        WHERE id=:id
                        """,
                        row,
                    )
            else:
                stats["gpt_conversations_inserted"] += 1
                existing_conversations.add(row["id"])
                if not dry_run:
                    con.execute(
                        """
                        INSERT INTO conversations (
                            id, title, create_time, create_date, create_year, create_month,
                            create_hour, create_weekday, model_slug, model_name, is_archived,
                            user_msg_count, assistant_msg_count, total_msg_count, total_chars,
                            has_code, has_attachments, first_user_msg
                        ) VALUES (
                            :id, :title, :create_time, :create_date, :create_year, :create_month,
                            :create_hour, :create_weekday, :model_slug, :model_name, :is_archived,
                            :user_msg_count, :assistant_msg_count, :total_msg_count, :total_chars,
                            :has_code, :has_attachments, :first_user_msg
                        )
                        """,
                        row,
                    )

        for row in messages:
            fingerprint = row["message_fingerprint"]
            if fingerprint in existing_fingerprints:
                stats["gpt_messages_duplicate"] += 1
                continue
            stats["gpt_messages_inserted"] += 1
            existing_fingerprints.add(fingerprint)
            if not dry_run:
                con.execute(
                    """
                    INSERT INTO messages (
                        conversation_id, turn_number, role, content, content_type, timestamp,
                        char_count, source_message_id, message_fingerprint
                    ) VALUES (
                        :conversation_id, :turn_number, :role, :content, :content_type, :timestamp,
                        :char_count, :source_message_id, :message_fingerprint
                    )
                    """,
                    row,
                )

        for row in keywords:
            key = (row["conversation_id"], row["keyword"])
            if key in existing_keywords:
                continue
            existing_keywords.add(key)
            stats["gpt_keywords_inserted"] += 1
            if not dry_run:
                con.execute(
                    "INSERT INTO keywords (conversation_id, keyword, weight) VALUES (:conversation_id, :keyword, :weight)",
                    row,
                )

    return stats


def parse_events(source: str, files: list[Path], batch_id: str, batch_dir: Path) -> list[ParsedEvent]:
    events: list[ParsedEvent] = []
    for path in files:
        rel = str(path.relative_to(batch_dir))
        digest = sha256_file(path)
        sid = file_id(source, batch_id, rel, digest)
        suffix = path.suffix.lower()
        try:
            if source == "gpt" and is_gpt_conversations_file(path):
                events.extend(parse_gpt_conversations(path, sid, batch_id))
            elif suffix == ".json":
                if source == "google":
                    events.extend(parse_google_json(path, sid, batch_id))
            elif suffix == ".csv":
                events.extend(parse_csv_events(path, source, sid, batch_id))
        except Exception as exc:
            events.append(
                ParsedEvent(
                    source=source,
                    service="parse_error",
                    event_time=None,
                    title=f"Parse failed: {path.name}",
                    url=None,
                    content=str(exc),
                    raw={"path": rel, "error": str(exc)},
                    source_file_id=sid,
                    batch_id=batch_id,
                )
            )
    return events


def domain_from_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    return parsed.netloc or None


def insert_events(con: sqlite3.Connection, events: list[ParsedEvent], dry_run: bool) -> tuple[int, int]:
    inserted = 0
    duplicates = 0
    for event in events:
        row = {
            "event_id": sha256_text(f"{event.batch_id}|{event.source_file_id}|{event.record_hash}"),
            "source": event.source,
            "service": event.service,
            "event_time": event.event_time,
            "title": event.title,
            "url": event.url,
            "domain": domain_from_url(event.url),
            "content": event.content,
            "raw_json": json.dumps(event.raw, ensure_ascii=False, sort_keys=True),
            "record_hash": event.record_hash,
            "batch_id": event.batch_id,
            "source_file_id": event.source_file_id,
        }
        if dry_run:
            inserted += 1
            continue
        cur = con.execute(
            """
            INSERT OR IGNORE INTO normalized_events (
                event_id, source, service, event_time, title, url, domain, content,
                raw_json, record_hash, batch_id, source_file_id
            ) VALUES (
                :event_id, :source, :service, :event_time, :title, :url, :domain, :content,
                :raw_json, :record_hash, :batch_id, :source_file_id
            )
            """,
            row,
        )
        if cur.rowcount == 1:
            inserted += 1
        else:
            duplicates += 1
    return inserted, duplicates


def write_report(source: str, batch_id: str, summary: dict[str, Any]) -> Path:
    out = ROOT / ("Google" if source == "google" else "GPT") / "analysis" / "reports_html"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"import_summary_{batch_id}.html"
    rows = "\n".join(
        f"<tr><th>{key}</th><td>{value}</td></tr>"
        for key, value in summary.items()
    )
    path.write_text(
        f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>{source} 导入摘要 {batch_id}</title>
<style>body{{font-family:Segoe UI,Microsoft YaHei,sans-serif;max-width:960px;margin:32px auto;line-height:1.6}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ddd;padding:8px;text-align:left}}th{{width:260px;background:#f6f6f6}}</style></head>
<body><h1>{source} 导入摘要</h1><table>{rows}</table></body></html>
""",
        encoding="utf-8",
    )
    return path


def run_source(source: str, input_path: Path, dry_run: bool = False) -> dict[str, Any]:
    ensure_layout()
    init_db(target_db(source))
    batch_id = f"{now_id()}_{source}"
    batch_dir = BATCHES / batch_id
    raw_dir = batch_dir / "raw"
    extracted_dir = batch_dir / "extracted"
    raw_dir.mkdir(parents=True, exist_ok=True)
    extracted_dir.mkdir(parents=True, exist_ok=True)

    known_hashes = existing_hashes()
    raw_files = copy_input_to_batch(input_path, raw_dir)
    extracted_files = extract_archives(raw_files, extracted_dir)
    candidate_files = raw_files + extracted_files

    db_path = target_db(source)
    with sqlite3.connect(db_path) as con:
        if not dry_run:
            con.execute(
                """
                INSERT OR REPLACE INTO import_batches (
                    batch_id, source, imported_at, raw_path, status, file_count, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (batch_id, source, datetime.now().isoformat(timespec="seconds"), str(input_path), "running", len(candidate_files), None),
            )
        file_rows, importable = register_files(con, source, batch_id, batch_dir, candidate_files, known_hashes, dry_run)
        events = parse_events(source, importable, batch_id, batch_dir)
        inserted, duplicate_records = insert_events(con, events, dry_run)
        core_stats = upsert_gpt_core(con, importable, dry_run) if source == "gpt" else {}
        batch_inserted_records = core_stats.get("gpt_messages_inserted", inserted)
        batch_duplicate_records = core_stats.get("gpt_messages_duplicate", duplicate_records)
        if not dry_run:
            con.execute(
                """
                UPDATE import_batches
                SET status = ?, file_count = ?, inserted_records = ?, duplicate_records = ?
                WHERE batch_id = ?
                """,
                ("imported", len(candidate_files), batch_inserted_records, batch_duplicate_records, batch_id),
            )
            con.commit()

    summary = {
        "batch_id": batch_id,
        "source": source,
        "input_path": str(input_path),
        "db_path": str(db_path),
        "dry_run": dry_run,
        "files_seen": len(candidate_files),
        "duplicate_files": sum(1 for row in file_rows if row["status"] == "duplicate"),
        "importable_files": len(importable),
        "parsed_events": len(events),
        "inserted_records": batch_inserted_records,
        "duplicate_records": batch_duplicate_records,
        "normalized_events_inserted": inserted,
        "normalized_events_duplicate": duplicate_records,
        **core_stats,
    }
    report = write_report(source, batch_id, summary)
    summary["report_path"] = str(report)

    if not dry_run:
        (batch_dir / "manifest.json").write_text(json.dumps(file_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        (batch_dir / "import_log.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Google/GPT 增量导入流水线")
    parser.add_argument("--source", choices=["google", "gpt", "all"], help="导入来源")
    parser.add_argument("--input", type=Path, help="新导出数据入口路径")
    parser.add_argument("--init", action="store_true", help="只初始化目录和数据库控制表")
    parser.add_argument("--dry-run", action="store_true", help="演练导入，不移动重复文件、不写入事件")
    args = parser.parse_args()

    if args.init:
        init_all()
        print(json.dumps({"status": "initialized", "root": str(ROOT)}, ensure_ascii=False))
        return

    if not args.source:
        parser.error("--source is required unless --init is used")

    sources = ["google", "gpt"] if args.source == "all" else [args.source]
    results = []
    for source in sources:
        input_path = args.input or (INCOMING / source)
        results.append(run_source(source, input_path, args.dry_run))
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
