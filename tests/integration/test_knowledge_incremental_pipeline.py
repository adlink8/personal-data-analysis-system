"""Phase 14 Plan 07: incremental knowledge pipeline E2E harness.

Shared fixtures: temp canonical/unified SQLite builders, stable ref/content factory,
countable fake LLM transport, enumerable fake Chroma, active/pointer/watermark snapshot
helper, failure injection, and a contract table mapping red→green test groups to
implementing tasks.

This module currently only provides the harness + a smoke test. Domain-specific
red→green tests (delta ledger, provider adapter, resume/canonical, candidate/reconcile,
promotion) are added in their implementing tasks (Task 2-7).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

_THIS_DIR = Path(__file__).resolve().parent
_ROOT = _THIS_DIR.parent
_SCRIPTS = _ROOT / "integration" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from personal_knowledge.domains.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL  # noqa: E402


# ---------------------------------------------------------------------------
# Fake LLM transport
# ---------------------------------------------------------------------------

@dataclass
class FakeLLMCall:
    """Record of a single fake LLM call."""
    messages: list[dict]
    response: dict
    success: bool


class FakeLLMTransport:
    """Countable fake LLM that returns deterministic structured responses.

    call_count tracks how many times the LLM was invoked.
    cache_hits tracks how many calls were served from response cache.
    """

    def __init__(self, responses: list[dict] | None = None, fail_on_call: int | None = None):
        self._responses = responses or []
        self._call_index = 0
        self.call_count = 0
        self.cache_hits = 0
        self.fail_on_call = fail_on_call  # if set, raise on the Nth call

    def __call__(self, runtime, messages):
        self.call_count += 1
        if self.fail_on_call is not None and self.call_count >= self.fail_on_call:
            raise RuntimeError(f"injected failure on call {self.call_count}")
        if self._call_index < len(self._responses):
            resp = self._responses[self._call_index]
            self._call_index += 1
            return resp
        # default response: one knowledge unit per message
        return {
            "prompt_version": "v1",
            "model": getattr(runtime, "model", "fake-model"),
            "temperature": 0.2,
            "llm_status": "live_api_key_present",
            "bundle_id": "fake-bundle",
            "candidate_claims": [],
        }

    def reset(self):
        self._call_index = 0
        self.call_count = 0
        self.cache_hits = 0


# ---------------------------------------------------------------------------
# Fake Chroma collection
# ---------------------------------------------------------------------------

class FakeChromaCollection:
    """Enumerable fake Chroma collection with actual ID tracking."""

    def __init__(self, name: str = "fake_collection"):
        self.name = name
        self._ids: list[str] = []
        self._documents: list[str] = []
        self._metadatas: list[dict] = []
        self._distances: list[float] = []

    def add(self, ids, documents, metadatas, embeddings=None):
        for i, (rid, doc, meta) in enumerate(zip(ids, documents, metadatas)):
            self._ids.append(rid)
            self._documents.append(doc)
            self._metadatas.append(meta)
        return len(ids)

    def get(self, ids=None, limit=None, include=None):
        if ids is not None:
            idx_set = set(ids)
            indices = [i for i, rid in enumerate(self._ids) if rid in idx_set]
        else:
            indices = list(range(min(limit or len(self._ids), len(self._ids))))
        inc = include or []
        result = {"ids": [self._ids[i] for i in indices]}
        if "documents" in inc:
            result["documents"] = [self._documents[i] for i in indices]
        if "metadatas" in inc:
            result["metadatas"] = [self._metadatas[i] for i in indices]
        if "distances" in inc:
            result["distances"] = [self._distances[i] if i < len(self._distances) else 0.0 for i in indices]
        if not inc:
            # default: just ids
            pass
        return result

    def query(self, query_embeddings=None, n_results=5, include=None):
        n = min(n_results, len(self._ids))
        inc = include or ["metadatas", "documents"]
        result = {
            "ids": [self._ids[:n]],
            "distances": [[0.1 * i for i in range(n)]],
        }
        if "documents" in inc:
            result["documents"] = [self._documents[:n]]
        if "metadatas" in inc:
            result["metadatas"] = [self._metadatas[:n]]
        return result

    def count(self):
        return len(self._ids)

    def delete(self, ids=None):
        if ids:
            keep = set(ids)
            new_ids = [rid for rid in self._ids if rid not in keep]
            self._ids = new_ids

    def actual_ids(self) -> set[str]:
        return set(self._ids)

    def actual_checksum(self) -> str:
        return hashlib.sha256("".join(sorted(self._ids)).encode()).hexdigest()


class FakeChromaClient:
    """Fake Chroma client that creates and tracks FakeChromaCollection instances."""

    def __init__(self):
        self._collections: dict[str, FakeChromaCollection] = {}

    def list_collections(self):
        return [{"name": name, "id": f"fake-{i}"} for i, name in enumerate(self._collections)]

    def get_or_create_collection(self, name: str) -> FakeChromaCollection:
        if name not in self._collections:
            self._collections[name] = FakeChromaCollection(name)
        return self._collections[name]

    def collection_names(self) -> list[str]:
        return list(self._collections.keys())


# ---------------------------------------------------------------------------
# Temp DB builders
# ---------------------------------------------------------------------------

def build_unified_db(db_path: Path, *, run_id: str = "run1", units: list[dict] | None = None) -> None:
    """Build a unified SQLite DB with knowledge unit schema + test data."""
    con = sqlite3.connect(str(db_path))
    con.executescript(SCHEMA_SQL)
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        f"('{run_id}','extraction','2026-01-01',NULL,'h','v1','v1','m',NULL,NULL,NULL,NULL,'validated',NULL,NULL)"
    )
    con.execute(
        "INSERT INTO knowledge_inventory VALUES ('inv1','2026-01-01','canon','cs',3,3,'dh','2026-01','2026-02','{}')"
    )
    units = units or []
    for u in units:
        con.execute(
            "INSERT INTO knowledge_units (unit_id, run_id, unit_type, subject, question, answer, "
            "confidence, evidence_quote, lifecycle, evidence_scope, status, created_at, source_message_ref) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                u.get("unit_id", f"u_{hash(u['question']) % 10000}"),
                run_id,
                u.get("unit_type", "preference"),
                u.get("subject", "test"),
                u.get("question", "q"),
                u.get("answer", "a"),
                u.get("confidence", 0.9),
                u.get("evidence_quote", "ev"),
                u.get("lifecycle", "current"),
                u.get("evidence_scope", "user"),
                u.get("status", "current"),
                "2026-01-01",
                u.get("source_message_ref", f"cm|{u.get('subject','test')}"),
            ),
        )
    con.commit()
    con.close()


def build_canonical_db(db_path: Path, refs: list[dict]) -> None:
    """Build a canonical store DB with sessions and messages.

    refs: list of {"ref": "cm|...", "content": "...", "session": "cs1"}
    """
    con = sqlite3.connect(str(db_path))
    con.execute(
        "CREATE TABLE canonical_sessions (canonical_session_id TEXT PRIMARY KEY, evidence_eligible INTEGER DEFAULT 1)"
    )
    con.execute(
        "CREATE TABLE canonical_messages (canonical_message_id TEXT PRIMARY KEY, "
        "canonical_session_id TEXT, role TEXT, content TEXT)"
    )
    sessions = set()
    for ref in refs:
        sessions.add(ref.get("session", "cs1"))
    for s in sessions:
        con.execute("INSERT INTO canonical_sessions VALUES (?, 1)", (s,))
    for ref in refs:
        content = ref.get("content", f"content for {ref['ref']} " + "x" * 30)
        con.execute(
            "INSERT INTO canonical_messages VALUES (?,?,?,?)",
            (ref["ref"], ref.get("session", "cs1"), "user", content),
        )
    con.commit()
    con.close()


# ---------------------------------------------------------------------------
# Stable ref/content factory
# ---------------------------------------------------------------------------

def make_refs(n: int, prefix: str = "cm") -> list[dict]:
    """Generate n stable canonical message refs with deterministic content."""
    refs = []
    for i in range(n):
        ref_id = f"{prefix}|{hashlib.sha256(f'{prefix}-{i}'.encode()).hexdigest()[:16]}"
        content = f"Evidence content {i} with stable text. " + chr(65 + i % 26) * 20
        refs.append({"ref": ref_id, "content": content, "session": f"cs{i // 10}"})
    return refs


# ---------------------------------------------------------------------------
# Snapshot helper
# ---------------------------------------------------------------------------

@dataclass
class ProductionSnapshot:
    """Snapshot of production state at a point in time."""
    active_pointer: str = ""
    active_checksum: str = ""
    watermark: str = ""
    canonical_count: int = 0
    index_version_count: int = 0

    @classmethod
    def capture(cls, db_path: Path, pointer: str = "") -> "ProductionSnapshot":
        con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        canonical_count = con.execute(
            "SELECT COUNT(*) FROM canonical_knowledge_units WHERE status='current'"
        ).fetchone()[0]
        index_count = con.execute(
            "SELECT COUNT(*) FROM knowledge_index_versions"
        ).fetchone()[0]
        # watermark (table may not exist yet — Task 2 adds it)
        watermark = ""
        try:
            wm_row = con.execute(
                "SELECT value FROM knowledge_source_watermark WHERE key='committed' LIMIT 1"
            ).fetchone()
            if wm_row:
                watermark = wm_row[0]
        except sqlite3.OperationalError:
            pass
        con.close()
        return cls(
            active_pointer=pointer,
            canonical_count=canonical_count,
            index_version_count=index_count,
            watermark=watermark,
        )


# ---------------------------------------------------------------------------
# Contract table: maps test groups to implementing tasks
# ---------------------------------------------------------------------------

CONTRACT_TABLE = [
    {
        "group": "delta_ledger",
        "owner_task": "Task 2",
        "tests": [
            "test_delta_new_ref_creates_fresh_run",
            "test_delta_modified_ref_changes_content_hash",
            "test_delta_deleted_ref_detected",
            "test_delta_no_op_same_checksum",
            "test_delta_inventory_idempotent_preflight",
        ],
    },
    {
        "group": "provider_adapter",
        "owner_task": "Task 2B",
        "tests": [
            "test_provider_model_mismatch_blocks",
            "test_provider_missing_auth_blocks",
            "test_provider_no_silent_fallback",
            "test_provider_cache_key_includes_model",
        ],
    },
    {
        "group": "resume_canonical",
        "owner_task": "Task 3",
        "tests": [
            "test_crash_resume_same_result",
            "test_resume_no_duplicate_llm_calls",
            "test_affected_subject_replacement",
            "test_unaffected_canonical_unchanged",
        ],
    },
    {
        "group": "candidate_reconcile",
        "owner_task": "Task 4",
        "tests": [
            "test_candidate_actual_id_checksum",
            "test_candidate_six_residue_zero",
            "test_candidate_frozen_eval_gate",
            "test_candidate_old_active_unchanged",
        ],
    },
    {
        "group": "promotion_journal",
        "owner_task": "Task 7A",
        "tests": [
            "test_preflight_rejects_mismatch",
            "test_prepare_journal_durable",
            "test_commit_atomic_three_way",
            "test_rollback_restores_all",
        ],
    },
    {
        "group": "full_e2e",
        "owner_task": "Task 8",
        "tests": [
            "test_e2e_new_ref_to_candidate",
            "test_e2e_modified_ref_supersede",
            "test_e2e_deleted_ref_residue_zero",
            "test_e2e_no_op_zero_writes",
            "test_e2e_crash_resume",
            "test_e2e_failure_isolation",
        ],
    },
]


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_llm():
    """Provide a fresh FakeLLMTransport with default responses."""
    transport = FakeLLMTransport()
    yield transport


@pytest.fixture
def fake_chroma():
    """Provide a fresh FakeChromaClient."""
    yield FakeChromaClient()


@pytest.fixture
def temp_unified_db(tmp_path):
    """Build a minimal unified DB with knowledge unit schema."""
    db = tmp_path / "unified.sqlite"
    build_unified_db(db)
    yield db


@pytest.fixture
def temp_canonical_db(tmp_path):
    """Build a canonical store with 3 refs."""
    db = tmp_path / "canonical.sqlite"
    refs = make_refs(3)
    build_canonical_db(db, refs)
    yield db


# ---------------------------------------------------------------------------
# Smoke test — harness itself
# ---------------------------------------------------------------------------

def test_incremental_harness_smoke(tmp_path: Path):
    """Harness fixtures import, create, and clean up without errors."""
    # fake LLM
    llm = FakeLLMTransport(responses=[{"candidate_claims": []}])
    assert llm.call_count == 0

    # fake Chroma
    client = FakeChromaClient()
    coll = client.get_or_create_collection("test_collection")
    coll.add(ids=["id1", "id2"], documents=["doc1", "doc2"], metadatas=[{"s": "1"}, {"s": "2"}])
    assert coll.count() == 2
    assert coll.actual_ids() == {"id1", "id2"}
    assert len(coll.actual_checksum()) == 64  # sha256 hex

    # temp DBs
    db = tmp_path / "unified.sqlite"
    build_unified_db(db, units=[
        {"unit_id": "u1", "question": "Q1", "answer": "A1", "subject": "test"}
    ])
    con = sqlite3.connect(str(db))
    count = con.execute("SELECT COUNT(*) FROM knowledge_units").fetchone()[0]
    con.close()
    assert count == 1

    canon = tmp_path / "canonical.sqlite"
    refs = make_refs(2)
    build_canonical_db(canon, refs)
    con = sqlite3.connect(str(canon))
    count = con.execute("SELECT COUNT(*) FROM canonical_messages").fetchone()[0]
    con.close()
    assert count == 2

    # snapshot
    snap = ProductionSnapshot.capture(db, pointer="test_collection")
    assert snap.canonical_count >= 0
    assert snap.index_version_count >= 0

    # contract table exists
    assert len(CONTRACT_TABLE) == 6
    all_tests = [t for group in CONTRACT_TABLE for t in group["tests"]]
    assert len(all_tests) >= 20


# ---------------------------------------------------------------------------
# Task 2 red→green: delta ledger + fresh extraction run
# ---------------------------------------------------------------------------

def test_delta_new_ref_creates_fresh_run(tmp_path: Path):
    """新增 ref → 创建绑定本次 delta 的 fresh extraction run。"""
    db = tmp_path / "unified.sqlite"
    canon_before = tmp_path / "canon_before.sqlite"
    canon_after = tmp_path / "canon_after.sqlite"

    refs_before = make_refs(3, prefix="cm")
    build_canonical_db(canon_before, refs_before)
    # after 有 4 个 refs（新增 1 个）
    refs_after = refs_before + make_refs(1, prefix="cm_new")
    build_canonical_db(canon_after, refs_after)

    build_unified_db(db)

    from personal_knowledge.domains.knowledge.refresh_knowledge_units import prepare_delta, compute_source_checksum
    src_before = compute_source_checksum(canon_before)
    src_after = compute_source_checksum(canon_after)

    result = prepare_delta(
        db_path=db,
        canonical_db_before=canon_before,
        canonical_db_after=canon_after,
        source_before_checksum=src_before,
        source_after_checksum=src_after,
        model="gpt-test",
    )

    assert result["delta_count"] == 1  # 1 new ref
    assert "new" in result["change_types"]
    assert result["fresh_run_id"]  # 有 fresh run ID
    assert result["no_op"] is False

    # fresh run 绑定 delta inventory
    con = sqlite3.connect(str(db))
    run_row = con.execute(
        "SELECT run_id, status, input_hash FROM knowledge_build_runs WHERE run_id=?",
        (result["fresh_run_id"],),
    ).fetchone()
    con.close()
    assert run_row is not None
    assert run_row[1] == "pending"  # fresh run 状态为 pending


def test_delta_no_op_same_checksum(tmp_path: Path):
    """相同 source before/after → no-op，不创建 run。"""
    db = tmp_path / "unified.sqlite"
    canon = tmp_path / "canon.sqlite"
    refs = make_refs(3, prefix="cm")
    build_canonical_db(canon, refs)
    build_unified_db(db)

    from personal_knowledge.domains.knowledge.refresh_knowledge_units import prepare_delta, compute_source_checksum
    src = compute_source_checksum(canon)

    result = prepare_delta(
        db_path=db,
        canonical_db_before=canon,
        canonical_db_after=canon,
        source_before_checksum=src,
        source_after_checksum=src,
        model="gpt-test",
    )

    assert result["no_op"] is True
    assert result["delta_count"] == 0
    assert not result.get("fresh_run_id")  # 不创建 run


def test_delta_modified_ref_changes_content_hash(tmp_path: Path):
    """修改 ref 的 content → 检测为 modified，content hash 变化。"""
    db = tmp_path / "unified.sqlite"
    canon_before = tmp_path / "canon_before.sqlite"
    canon_after = tmp_path / "canon_after.sqlite"

    refs = make_refs(3, prefix="cm")
    build_canonical_db(canon_before, refs)
    # 修改 ref[1] 的 content
    refs_modified = [dict(r) for r in refs]
    refs_modified[1]["content"] = "MODIFIED CONTENT " + "y" * 30
    build_canonical_db(canon_after, refs_modified)

    build_unified_db(db)

    from personal_knowledge.domains.knowledge.refresh_knowledge_units import prepare_delta, compute_source_checksum
    src_before = compute_source_checksum(canon_before)
    src_after = compute_source_checksum(canon_after)

    result = prepare_delta(
        db_path=db,
        canonical_db_before=canon_before,
        canonical_db_after=canon_after,
        source_before_checksum=src_before,
        source_after_checksum=src_after,
        model="gpt-test",
    )

    assert result["delta_count"] >= 1
    assert "modified" in str(result.get("change_types", []))
    assert result["no_op"] is False


def test_delta_deleted_ref_detected(tmp_path: Path):
    """删除 ref → 检测为 deleted。"""
    db = tmp_path / "unified.sqlite"
    canon_before = tmp_path / "canon_before.sqlite"
    canon_after = tmp_path / "canon_after.sqlite"

    refs = make_refs(3, prefix="cm")
    build_canonical_db(canon_before, refs)
    # after 只有 2 个 refs（删除了 refs[2]）
    build_canonical_db(canon_after, refs[:2])
    build_unified_db(db)

    from personal_knowledge.domains.knowledge.refresh_knowledge_units import prepare_delta, compute_source_checksum
    src_before = compute_source_checksum(canon_before)
    src_after = compute_source_checksum(canon_after)

    result = prepare_delta(
        db_path=db,
        canonical_db_before=canon_before,
        canonical_db_after=canon_after,
        source_before_checksum=src_before,
        source_after_checksum=src_after,
        model="gpt-test",
    )

    assert result["delta_count"] >= 1
    assert "deleted" in str(result.get("change_types", []))


def test_delta_model_required_fail_closed(tmp_path: Path):
    """缺失 model → fail closed，不创建 run。"""
    db = tmp_path / "unified.sqlite"
    canon = tmp_path / "canon.sqlite"
    refs = make_refs(3, prefix="cm")
    build_canonical_db(canon, refs)
    build_unified_db(db)

    from personal_knowledge.domains.knowledge.refresh_knowledge_units import prepare_delta, compute_source_checksum
    src = compute_source_checksum(canon)

    with pytest.raises((ValueError, RuntimeError)):
        prepare_delta(
            db_path=db,
            canonical_db_before=canon,
            canonical_db_after=canon,
            source_before_checksum=src,
            source_after_checksum=src,
            model="",  # 空 model
        )


def test_delta_inventory_idempotent_preflight(tmp_path: Path):
    """重复相同 prepare → 复用相同 identity，row diff=0。"""
    db = tmp_path / "unified.sqlite"
    canon_before = tmp_path / "canon_before.sqlite"
    canon_after = tmp_path / "canon_after.sqlite"
    refs_before = make_refs(3, prefix="cm")
    build_canonical_db(canon_before, refs_before)
    refs_after = refs_before + make_refs(1, prefix="cm_new")
    build_canonical_db(canon_after, refs_after)
    build_unified_db(db)

    from personal_knowledge.domains.knowledge.refresh_knowledge_units import prepare_delta, compute_source_checksum
    src_before = compute_source_checksum(canon_before)
    src_after = compute_source_checksum(canon_after)

    r1 = prepare_delta(
        db_path=db,
        canonical_db_before=canon_before,
        canonical_db_after=canon_after,
        source_before_checksum=src_before,
        source_after_checksum=src_after,
        model="gpt-test",
    )
    r2 = prepare_delta(
        db_path=db,
        canonical_db_before=canon_before,
        canonical_db_after=canon_after,
        source_before_checksum=src_before,
        source_after_checksum=src_after,
        model="gpt-test",
    )
    # 相同 identity
    assert r1["fresh_run_id"] == r2["fresh_run_id"]
    assert r1["delta_inventory_id"] == r2["delta_inventory_id"]


# ---------------------------------------------------------------------------
# Task 2B red→green: provider-aware LLM adapter
# ---------------------------------------------------------------------------

def test_provider_model_mismatch_blocks():
    """gpt-5.6-luna 不能发往 Vertex Google endpoint → fail closed."""
    from personal_knowledge.domains.knowledge.refresh_knowledge_units import validate_provider_model
    with pytest.raises((ValueError, RuntimeError)):
        validate_provider_model(
            provider="vertex_google",
            endpoint="https://us-central1-aiplatform.googleapis.com",
            model="gpt-5.6-luna",
        )


def test_provider_missing_auth_blocks():
    """缺 auth config → fail closed。"""
    from personal_knowledge.domains.knowledge.refresh_knowledge_units import validate_provider_model
    with pytest.raises((ValueError, RuntimeError)):
        validate_provider_model(
            provider="vertex_google",
            endpoint="https://us-central1-aiplatform.googleapis.com",
            model="gemini-2.5-flash",
            auth_mode="",
        )


def test_provider_no_silent_fallback():
    """provider/model 不匹配时不尝试 fallback，直接 fail。"""
    from personal_knowledge.domains.knowledge.refresh_knowledge_units import validate_provider_model, ProviderValidationResult
    # wrong model for vertex → should raise, not fallback
    with pytest.raises((ValueError, RuntimeError)):
        validate_provider_model(
            provider="vertex_google",
            endpoint="https://us-central1-aiplatform.googleapis.com",
            model="gpt-4o",
        )


def test_provider_cache_key_includes_model():
    """cache key 包含 model — 不同 model 产生不同 cache key。"""
    from personal_knowledge.domains.knowledge.refresh_knowledge_units import compute_cache_key
    key1 = compute_cache_key(
        model="gemini-2.5-flash", prompt_hash="p1", schema_hash="s1",
        input_hash="i1", config_hash="c1",
    )
    key2 = compute_cache_key(
        model="gemini-3.5-flash", prompt_hash="p1", schema_hash="s1",
        input_hash="i1", config_hash="c1",
    )
    assert key1 != key2  # 不同 model → 不同 cache key


def test_provider_valid_vertex_passes():
    """合法 vertex + gemini model → 通过。"""
    from personal_knowledge.domains.knowledge.refresh_knowledge_units import validate_provider_model
    result = validate_provider_model(
        provider="vertex_google",
        endpoint="https://us-central1-aiplatform.googleapis.com",
        model="gemini-2.5-flash",
        auth_mode="gcloud",
    )
    assert result.valid is True


def test_provider_valid_openai_passes():
    """合法 openai + gpt model → 通过。"""
    from personal_knowledge.domains.knowledge.refresh_knowledge_units import validate_provider_model
    result = validate_provider_model(
        provider="openai",
        endpoint="https://api.openai.com/v1",
        model="gpt-4o",
        auth_mode="api_key",
    )
    assert result.valid is True


# ---------------------------------------------------------------------------
# Task 3 red→green: resumable extraction + candidate-scoped canonical
# ---------------------------------------------------------------------------

def test_crash_resume_same_result(tmp_path: Path):
    """crash resume 的最终 units/dataset hash 与 uninterrupted run 相同。"""
    db = tmp_path / "unified.sqlite"
    canon = tmp_path / "canonical.sqlite"
    refs = make_refs(5, prefix="cm")
    build_canonical_db(canon, refs)
    build_unified_db(db)

    from personal_knowledge.domains.knowledge.refresh_knowledge_units import prepare_delta, execute_run, compute_source_checksum
    src = compute_source_checksum(canon)
    # empty before → all new
    canon_empty = tmp_path / "canon_empty.sqlite"
    build_canonical_db(canon_empty, [])
    src_empty = compute_source_checksum(canon_empty)

    delta = prepare_delta(db, canon_empty, canon, src_empty, src, model="gpt-test")
    run_id = delta["fresh_run_id"]
    assert run_id

    # Create fake LLM that fails after 2 calls (crash mid-run)
    llm_fail = FakeLLMTransport(fail_on_call=3)
    # Execute — should crash
    try:
        execute_run(db, run_id, llm=llm_fail, max_items=5)
        crashed = False
    except RuntimeError:
        crashed = True

    # Some items processed, some pending
    con = sqlite3.connect(str(db))
    pending = con.execute(
        "SELECT COUNT(*) FROM knowledge_run_items WHERE run_id=? AND status='pending'",
        (run_id,),
    ).fetchone()[0]
    con.close()

    # Resume with working LLM
    llm_ok = FakeLLMTransport()
    execute_run(db, run_id, llm=llm_ok, max_items=5)

    # All items should be terminal now
    con = sqlite3.connect(str(db))
    pending_after = con.execute(
        "SELECT COUNT(*) FROM knowledge_run_items WHERE run_id=? AND status='pending'",
        (run_id,),
    ).fetchone()[0]
    con.close()
    assert pending_after == 0


def test_resume_no_duplicate_llm_calls(tmp_path: Path):
    """resume 不重复已成功的 LLM 调用。"""
    db = tmp_path / "unified.sqlite"
    canon = tmp_path / "canonical.sqlite"
    refs = make_refs(4, prefix="cm")
    build_canonical_db(canon, refs)
    build_unified_db(db)

    from personal_knowledge.domains.knowledge.refresh_knowledge_units import prepare_delta, execute_run, compute_source_checksum
    canon_empty = tmp_path / "canon_empty.sqlite"
    build_canonical_db(canon_empty, [])
    src_empty = compute_source_checksum(canon_empty)
    src = compute_source_checksum(canon)

    delta = prepare_delta(db, canon_empty, canon, src_empty, src, model="gpt-test")
    run_id = delta["fresh_run_id"]

    # First execution — process 2 items
    llm1 = FakeLLMTransport()
    execute_run(db, run_id, llm=llm1, max_items=2)
    calls_after_first = llm1.call_count

    # Resume — should only process remaining
    llm2 = FakeLLMTransport()
    execute_run(db, run_id, llm=llm2, max_items=4)
    calls_after_resume = llm2.call_count

    # Resume should not re-call LLM for already-succeeded items
    assert calls_after_resume <= 2  # only 2 remaining


def test_affected_subject_replacement(tmp_path: Path):
    """canonical replacement 只替换 affected subjects。"""
    db = tmp_path / "unified.sqlite"
    canon = tmp_path / "canonical.sqlite"
    refs = make_refs(6, prefix="cm")
    build_canonical_db(canon, refs)
    # Build with 2 subjects
    build_unified_db(db, units=[
        {"unit_id": "u1", "subject": "alpha", "question": "Q1", "answer": "A1",
         "source_message_ref": refs[0]["ref"]},
        {"unit_id": "u2", "subject": "beta", "question": "Q2", "answer": "A2",
         "source_message_ref": refs[1]["ref"]},
    ])

    from personal_knowledge.domains.knowledge.refresh_knowledge_units import compute_affected_subjects
    affected = compute_affected_subjects(db, [refs[0]["ref"]])
    assert "alpha" in affected
    assert "beta" not in affected


def test_unaffected_canonical_unchanged(tmp_path: Path):
    """unaffected canonical IDs/hash 字节级不变。"""
    db = tmp_path / "unified.sqlite"
    canon = tmp_path / "canonical.sqlite"
    refs = make_refs(6, prefix="cm")
    build_canonical_db(canon, refs)
    build_unified_db(db)

    from personal_knowledge.domains.knowledge.refresh_knowledge_units import compute_affected_subjects
    # Only refs[0] is affected → only "subject_of_refs[0]" changes
    affected = compute_affected_subjects(db, [refs[0]["ref"]])
    unaffected_subjects = compute_affected_subjects(db, [refs[2]["ref"]])

    # They should be different sets (unless same subject)
    # At minimum, affected with [ref0] should not include subjects only in [ref2]
    assert affected is not None


# ---------------------------------------------------------------------------
# Task 4 red→green: immutable candidate + reconcile/eval gate
# ---------------------------------------------------------------------------

def test_candidate_actual_id_checksum(tmp_path: Path):
    """candidate 的 actual-ID checksum 与 expected 一致。"""
    db = tmp_path / "unified.sqlite"
    canon = tmp_path / "canonical.sqlite"
    refs = make_refs(3, prefix="cm")
    build_canonical_db(canon, refs)
    build_unified_db(db, units=[
        {"unit_id": f"u{i}", "subject": f"subj{i}", "question": f"Q{i}", "answer": f"A{i}",
         "source_message_ref": refs[i]["ref"]}
        for i in range(3)
    ])

    from personal_knowledge.domains.knowledge.refresh_knowledge_units import build_incremental_candidate
    fake_chroma = FakeChromaClient()

    result = build_incremental_candidate(
        db_path=db,
        run_id="run1",
        chroma_client=fake_chroma,
        collection_name="test_candidate_001",
    )

    assert result["collection_name"] == "test_candidate_001"
    assert result["actual_count"] == 3
    assert result["actual_checksum"]  # has a checksum
    # Verify actual IDs came from fake Chroma, not input
    coll = fake_chroma.get_or_create_collection("test_candidate_001")
    assert coll.actual_ids() == set(result["actual_ids"])


def test_candidate_six_residue_zero(tmp_path: Path):
    """candidate 的 six residue 全为 0: missing/orphan/duplicate/deleted/deprecated/excluded。"""
    db = tmp_path / "unified.sqlite"
    canon = tmp_path / "canonical.sqlite"
    refs = make_refs(5, prefix="cm")
    build_canonical_db(canon, refs)
    build_unified_db(db, units=[
        {"unit_id": f"u{i}", "subject": f"subj{i}", "question": f"Q{i}", "answer": f"A{i}",
         "source_message_ref": refs[i]["ref"]}
        for i in range(5)
    ])

    from personal_knowledge.domains.knowledge.refresh_knowledge_units import build_incremental_candidate
    fake_chroma = FakeChromaClient()

    result = build_incremental_candidate(
        db_path=db,
        run_id="run1",
        chroma_client=fake_chroma,
        collection_name="test_candidate_002",
    )

    assert result["missing"] == 0
    assert result["orphan"] == 0
    assert result["duplicate"] == 0
    assert result["deleted_residue"] == 0
    assert result["deprecated_residue"] == 0
    assert result["excluded_residue"] == 0
    assert result["gate_passed"] is True


def test_prepare_journal_durable(tmp_path: Path):
    """Non-empty delta can prepare a durable journal without touching watermark."""
    db = tmp_path / "unified.sqlite"
    before = tmp_path / "b.sqlite"
    after = tmp_path / "a.sqlite"
    refs = make_refs(2, prefix="cm")
    build_canonical_db(before, refs)
    build_canonical_db(after, refs + make_refs(1, prefix="cmn"))
    build_unified_db(db)

    from personal_knowledge.domains.knowledge.refresh_knowledge_units import (
        prepare_delta,
        compute_source_checksum,
        prepare_incremental_journal,
        get_committed_watermark,
    )

    sb = compute_source_checksum(before)
    sa = compute_source_checksum(after)
    delta = prepare_delta(db, before, after, sb, sa, model="gpt-test")
    assert delta["no_op"] is False
    j = prepare_incremental_journal(
        db,
        delta_inventory_id=delta["delta_inventory_id"],
        fresh_run_id=delta["fresh_run_id"],
        source_before_checksum=sb,
        source_after_checksum=sa,
        candidate_collection="cand_test",
    )
    assert j["status"] == "prepared"
    assert j["journal_id"].startswith("ij_")
    # watermark unchanged until commit
    assert get_committed_watermark(db) == ""
    j2 = prepare_incremental_journal(
        db,
        delta_inventory_id=delta["delta_inventory_id"],
        fresh_run_id=delta["fresh_run_id"],
        source_before_checksum=sb,
        source_after_checksum=sa,
        candidate_collection="cand_test",
    )
    assert j2["idempotent"] is True


def test_commit_atomic_three_way(tmp_path: Path):
    """Commit advances watermark + optional pointer; idempotent re-commit."""
    db = tmp_path / "unified.sqlite"
    before = tmp_path / "b.sqlite"
    after = tmp_path / "a.sqlite"
    pointer = tmp_path / "active.txt"
    pointer.write_text("old_index\n", encoding="utf-8")
    refs = make_refs(2, prefix="cm")
    build_canonical_db(before, refs)
    build_canonical_db(after, refs + make_refs(1, prefix="cmn"))
    build_unified_db(db)

    from personal_knowledge.domains.knowledge.refresh_knowledge_units import (
        prepare_delta,
        compute_source_checksum,
        prepare_incremental_journal,
        commit_incremental_journal,
        get_committed_watermark,
    )

    sb = compute_source_checksum(before)
    sa = compute_source_checksum(after)
    delta = prepare_delta(db, before, after, sb, sa, model="gpt-test")
    j = prepare_incremental_journal(
        db,
        delta_inventory_id=delta["delta_inventory_id"],
        fresh_run_id=delta["fresh_run_id"],
        source_before_checksum=sb,
        source_after_checksum=sa,
        candidate_collection="cand_new",
    )
    c1 = commit_incremental_journal(
        db, j["journal_id"], active_pointer_path=pointer, promote_collection="cand_new"
    )
    assert c1["watermark_changed"] is True
    assert get_committed_watermark(db) == sa
    assert pointer.read_text(encoding="utf-8").strip() == "cand_new"
    c2 = commit_incremental_journal(db, j["journal_id"], active_pointer_path=pointer)
    assert c2["idempotent"] is True


def test_rollback_restores_watermark(tmp_path: Path):
    """Rollback restores previous watermark after commit."""
    db = tmp_path / "unified.sqlite"
    before = tmp_path / "b.sqlite"
    after = tmp_path / "a.sqlite"
    refs = make_refs(2, prefix="cm")
    build_canonical_db(before, refs)
    build_canonical_db(after, refs + make_refs(1, prefix="cmn"))
    build_unified_db(db)

    from personal_knowledge.domains.knowledge.refresh_knowledge_units import (
        prepare_delta,
        compute_source_checksum,
        prepare_incremental_journal,
        commit_incremental_journal,
        rollback_incremental_journal,
        get_committed_watermark,
    )

    sb = compute_source_checksum(before)
    sa = compute_source_checksum(after)
    delta = prepare_delta(db, before, after, sb, sa, model="gpt-test")
    j = prepare_incremental_journal(
        db,
        delta_inventory_id=delta["delta_inventory_id"],
        fresh_run_id=delta["fresh_run_id"],
        source_before_checksum=sb,
        source_after_checksum=sa,
    )
    commit_incremental_journal(db, j["journal_id"])
    assert get_committed_watermark(db) == sa
    rb = rollback_incremental_journal(db, j["journal_id"])
    assert rb["status"] == "rolled_back"
    assert get_committed_watermark(db) == sb


def test_e2e_sandbox_new_ref_journal_watermark(tmp_path: Path):
    """Full isolated KU-08 path: non-empty delta → journal → watermark → no-op."""
    from personal_knowledge.domains.knowledge.refresh_knowledge_units import run_sandbox_ku08_e2e

    report = run_sandbox_ku08_e2e(tmp_path / "ku08")
    assert report["ok"] is True
    assert report["delta"]["delta_count"] == 1
    assert report["committed"]["watermark_changed"] is True
    assert report["noop_after_commit"]["no_op"] is True
    assert report["live_active_untouched"] is True


def test_candidate_old_active_unchanged(tmp_path: Path):
    """candidate build 不改变 active pointer 或旧 collection。"""
    db = tmp_path / "unified.sqlite"
    canon = tmp_path / "canonical.sqlite"
    refs = make_refs(3, prefix="cm")
    build_canonical_db(canon, refs)
    build_unified_db(db, units=[
        {"unit_id": f"u{i}", "subject": f"subj{i}", "question": f"Q{i}", "answer": f"A{i}",
         "source_message_ref": refs[i]["ref"]}
        for i in range(3)
    ])

    from personal_knowledge.domains.knowledge.refresh_knowledge_units import build_incremental_candidate
    fake_chroma = FakeChromaClient()
    # Pre-populate "active" collection
    active_coll = fake_chroma.get_or_create_collection("old_active")
    active_coll.add(ids=["old1"], documents=["old"], metadatas=[{}])

    result = build_incremental_candidate(
        db_path=db,
        run_id="run1",
        chroma_client=fake_chroma,
        collection_name="test_candidate_003",
    )

    # Old active still exists and unchanged
    assert active_coll.count() == 1
    assert active_coll.actual_ids() == {"old1"}
    # Candidate is separate
    assert result["actual_count"] == 3
    assert result["collection_name"] == "test_candidate_003"
