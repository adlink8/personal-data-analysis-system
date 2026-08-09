"""Plan 61-06 Task 1 RED contract: metadata-only committed delta publication (HARNESS-05).

The producer entry is the real post-commit seam inside ``pk-sync conversations
--write`` (``personal_knowledge.application.sync``), NOT a test helper and never
``harness_reflection`` or a Candidate helper. The Kernel-side producer endpoint,
dispatcher replay and cursor contract live in the Node test
``apps/personal_intelligence_kernel/test/conversation-delta-reflection.test.mjs``.

Sentinel fixtures prove the published ``conversation.delta.committed`` event is
metadata-only: canonical checksum, committed watermark/publication version,
source/scope binding, occurred time and idempotency key. No conversation body,
prompt, credential, SQL statement or secret ever reaches the Journal
(``pi_kernel_events``), a consumer checkpoint, or the dispatcher callback.

Implementation target (Plan 61-06 Task 2):
    personal_knowledge/application/sync.py
      publish_conversation_delta_committed(
        *, canonical_checksum, source_checksum=None, watermark=None,
           publication_version=None, source="pk-sync", scope="agent.conversation",
           idempotency_key, occurred_at=None, committed=True,
           endpoint=None, internal_capability=None) -> dict
    called by _cmd_conversations() only after _record_conversation_versions()
    (strictly post-commit, checksum == committed watermark); every dry-run,
    uncommitted, missing or mismatched pre-commit state publishes nothing.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import os
import sqlite3
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.contract.test_pi_kernel_host import _Server  # noqa: E402
from personal_knowledge.application.sync import _cmd_conversations  # noqa: E402

try:  # RED until Plan 61-06 Task 2 adds the post-commit publisher hook.
    from personal_knowledge.application.sync import publish_conversation_delta_committed  # noqa: F401
    _PUBLISHER_AVAILABLE = True
    _PUBLISHER_IMPORT_ERROR = None
except (ImportError, AttributeError) as exc:  # expected RED: publisher not implemented yet
    _PUBLISHER_AVAILABLE = False
    _PUBLISHER_IMPORT_ERROR = exc


def _require_publisher() -> None:
    """Fail each publisher test with a clear RED signal until the seam exists."""
    if not _PUBLISHER_AVAILABLE:
        pytest.fail(
            "RED: personal_knowledge.application.sync.publish_conversation_delta_committed "
            f"missing (expected for 61-06 Task 1 RED): {_PUBLISHER_IMPORT_ERROR}",
            pytrace=False,
        )


DELTA_TYPE = "conversation.delta.committed"
INTERNAL_CAPABILITY = "test-conversation-delta-capability"

# Sentinel private values. If any reaches the published event, the Journal, a
# checkpoint or a callback payload the test fails closed, exactly like the
# Kernel-side privacy walker.
SENTINELS = (
    "PRIVATE_CONVERSATION_BODY_SENTINEL_4a1f2b",
    "PRIVATE_PROMPT_SENTINEL_9f3a1c",
    "PRIVATE_CREDENTIAL_SENTINEL_8a4c2d",
    "PRIVATE_SECRET_SENTINEL_1b5e7c",
    "SELECT * FROM messages WHERE body LIKE '%PRIVATE_SQL_SENTINEL_2c6d8e%'",
)
FORBIDDEN_KEYS = (
    "body",
    "content",
    "prompt",
    "completion",
    "payload",
    "inline_payload",
    "input",
    "output",
    "result",
    "credential",
    "secret",
    "token",
    "password",
    "path",
    "sql",
    "query",
    "statement",
)


def _walk_private(node, path, errors):
    if node is None:
        return
    if isinstance(node, dict):
        for key, value in node.items():
            if key.lower() in FORBIDDEN_KEYS:
                errors.append(f"forbidden key {key!r} at {path}")
            _walk_private(value, f"{path}.{key}", errors)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _walk_private(value, f"{path}[{index}]", errors)
    elif isinstance(node, str):
        for sentinel in SENTINELS:
            if sentinel in node:
                errors.append(f"sentinel leaked at {path}")


def _assert_metadata_only(value) -> None:
    errors: list[str] = []
    _walk_private(value, "event", errors)
    assert not errors, "delta event leaked private data: " + "; ".join(errors)


def _canonical_fixture(tmp_path: Path) -> Path:
    """A redacted temporary canonical store whose rows carry sentinel private values.

    The publisher must only ever derive a content checksum from this file; the
    sentinel bodies/prompt/credential/SQL must never appear in any event.
    """
    store = tmp_path / "canonical" / "agent_conversations.sqlite"
    store.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(store)
    con.execute(
        "CREATE TABLE messages (id INTEGER PRIMARY KEY, conversation_id TEXT, role TEXT, content TEXT)"
    )
    con.executemany(
        "INSERT INTO messages (conversation_id, role, content) VALUES (?,?,?)",
        [
            ("c1", "user", SENTINELS[1]),
            ("c1", "assistant", SENTINELS[0]),
            ("c2", "system", f"credential={SENTINELS[2]} secret={SENTINELS[3]}"),
            ("c2", "tool", SENTINELS[4]),
        ],
    )
    con.commit()
    con.close()
    return store


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _delta_rows(server: _Server) -> list[dict]:
    """Read the append-only EventJournal (the Journal) for committed delta events."""
    con = sqlite3.connect(f"file:{server.database.resolve().as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        return [
            dict(row)
            for row in con.execute(
                "SELECT sequence, event_id, event_type, event_json, canonical_checksum "
                "FROM pi_kernel_events WHERE event_type = ? ORDER BY sequence",
                (DELTA_TYPE,),
            )
        ]
    finally:
        con.close()


@pytest.fixture
def kernel_server(tmp_path: Path):
    """Real Kernel server (temp EventJournal) wired with the internal capability."""
    previous = os.environ.get("PI_KERNEL_INTERNAL_CAPABILITY")
    os.environ["PI_KERNEL_INTERNAL_CAPABILITY"] = INTERNAL_CAPABILITY
    server = _Server(tmp_path)
    yield server
    server.stop()
    if previous is None:
        os.environ.pop("PI_KERNEL_INTERNAL_CAPABILITY", None)
    else:
        os.environ["PI_KERNEL_INTERNAL_CAPABILITY"] = previous


def _committed_publish_args(canonical_checksum: str, source_checksum: str, **overrides) -> dict:
    args = {
        "canonical_checksum": canonical_checksum,
        "source_checksum": source_checksum,
        "watermark": canonical_checksum,
        "publication_version": "2026-08-09T09:00:00.000Z#1",
        "source": "pk-sync",
        "scope": "agent.conversation",
        "idempotency_key": "pi-idem-python-delta-001",
        "occurred_at": "2026-08-09T09:00:00.000Z",
        "committed": True,
    }
    args.update(overrides)
    return args


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_publisher_is_wired_into_the_production_post_commit_command():
    """The seam is the real `pk-sync conversations --write` post-commit path."""
    _require_publisher()
    source = inspect.getsource(_cmd_conversations)
    assert "publish_conversation_delta_committed(" in source, (
        "RED: _cmd_conversations must call the publisher after commit (expected for 61-06 Task 1)"
    )
    assert source.index("publish_conversation_delta_committed(") > source.index("_record_conversation_versions"), (
        "publisher must run after canonical records/watermark are committed"
    )


def test_committed_publish_reaches_the_journal_as_one_metadata_only_delta(kernel_server, tmp_path):
    """A committed canonical checksum/watermark publishes exactly one event."""
    _require_publisher()
    canonical = _canonical_fixture(tmp_path)
    checksum = hashlib.sha256(canonical.read_bytes()).hexdigest()
    source_checksum = _sha256("agentsview:sessions.db:fixture-v1")
    result = publish_conversation_delta_committed(
        endpoint=f"http://127.0.0.1:{kernel_server.port}",
        internal_capability=INTERNAL_CAPABILITY,
        **_committed_publish_args(checksum, source_checksum),
    )
    assert result.get("published") is True
    assert result.get("status") == "appended"
    assert result.get("event_type") == DELTA_TYPE
    assert result.get("event_id", "").startswith("pi_evt_")
    assert isinstance(result.get("sequence"), int)
    _assert_metadata_only(result)

    rows = _delta_rows(kernel_server)
    assert len(rows) == 1, "one committed sync emits exactly one delta event"
    event = json.loads(rows[0]["event_json"])
    assert event["type"] == DELTA_TYPE
    assert event["payload_ref"]["checksum"] == checksum, "AgentView->canonical binding carries the committed checksum"
    assert source_checksum in event["snapshot"], "source->AgentView binding is present in the snapshot"
    assert checksum in event["payload_ref"]["ref"], "payload ref binds the committed watermark"
    assert "2026-08-09T09:00:00.000Z#1" in event["payload_ref"]["ref"], "payload ref binds the publication version"
    assert rows[0]["canonical_checksum"] == checksum
    _assert_metadata_only(rows[0])


def test_exact_retry_returns_the_same_event_and_sequence(kernel_server, tmp_path):
    """An exact retry replays the same Journal event/sequence without a second delta."""
    _require_publisher()
    canonical = _canonical_fixture(tmp_path)
    checksum = hashlib.sha256(canonical.read_bytes()).hexdigest()
    source_checksum = _sha256("agentsview:sessions.db:fixture-v1")
    args = dict(
        endpoint=f"http://127.0.0.1:{kernel_server.port}",
        internal_capability=INTERNAL_CAPABILITY,
        **_committed_publish_args(checksum, source_checksum),
    )
    first = publish_conversation_delta_committed(**args)
    retry = publish_conversation_delta_committed(**args)
    assert first.get("published") is True and retry.get("published") is True
    assert retry.get("replay") is True
    assert retry.get("event_id") == first.get("event_id")
    assert retry.get("sequence") == first.get("sequence")
    assert len(_delta_rows(kernel_server)) == 1, "exact retry must not append a second delta"


def test_dry_run_uncommitted_missing_and_mismatched_publish_nothing(kernel_server, tmp_path):
    """Every non-committed or mismatched pre-commit state emits no event."""
    _require_publisher()
    canonical = _canonical_fixture(tmp_path)
    checksum = hashlib.sha256(canonical.read_bytes()).hexdigest()
    source_checksum = _sha256("agentsview:sessions.db:fixture-v1")
    cases = [
        ("dry-run/uncommitted", dict(committed=False)),
        ("missing canonical checksum", dict(canonical_checksum="")),
        ("missing watermark", dict(watermark="")),
        ("mismatched watermark", dict(watermark=_sha256("different:watermark"))),
    ]
    for label, overrides in cases:
        result = publish_conversation_delta_committed(
            endpoint=f"http://127.0.0.1:{kernel_server.port}",
            internal_capability=INTERNAL_CAPABILITY,
            **_committed_publish_args(checksum, source_checksum, **overrides),
        )
        assert result.get("published") is False, f"{label} must publish nothing"
        assert result.get("reason"), f"{label} must state a fail-closed reason"
        _assert_metadata_only(result)
    assert _delta_rows(kernel_server) == [], "no uncommitted/mismatched trigger may reach the Journal"


def test_sentinels_never_reach_journal_checkpoint_or_callback(kernel_server, tmp_path):
    """No conversation body/prompt/credential/SQL reaches the Journal payload."""
    _require_publisher()
    canonical = _canonical_fixture(tmp_path)
    checksum = hashlib.sha256(canonical.read_bytes()).hexdigest()
    source_checksum = _sha256("agentsview:sessions.db:fixture-v1")
    result = publish_conversation_delta_committed(
        endpoint=f"http://127.0.0.1:{kernel_server.port}",
        internal_capability=INTERNAL_CAPABILITY,
        **_committed_publish_args(checksum, source_checksum),
    )
    _assert_metadata_only(result)
    rows = _delta_rows(kernel_server)
    assert len(rows) == 1
    for row in rows:
        _assert_metadata_only(row)  # event_json + canonical_checksum carry no sentinel/private key
    raw_journal = kernel_server.database.read_bytes()
    for sentinel in SENTINELS:
        assert sentinel.encode() not in raw_journal, "sentinel reached the EventJournal file"


def test_publisher_signature_accepts_only_metadata_never_bodies():
    """The publisher seam can never be handed a body, prompt, credential or SQL."""
    _require_publisher()
    parameters = inspect.signature(publish_conversation_delta_committed).parameters
    names = set(parameters)
    assert "canonical_checksum" in names and "idempotency_key" in names, (
        "publisher must bind the canonical checksum and idempotency key"
    )
    forbidden = {"body", "content", "prompt", "completion", "credential", "secret", "sql", "statement", "token", "password", "path"}
    assert not (names & forbidden), f"publisher must never accept {sorted(names & forbidden)}"
    assert parameters["canonical_checksum"].kind is inspect.Parameter.KEYWORD_ONLY, "publisher args are keyword-only metadata"
