"""Phase 4: wiki consolidated page store + consolidation task + page-first read.

Covers:
- ``wiki_projection_pages`` schema and page store round-trip (4.1)
- ``consolidate_wiki`` bucketing / deterministic body / idempotency (4.2)
- page-first ``topic_get`` with read-time fallback (4.3)
- subject topics in ``topic.list`` directory (4.3)
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from personal_knowledge.application.wiki.consolidate_wiki import (
    ConsolidationStats,
    build_page_body,
    bucket_by_subject,
    consolidate_wiki,
    load_current_units,
)
from personal_knowledge.services.topic_projection import TopicProjectionService, parse_topic_key
from personal_knowledge.wiki.derived_store import (
    ProjectionDependency,
    ProjectionPage,
    ProjectionVersion,
    SCHEMA_VERSION,
    connect_rw,
    insert_page,
    insert_version,
    latest_page,
)
from personal_knowledge.wiki.materialization import (
    dependency_manifest_checksum,
    projection_checksum,
)
from personal_knowledge.wiki.page_reader import WikiPageReader, parse_page_body, subject_topic_id


def _write_version_and_page(path, *, subject="PowerShell", body=None, freshness="fresh"):
    """Write a version row + page row so the joinable page reader finds them."""
    from personal_knowledge.wiki.page_reader import page_checksum
    con = connect_rw(path)
    try:
        normalized = subject.strip().lower()
        topic_id = subject_topic_id(normalized)
        body = body or {
            "schema": "wiki_page_body_v1",
            "topic": {"topic_id": topic_id, "topic_type": "subject", "canonical_key": f"subject:{normalized}", "display_label": f"subject:{normalized}"},
            "subject": normalized,
            "aggregation": {"unit_count": 1, "unit_type_counts": {"fact": 1}, "lifecycle_counts": {"current": 1}},
            "claims": [{"claim_type": "knowledge_unit", "unit_id": "cu|a", "unit_type": "fact", "question": "q1", "answer": "ans1", "confidence": 0.9, "lifecycle": "current", "evidence_refs": []}],
            "evidence_refs": [],
            "source_fingerprint": "fp",
        }
        body_json = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        checksum = page_checksum(body_json)
        deps = [ProjectionDependency("knowledge_unit", normalized, expected_checksum="fp", order_key=f"knowledge_unit:{normalized}")]
        version = ProjectionVersion(
            topic_id=topic_id, topic_type="subject", projection_format_version=SCHEMA_VERSION,
            projection_version="pv_1",
            projection_checksum=projection_checksum(topic_id=topic_id, topic_type="subject", snapshot_bindings={"knowledge_unit": normalized}, dependencies=deps, source_refs={}),
            generated_at="2026-08-11T00:00:00Z", freshness_status=freshness, reason_codes=(),
            snapshot_bindings={"knowledge_unit": normalized},
            dependency_manifest_checksum=dependency_manifest_checksum(deps),
        )
        insert_version(con, version, deps)
        insert_page(con, ProjectionPage(
            topic_id=topic_id, topic_type="subject", projection_version="pv_1",
            page_body=body_json, page_checksum=checksum, generated_at="2026-08-11T00:00:00Z",
            snapshot_bindings={"knowledge_unit": normalized},
        ))
        return topic_id
    finally:
        con.close()


# ---------------------------------------------------------------------------
# 4.1 — page store
# ---------------------------------------------------------------------------

def test_page_schema_and_round_trip(tmp_path):
    path = tmp_path / "wiki.sqlite"
    con = connect_rw(path)
    try:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "wiki_projection_pages" in tables
        # existing metadata tables preserved
        assert {"wiki_projection_versions", "wiki_projection_dependencies", "wiki_projection_invalidations"} <= tables
    finally:
        con.close()
    topic_id = _write_version_and_page(path)
    page = latest_page(path, topic_id)
    assert page is not None
    assert page.topic_type == "subject"
    assert page.projection_version == "pv_1"
    assert page.freshness_status == "fresh"


def test_page_schema_keeps_metadata_columns_clean(tmp_path):
    """The new page table must not add forbidden content columns to versions."""
    path = tmp_path / "wiki.sqlite"
    con = connect_rw(path)
    try:
        columns = {row[1] for row in con.execute("PRAGMA table_info(wiki_projection_versions)")}
        forbidden = {"content", "raw_message", "embedding", "provider_response", "evidence_body"}
        assert columns.isdisjoint(forbidden)
    finally:
        con.close()


# ---------------------------------------------------------------------------
# 4.2 — consolidation task
# ---------------------------------------------------------------------------

def _fixture_units():
    return [
        {"canonical_unit_id": "cu|a", "subject": "PowerShell", "unit_type": "fact", "question": "q1", "answer": "ans1", "confidence": 0.9, "lifecycle": "current", "version": 1},
        {"canonical_unit_id": "cu|b", "subject": "PowerShell", "unit_type": "preference", "question": "q2", "answer": "ans2", "confidence": 0.8, "lifecycle": "current", "version": 2},
        {"canonical_unit_id": "cu|c", "subject": "工作流", "unit_type": "fact", "question": "q3", "answer": "ans3", "confidence": 0.7, "lifecycle": "deprecated", "version": 1},
    ]


def test_bucket_by_subject_normalizes_case_and_trim():
    buckets = bucket_by_subject(_fixture_units())
    assert "powershell" in buckets
    assert "工作流" in buckets
    assert all(unit["subject"] in {"PowerShell", "工作流"} for units in buckets.values() for unit in units)


def test_page_body_is_deterministic_and_aggregated_only():
    body = build_page_body("PowerShell", _fixture_units()[:2], {"cu|a": ["cm|1"], "cu|b": []})
    assert body["schema"] == "wiki_page_body_v1"
    assert body["subject"] == "powershell"
    assert body["aggregation"]["unit_count"] == 2
    assert body["aggregation"]["unit_type_counts"] == {"fact": 1, "preference": 1}
    assert body["evidence_refs"] == ["cm|1"]
    # no raw conversation text anywhere
    dumped = json.dumps(body, ensure_ascii=False)
    assert "对话" not in dumped
    # deterministic
    assert build_page_body("PowerShell", _fixture_units()[:2], {"cu|a": ["cm|1"], "cu|b": []}) == body


def test_consolidate_wiki_write_and_idempotency(tmp_path, monkeypatch):
    db = tmp_path / "ku.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE canonical_knowledge_units (canonical_unit_id TEXT, subject TEXT, unit_type TEXT, question TEXT, answer TEXT, confidence REAL, lifecycle TEXT, status TEXT, version INTEGER)")
    for unit in _fixture_units():
        con.execute(
            "INSERT INTO canonical_knowledge_units VALUES (?,?,?,?,?,?,?,'current',?)",
            (unit["canonical_unit_id"], unit["subject"], unit["unit_type"], unit["question"], unit["answer"], unit["confidence"], unit["lifecycle"], unit["version"]),
        )
    con.execute("CREATE TABLE canonical_unit_members (id INTEGER, canonical_unit_id TEXT, member_unit_id TEXT)")
    con.execute("CREATE TABLE knowledge_unit_evidence (id INTEGER, unit_id TEXT, evidence_ref TEXT, evidence_type TEXT)")
    con.commit()
    con.close()
    store = tmp_path / "wiki.sqlite"

    stats = consolidate_wiki(db, store, write=True, subjects=["PowerShell"])
    assert stats.units_loaded == 3
    assert stats.pages_written == 1
    assert stats.errors == []

    # idempotency: second run with same input → skip, no new version
    stats2 = consolidate_wiki(db, store, write=True, subjects=["PowerShell"])
    assert stats2.global_noop is True
    con = sqlite3.connect(store)
    assert con.execute("SELECT COUNT(*) FROM wiki_projection_pages WHERE topic_id=?", (subject_topic_id("PowerShell"),)).fetchone()[0] == 1
    con.close()


def test_consolidate_wiki_fail_safe_on_missing_store(tmp_path):
    stats = consolidate_wiki(Path(tmp_path) / "missing.sqlite", Path(tmp_path) / "wiki.sqlite", write=True)
    assert isinstance(stats, ConsolidationStats)
    assert stats.errors  # unified db unavailable reported, no raise


# ---------------------------------------------------------------------------
# 4.3 — page-first read with fallback
# ---------------------------------------------------------------------------

class Reader:
    def __init__(self, data):
        self.data = data

    def invoke(self, operation, **params):
        return self.data.get(operation, {"ok": True, "data": {}})


def _service(store=None):
    return TopicProjectionService(
        personal_reader=Reader({"state.current": {"ok": True, "snapshot": {"snapshot_id": "ps"}, "data": {"items": []}}}),
        decision_reader=Reader({"recommendations.list": {"ok": True, "data": {"items": []}}}),
        external_reader=Reader({"external.list": {"ok": True, "data": {"snapshot": {"snapshot_id": "ex"}, "facts": []}}}),
        page_reader=WikiPageReader(store) if store is not None else None,
        now=lambda: "2026-08-11T00:00:00Z",
    )


def test_topic_get_prefers_stored_page_body(tmp_path):
    store = tmp_path / "wiki.sqlite"
    _write_version_and_page(store)
    result = _service(store).invoke("topic.get", topic_key="subject:PowerShell")
    assert result["ok"] is True
    assert result["status"] == "fresh"
    assert result["data"]["subject"] == "powershell"
    assert result["data"]["claims"][0]["unit_id"] == "cu|a"
    assert result["authorities"] == {"wiki": "ok"}


def test_topic_get_falls_back_when_page_missing(tmp_path):
    # no page store at all → compute path (empty authority data, fresh)
    result = _service(None).invoke("topic.get", topic_key="subject:PowerShell")
    assert result["ok"] is False
    assert result["error"] == "topic_not_found"


def test_topic_list_includes_subject_pages_when_reader_configured(tmp_path):
    store = tmp_path / "wiki.sqlite"
    _write_version_and_page(store)
    result = _service(store).invoke("topic.list", limit=50)
    assert result["ok"] is True
    keys = [item["canonical_key"] for item in result["data"]["items"]]
    assert "subject:powershell" in keys


def test_topic_list_unchanged_without_reader():
    result = _service(None).invoke("topic.list", limit=50)
    assert result["ok"] is True
    assert all(item["topic_type"] != "subject" for item in result["data"]["items"])


def test_subject_topic_id_is_stable_and_keyable():
    assert subject_topic_id("PowerShell") == subject_topic_id("powershell")
    key = parse_topic_key("subject:powershell")
    assert key.topic_type == "subject"
    assert key.parts == ("powershell",)
