from __future__ import annotations

import csv
import sqlite3
from pathlib import Path


GOOGLE_DIR = Path(r"C:\Users\li\Desktop\数据分析\Google")
SOURCE_DIR = GOOGLE_DIR / "分析数据" / "旧分析输出" / "google_content_analysis"
DB_PATH = GOOGLE_DIR / "结构化数据" / "SQLite数据库" / "google_data.sqlite"
SCHEMA_PATH = GOOGLE_DIR / "结构化数据" / "SQLite数据库" / "google_data_schema.sql"


SCHEMA = """
PRAGMA foreign_keys = ON;

DROP VIEW IF EXISTS v_monthly_activity;
DROP VIEW IF EXISTS v_category_summary;
DROP VIEW IF EXISTS v_service_summary;
DROP VIEW IF EXISTS v_youtube_channel_summary;
DROP VIEW IF EXISTS v_domain_summary;
DROP TABLE IF EXISTS activity_fts;
DROP TABLE IF EXISTS map_details;
DROP TABLE IF EXISTS gemini_attachments;
DROP TABLE IF EXISTS activities;

CREATE TABLE activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service TEXT NOT NULL,
    event_at TEXT,
    month TEXT,
    action TEXT,
    category TEXT,
    title_or_query TEXT,
    channel_or_source TEXT,
    domain TEXT,
    url TEXT,
    raw_excerpt TEXT,
    source_dataset TEXT NOT NULL DEFAULT 'full_activity_details.csv',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE gemini_attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_name TEXT NOT NULL,
    extension TEXT,
    size_kb REAL,
    category TEXT,
    source_dataset TEXT NOT NULL DEFAULT 'gemini_attachments.csv',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE map_details (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file TEXT NOT NULL,
    record_type TEXT,
    name_or_value TEXT,
    category TEXT,
    source_dataset TEXT NOT NULL DEFAULT 'maps_extracted_details.csv',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE activity_fts USING fts5(
    title_or_query,
    channel_or_source,
    domain,
    raw_excerpt,
    category,
    content='activities',
    content_rowid='id'
);

CREATE TRIGGER activities_ai AFTER INSERT ON activities BEGIN
    INSERT INTO activity_fts(rowid, title_or_query, channel_or_source, domain, raw_excerpt, category)
    VALUES (new.id, new.title_or_query, new.channel_or_source, new.domain, new.raw_excerpt, new.category);
END;

CREATE TRIGGER activities_ad AFTER DELETE ON activities BEGIN
    INSERT INTO activity_fts(activity_fts, rowid, title_or_query, channel_or_source, domain, raw_excerpt, category)
    VALUES ('delete', old.id, old.title_or_query, old.channel_or_source, old.domain, old.raw_excerpt, old.category);
END;

CREATE TRIGGER activities_au AFTER UPDATE ON activities BEGIN
    INSERT INTO activity_fts(activity_fts, rowid, title_or_query, channel_or_source, domain, raw_excerpt, category)
    VALUES ('delete', old.id, old.title_or_query, old.channel_or_source, old.domain, old.raw_excerpt, old.category);
    INSERT INTO activity_fts(rowid, title_or_query, channel_or_source, domain, raw_excerpt, category)
    VALUES (new.id, new.title_or_query, new.channel_or_source, new.domain, new.raw_excerpt, new.category);
END;

CREATE INDEX idx_activities_service ON activities(service);
CREATE INDEX idx_activities_month ON activities(month);
CREATE INDEX idx_activities_category ON activities(category);
CREATE INDEX idx_activities_action ON activities(action);
CREATE INDEX idx_activities_domain ON activities(domain);
CREATE INDEX idx_activities_channel ON activities(channel_or_source);
CREATE INDEX idx_attachments_category ON gemini_attachments(category);
CREATE INDEX idx_attachments_extension ON gemini_attachments(extension);
CREATE INDEX idx_map_category ON map_details(category);

CREATE VIEW v_category_summary AS
SELECT category, COUNT(*) AS activity_count
FROM activities
GROUP BY category
ORDER BY activity_count DESC;

CREATE VIEW v_service_summary AS
SELECT service, COUNT(*) AS activity_count
FROM activities
GROUP BY service
ORDER BY activity_count DESC;

CREATE VIEW v_monthly_activity AS
SELECT month, service, category, COUNT(*) AS activity_count
FROM activities
WHERE month IS NOT NULL AND month <> ''
GROUP BY month, service, category
ORDER BY month, activity_count DESC;

CREATE VIEW v_youtube_channel_summary AS
SELECT channel_or_source AS channel, COUNT(*) AS item_count
FROM activities
WHERE service = 'YouTube' AND channel_or_source IS NOT NULL AND channel_or_source <> ''
GROUP BY channel_or_source
ORDER BY item_count DESC;

CREATE VIEW v_domain_summary AS
SELECT domain, COUNT(*) AS item_count
FROM activities
WHERE domain IS NOT NULL AND domain <> ''
GROUP BY domain
ORDER BY item_count DESC;
"""


def open_csv(name: str):
    path = SOURCE_DIR / name
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        yield from csv.DictReader(f)


def build_database() -> dict:
    if not SOURCE_DIR.exists():
        raise FileNotFoundError(f"Missing source directory: {SOURCE_DIR}")

    if DB_PATH.exists():
        DB_PATH.unlink()

    SCHEMA_PATH.write_text(SCHEMA.strip() + "\n", encoding="utf-8")

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(SCHEMA)
        conn.executemany(
            """
            INSERT INTO activities (
                service, event_at, month, action, category, title_or_query,
                channel_or_source, domain, url, raw_excerpt
            )
            VALUES (
                :service, :datetime, :month, :action, :category, :title_or_query,
                :channel_or_source, :domain, :url, :raw_excerpt
            )
            """,
            list(open_csv("full_activity_details.csv")),
        )
        conn.executemany(
            """
            INSERT INTO gemini_attachments (file_name, extension, size_kb, category)
            VALUES (:file_name, :extension, :size_kb, :category)
            """,
            list(open_csv("gemini_attachments.csv")),
        )
        conn.executemany(
            """
            INSERT INTO map_details (source_file, record_type, name_or_value, category)
            VALUES (:source_file, :record_type, :name_or_value, :category)
            """,
            list(open_csv("maps_extracted_details.csv")),
        )
        conn.execute("INSERT INTO activity_fts(activity_fts) VALUES ('rebuild')")
        conn.execute("ANALYZE")
        conn.commit()

        counts = {
            "activities": conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0],
            "gemini_attachments": conn.execute("SELECT COUNT(*) FROM gemini_attachments").fetchone()[0],
            "map_details": conn.execute("SELECT COUNT(*) FROM map_details").fetchone()[0],
            "db_path": str(DB_PATH),
            "schema_path": str(SCHEMA_PATH),
        }
        return counts
    finally:
        conn.close()


if __name__ == "__main__":
    print(build_database())
