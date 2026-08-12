"""Phase 62-01 Task 2: immutable allowlisted source snapshot seam.

RED tests for :mod:`personal_knowledge.adapters.conversation_sources.snapshots`:
  - content-addressed deduplication of identical bytes
  - manifest write/replay verification
  - changed-source detection with immutable old artifacts
  - symlink/reparse escape and exact allowlisted relative path rejection
  - byte/count limits fail closed before any formal artifact is published
  - SQLite online-backup consistency under concurrent WAL writes
  - declared table/column capability validation; credential/account/token/auth
    tables are never copied into the published artifact or reported
  - failure before publication leaves no artifact or manifest behind

All sources are synthetic fixtures under pytest tmp_path. No live data, no
user paths, no network, no provider calls (D-31, D-05, D-08).
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from personal_knowledge.adapters.conversation_sources.snapshots import (
    CaptureError,
    CaptureManifest,
    CapturePolicy,
    capture_directory,
    capture_file,
    capture_sqlite,
    read_manifest,
    replay_manifest,
    write_manifest,
)


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _blob_root(dest: Path) -> Path:
    return dest / "artifacts"


def _make_sqlite_store(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, agent TEXT)")
    con.execute(
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, content TEXT)"
    )
    con.commit()
    return con


# --------------------------------------------------------------------------
# content-addressed file capture + dedup
# --------------------------------------------------------------------------


def test_file_capture_is_content_addressed_and_deduped(tmp_path: Path) -> None:
    src = tmp_path / "rollout.jsonl"
    _write(src, '{"type":"message"}\n')
    dest = tmp_path / "snap"
    art1, _ = capture_file(
        src, dest, relative_path="codex/rollout.jsonl",
        byte_limit=10_000, count_limit=100,
    )
    art2, _ = capture_file(
        src, dest, relative_path="codex/rollout.jsonl",
        byte_limit=10_000, count_limit=100,
    )
    assert art1.artifact_id == art2.artifact_id
    assert art1.content_hash == art2.content_hash
    assert art1.capture_method == "sha256"
    # dedup: exactly one blob stored for the same content
    assert len(list(_blob_root(dest).iterdir())) == 1


def test_changed_source_detected_and_old_artifact_immutable(tmp_path: Path) -> None:
    src = tmp_path / "f.jsonl"
    _write(src, "v1\n")
    dest = tmp_path / "snap"
    art1, _ = capture_file(
        src, dest, relative_path="f.jsonl", byte_limit=100_000, count_limit=100,
    )
    _write(src, "v2\n")
    art2, _ = capture_file(
        src, dest, relative_path="f.jsonl", byte_limit=100_000, count_limit=100,
    )
    assert art1.content_hash != art2.content_hash
    assert art1.artifact_id != art2.artifact_id
    # both blobs remain on disk: capture is append-only / immutable
    blob_ids = {p.name for p in _blob_root(dest).iterdir()}
    assert art1.artifact_id in blob_ids
    assert art2.artifact_id in blob_ids


# --------------------------------------------------------------------------
# manifest write / replay
# --------------------------------------------------------------------------


def test_manifest_write_and_replay_verify_artifacts(tmp_path: Path) -> None:
    src = tmp_path / "a.jsonl"
    _write(src, "data\n")
    dest = tmp_path / "snap"
    art, _ = capture_file(
        src, dest, relative_path="a.jsonl", byte_limit=100_000, count_limit=100,
    )
    manifest = CaptureManifest(
        manifest_id="m1",
        source_root=str(src.parent),
        capture_method="file",
        artifacts=(art,),
        policy=CapturePolicy(byte_limit=100_000, count_limit=100),
        schema_digest=None,
        privacy_dispositions=(),
        created_at="2026-08-12T00:00:00Z",
    )
    manifest_path = write_manifest(manifest, dest)
    loaded = read_manifest(manifest_path)
    assert loaded.manifest_id == "m1"
    assert loaded.capture_method == "file"
    assert loaded.artifacts[0].content_hash == art.content_hash
    replay = replay_manifest(loaded, _blob_root(dest))
    assert replay.ok
    assert replay.missing == []
    assert replay.mismatched == []


# --------------------------------------------------------------------------
# symlink / reparse / allowlisted path validation
# --------------------------------------------------------------------------


def test_symlink_reparse_escape_rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside_secret.txt"
    _write(outside, "secret\n")
    root = tmp_path / "root"
    root.mkdir()
    link = root / "leak.txt"
    created = False
    try:
        link.symlink_to(outside)
        created = True
    except (OSError, NotImplementedError):
        # Windows without Developer Mode: fall back to a junction, which is a
        # reparse point too and requires no privilege to create.
        try:
            import _winapi

            _winapi.CreateJunction(str(outside), str(link))
            created = True
        except (OSError, AttributeError, ImportError):
            pytest.skip("neither symlinks nor junctions available on this host")
    assert created, "escape fixture could not be created"
    with pytest.raises(CaptureError, match="symlink|reparse|junction"):
        capture_file(
            link, tmp_path / "snap", relative_path="leak.txt",
            byte_limit=100_000, count_limit=100,
        )
    # fail closed: no artifact published
    assert not _blob_root(tmp_path / "snap").exists()


def test_exact_allowlisted_relative_paths_reject_escape(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    _write(root / "ok.jsonl", "ok\n")
    _write(tmp_path / "outside.jsonl", "out\n")
    # parent traversal is rejected
    with pytest.raises(CaptureError, match="escape|relative"):
        capture_directory(
            root, tmp_path / "snap",
            include_relative=("../outside.jsonl",),
            byte_limit=100_000, count_limit=100,
        )
    # absolute path input is rejected
    with pytest.raises(CaptureError, match="escape|relative|absolute"):
        capture_directory(
            root, tmp_path / "snap",
            include_relative=(str(root / "ok.jsonl"),),
            byte_limit=100_000, count_limit=100,
        )
    assert not _blob_root(tmp_path / "snap").exists()


def test_directory_capture_allowlisted_paths_only(tmp_path: Path) -> None:
    root = tmp_path / "grok"
    root.mkdir()
    _write(root / "summary.json", "{}")
    _write(root / "transcript.jsonl", "line1\n")
    _write(root / "events.jsonl", "e1\n")
    _write(root / "token_secrets.txt", "should-not-be-captured")
    manifest, artifacts = capture_directory(
        root, tmp_path / "snap",
        include_relative=("summary.json", "transcript.jsonl", "events.jsonl"),
        byte_limit=100_000, count_limit=100,
    )
    paths = {a.relative_path for a in artifacts}
    assert paths == {"summary.json", "transcript.jsonl", "events.jsonl"}
    assert "token_secrets.txt" not in paths
    assert manifest.capture_method == "directory"
    assert len(manifest.artifacts) == 3


# --------------------------------------------------------------------------
# byte / count limits fail closed
# --------------------------------------------------------------------------


def test_byte_limit_fails_closed_before_publish(tmp_path: Path) -> None:
    src = tmp_path / "big.jsonl"
    _write(src, "x" * 5000)
    dest = tmp_path / "snap"
    with pytest.raises(CaptureError, match="byte"):
        capture_file(
            src, dest, relative_path="big.jsonl",
            byte_limit=100, count_limit=100,
        )
    assert not _blob_root(dest).exists()
    assert not (dest / "manifest.json").exists()


def test_count_limit_fails_closed_before_publish(tmp_path: Path) -> None:
    root = tmp_path / "dir"
    root.mkdir()
    _write(root / "a.jsonl", "a")
    _write(root / "b.jsonl", "b")
    with pytest.raises(CaptureError, match="count"):
        capture_directory(
            root, tmp_path / "snap",
            include_relative=("a.jsonl", "b.jsonl"),
            byte_limit=100_000, count_limit=1,
        )
    assert not _blob_root(tmp_path / "snap").exists()
    assert not (tmp_path / "snap" / "manifest.json").exists()


# --------------------------------------------------------------------------
# SQLite capture: WAL consistency + allowlist + forbidden tables
# --------------------------------------------------------------------------


def test_sqlite_capture_is_wal_consistent_under_concurrent_writes(
    tmp_path: Path,
) -> None:
    src = tmp_path / "live.sqlite"
    con = sqlite3.connect(str(src))
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, agent TEXT)")
    con.execute(
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id TEXT, content TEXT)"
    )
    for i in range(50):
        con.execute("INSERT INTO sessions VALUES (?, 'codex')", (f"s{i}",))
    con.commit()
    baseline = con.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]

    stop = threading.Event()

    def writer() -> None:
        i = 1000
        while not stop.is_set():
            try:
                con.execute(
                    "INSERT INTO messages VALUES (?, 's0', 'body')", (i,)
                )
                con.commit()
            except sqlite3.Error:  # pragma: no cover - defensive
                pass
            i += 1

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    try:
        art, snap_path = capture_sqlite(
            src, tmp_path / "snap",
            allowed_tables=("sessions", "messages"),
            allowed_columns={
                "sessions": ("id", "agent"),
                "messages": ("id", "session_id", "content"),
            },
            byte_limit=1_000_000, count_limit=10_000,
        )
    finally:
        stop.set()
        thread.join()

    check = sqlite3.connect(str(snap_path))
    try:
        assert check.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        count = check.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        assert count == baseline  # consistent snapshot, no torn rows
        assert art.content_hash
    finally:
        check.close()
    con.close()


def test_sqlite_capture_excludes_credential_tables(tmp_path: Path) -> None:
    src = tmp_path / "store.sqlite"
    con = sqlite3.connect(str(src))
    con.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY, agent TEXT)")
    con.execute("CREATE TABLE messages (id INTEGER PRIMARY KEY, content TEXT)")
    con.execute("CREATE TABLE accounts (id TEXT PRIMARY KEY, password TEXT)")
    con.execute("CREATE TABLE auth_tokens (id TEXT PRIMARY KEY, token TEXT)")
    con.execute("CREATE TABLE api_credentials (id TEXT PRIMARY KEY, secret TEXT)")
    con.commit()
    con.close()

    art, snap_path = capture_sqlite(
        src, tmp_path / "snap",
        allowed_tables=("sessions", "messages"),
        allowed_columns={"sessions": ("id",), "messages": ("id", "content")},
        byte_limit=1_000_000, count_limit=100,
    )
    check = sqlite3.connect(str(snap_path))
    try:
        tables = {
            r[0]
            for r in check.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        check.close()
    assert tables == {"sessions", "messages"}
    assert not any(
        any(part in t for part in ("account", "token", "credential", "auth"))
        for t in tables
    )
    # schema digest recorded, no body
    assert art.schema_digest
    # privacy dispositions are metadata-only but mention the excluded kinds
    joined = " ".join(art.privacy_dispositions).lower()
    assert any(part in joined for part in ("credential", "token", "account"))


def test_sqlite_missing_declared_column_fails_closed(tmp_path: Path) -> None:
    src = tmp_path / "store.sqlite"
    con = sqlite3.connect(str(src))
    con.execute("CREATE TABLE sessions (id TEXT PRIMARY KEY)")
    con.commit()
    con.close()
    dest = tmp_path / "snap"
    with pytest.raises(CaptureError, match="column|schema"):
        capture_sqlite(
            src, dest,
            allowed_tables=("sessions",),
            allowed_columns={"sessions": ("id", "agent")},
            byte_limit=1_000_000, count_limit=100,
        )
    assert not _blob_root(dest).exists()
    assert not (dest / "manifest.json").exists()


def test_sqlite_forbidden_table_in_allowlist_fails_closed(tmp_path: Path) -> None:
    src = tmp_path / "store.sqlite"
    con = sqlite3.connect(str(src))
    con.execute("CREATE TABLE accounts (id TEXT PRIMARY KEY, password TEXT)")
    con.commit()
    con.close()
    dest = tmp_path / "snap"
    with pytest.raises(CaptureError, match="forbidden|allowlist"):
        capture_sqlite(
            src, dest,
            allowed_tables=("accounts",),
            allowed_columns={"accounts": ("id",)},
            byte_limit=1_000_000, count_limit=100,
        )
    assert not _blob_root(dest).exists()
