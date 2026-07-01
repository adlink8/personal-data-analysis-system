from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import sqlite3
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[2]
IMPORTS = ROOT / "imports"
BATCHES = IMPORTS / "batches"
INCOMING = IMPORTS / "incoming"
QUARANTINE = IMPORTS / "duplicate_audit" / "quarantine"
GOOGLE_DB = ROOT / "Google" / "structured" / "db" / "google_data.sqlite"
GPT_DB = ROOT / "GPT" / "structured" / "db" / "chatgpt_data.db"

SUPPORTED_SOURCES = {"google", "gpt"}


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


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


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
                content_obj = msg.get("content") or {}
                parts = content_obj.get("parts") if isinstance(content_obj, dict) else None
                if isinstance(parts, list):
                    content = "\n".join(str(p) for p in parts if isinstance(p, str))
                else:
                    content = None
                create_time = msg.get("create_time") or conv.get("create_time")
                event_time = datetime.fromtimestamp(create_time).isoformat() if isinstance(create_time, (int, float)) else None
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


def parse_events(source: str, files: list[Path], batch_id: str, batch_dir: Path) -> list[ParsedEvent]:
    events: list[ParsedEvent] = []
    for path in files:
        rel = str(path.relative_to(batch_dir))
        digest = sha256_file(path)
        sid = file_id(source, batch_id, rel, digest)
        suffix = path.suffix.lower()
        try:
            if source == "gpt" and path.name.lower() == "conversations.json":
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
        if not dry_run:
            con.execute(
                """
                UPDATE import_batches
                SET status = ?, file_count = ?, inserted_records = ?, duplicate_records = ?
                WHERE batch_id = ?
                """,
                ("imported", len(candidate_files), inserted, duplicate_records, batch_id),
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
        "inserted_records": inserted,
        "duplicate_records": duplicate_records,
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
