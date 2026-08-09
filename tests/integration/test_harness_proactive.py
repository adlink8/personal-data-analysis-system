"""Plan 61-07 Task 1 RED contract: deterministic proactive projection (HARNESS-05).

The proactive adapter consumes only declared deterministic event/cluster metadata
(committed ``conversation.delta.committed`` bindings, D-18/D-23) and projects
review cards through global/project/category (``同步``, ``简报``, ``反思候选``)
controls and quiet hours. One evidence cluster yields exactly one card with a
merged count and source/time/receipt/support/conflict drilldown. Dismissal/undo
is append-only feedback that never reorders manual messages and never changes
scheduling, permissions, values or authority (D-24/D-25/D-26/D-29).

Implementation target (Plan 61-07 Task 2):
    src/personal_knowledge/application/conversation/harness_proactive.py
      CONTROL_CATEGORIES      -> frozenset({"同步", "简报", "反思候选"})
      DECLARED_EVENT_TYPES    -> frozenset({"conversation.delta.committed"})
      ProactiveError(code, detail)
      project_proactive_state(*, events, controls, quiet_hours, now, manual_order)
      apply_dismissal(*, feedback_log, cluster_key, feedback_id,
                      actor_identity_hash, idempotency_key, now)
      undo_dismissal(*, feedback_log, dismissal_feedback_id, feedback_id,
                     actor_identity_hash, idempotency_key, now)

Running this against the current tree MUST FAIL: harness_proactive.py does not
exist. Every failure points at the missing adapter, never at a syntax error.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

try:  # RED until Plan 61-07 Task 2 creates the module.
    from personal_knowledge.application.conversation.harness_proactive import (  # noqa: F401
        CONTROL_CATEGORIES,
        DECLARED_EVENT_TYPES,
        ProactiveError,
        apply_dismissal,
        project_proactive_state,
        undo_dismissal,
    )
    _PROACTIVE_AVAILABLE = True
    _PROACTIVE_IMPORT_ERROR = None
except (ImportError, AttributeError) as exc:  # expected RED: adapter not implemented yet
    _PROACTIVE_AVAILABLE = False
    _PROACTIVE_IMPORT_ERROR = exc


def _require_proactive() -> None:
    """Fail each proactive test with a clear RED signal until the adapter exists."""
    if not _PROACTIVE_AVAILABLE:
        pytest.fail(
            "RED: personal_knowledge.application.conversation.harness_proactive "
            f"missing (expected for 61-07 Task 1 RED): {_PROACTIVE_IMPORT_ERROR}",
            pytrace=False,
        )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


# Contract error codes the adapter must use (fail closed, never a crash).
ERR_UNDECLARED_EVENT = "declared_event"
ERR_UNDECLARED_CATEGORY = "declared_category"
ERR_QUIET_HOURS_INVALID = "quiet_hours_invalid"

# Sentinel private values. If any reaches a projection, card or feedback receipt
# the test fails closed, exactly like the Kernel-side privacy walker.
SENTINELS = (
    "PRIVATE_CONVERSATION_BODY_SENTINEL_4a1f2b",
    "PRIVATE_PROMPT_SENTINEL_9f3a1c",
    "PRIVATE_CREDENTIAL_SENTINEL_8a4c2d",
    "PRIVATE_SECRET_SENTINEL_1b5e7c",
)
# Mirrors proactive/schema.py FORBIDDEN_KEYS plus SQL/body guards.
FORBIDDEN_KEYS = (
    "body", "content", "raw_text", "note", "prompt", "completion",
    "credential", "secret", "token", "password", "webhook", "command",
    "executable", "connector", "recipient", "send_target", "payment_detail",
    "query", "sql", "path", "statement",
)


def _walk_private(node, path, errors):
    if node is None:
        return
    if isinstance(node, dict):
        for key, value in node.items():
            lowered = key.lower()
            if lowered in FORBIDDEN_KEYS or any(
                token in lowered for token in ("credential", "password", "webhook", "send_target")
            ):
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
    _walk_private(value, "proactive", errors)
    assert not errors, "proactive projection leaked private data: " + "; ".join(errors)


def _delta_event(cluster_key: str, *, ordinal: int = 1, source: str = "pk-sync",
                 category: str = "反思候选", scope: str = "global",
                 occurred_at: str = "2026-08-09T09:00:00.000Z") -> dict[str, Any]:
    """Deterministic metadata-only committed-delta fixture for one evidence cluster.

    Bodies/credentials never enter these fixtures; each event carries only the
    declared cluster/evidence metadata the deterministic adapter may project.
    """
    canonical = _sha256(f"canonical:{cluster_key}:{ordinal}")
    return {
        "event_id": "pi_evt_" + _sha256(f"delta:{cluster_key}:{ordinal}"),
        "type": "conversation.delta.committed",
        "source": source,
        "canonical_checksum": canonical,
        "watermark": canonical,
        "rule_version": "conversation-reflection-v1",
        "occurred_at": occurred_at,
        "category": category,
        "scope": scope,
        "cluster_key": cluster_key,
        "support_refs": (f"evidence:{cluster_key}:{ordinal}:support",),
        "conflict_refs": (f"evidence:{cluster_key}:{ordinal}:conflict",),
        "receipt_checksum": _sha256(f"receipt:{cluster_key}:{ordinal}"),
    }


def _controls(**overrides) -> tuple[dict[str, Any], ...]:
    """Global/project x category (`同步`, `简报`, `反思候选`) enabled flags.

    Overrides use ``"<scope>.<category>"`` keys, e.g. ``global.简报=False`` or
    ``project:alpha.简报=False``.
    """
    rows = [
        {"scope": "global", "category": "同步", "enabled": True},
        {"scope": "global", "category": "简报", "enabled": True},
        {"scope": "global", "category": "反思候选", "enabled": True},
    ]
    by_key = {f"{row['scope']}.{row['category']}": row for row in rows}
    for key, enabled in overrides.items():
        if key not in by_key:
            scope, category = key.rsplit(".", 1)
            row = {"scope": scope, "category": category, "enabled": enabled}
            rows.append(row)
            by_key[key] = row
        by_key[key]["enabled"] = enabled
    return tuple(rows)


QUIET_HOURS = {"enabled": True, "start": "22:00", "end": "07:00"}
QUIET_OFF = {"enabled": False, "start": "22:00", "end": "07:00"}
NOW_QUIET = "2026-08-09T23:30:00Z"   # inside 22:00-07:00 -> quiet_until 07:00
NOW_ACTIVE = "2026-08-09T12:00:00Z"  # outside quiet window -> active


def _manual_order(count: int = 3) -> tuple[str, ...]:
    return tuple(f"manual-{index}" for index in range(1, count + 1))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_only_declared_deterministic_events_can_create_a_projection():
    """Only committed delta events project; model wakes/schedules/actions never do."""
    _require_proactive()
    assert DECLARED_EVENT_TYPES == {"conversation.delta.committed"}
    events = (_delta_event("cluster-1"), _delta_event("cluster-1", ordinal=2))
    projection = project_proactive_state(
        events=events, controls=_controls(), quiet_hours=QUIET_OFF,
        now=NOW_ACTIVE, manual_order=_manual_order(),
    )
    assert projection["active"] is True
    assert projection["cards"], "declared committed delta events must project cards"
    for label, bad_type in [
        ("model self-wake", "model.wake"),
        ("learned schedule", "schedule.learned"),
        ("autonomous action", "agent.action"),
    ]:
        with pytest.raises(ProactiveError, match=ERR_UNDECLARED_EVENT):
            project_proactive_state(
                events=({**_delta_event("cluster-1"), "type": bad_type},),
                controls=_controls(), quiet_hours=QUIET_OFF,
                now=NOW_ACTIVE, manual_order=_manual_order(),
            )
            pytest.fail(f"{label} must be rejected as a non-declared deterministic event")


def test_control_categories_are_exactly_the_three_declared():
    """Category controls are exactly 同步 / 简报 / 反思候选 (UI-SPEC drawer)."""
    _require_proactive()
    assert CONTROL_CATEGORIES == {"同步", "简报", "反思候选"}
    with pytest.raises(ProactiveError, match=ERR_UNDECLARED_CATEGORY):
        project_proactive_state(
            events=(_delta_event("cluster-1", category="autonomous"),),
            controls=_controls(), quiet_hours=QUIET_OFF,
            now=NOW_ACTIVE, manual_order=_manual_order(),
        )


def test_category_controls_gate_projection_per_category():
    """A disabled category produces no card of that category."""
    _require_proactive()
    events = (_delta_event("cluster-1", category="反思候选"),)
    enabled = project_proactive_state(
        events=events, controls=_controls(), quiet_hours=QUIET_OFF,
        now=NOW_ACTIVE, manual_order=_manual_order(),
    )
    assert any(card["category"] == "反思候选" for card in enabled["cards"])
    disabled = project_proactive_state(
        events=events, controls=_controls(**{"global.反思候选": False}),
        quiet_hours=QUIET_OFF, now=NOW_ACTIVE, manual_order=_manual_order(),
    )
    assert not any(card["category"] == "反思候选" for card in disabled["cards"]), (
        "a disabled category must not produce a card"
    )


def test_project_scope_control_suppresses_only_its_own_project():
    """Global/project scope resolution is deterministic and scoped."""
    _require_proactive()
    events = (
        _delta_event("cluster-global", scope="global"),
        _delta_event("cluster-alpha", scope="project:alpha", category="简报"),
        _delta_event("cluster-beta", scope="project:beta", category="简报"),
    )
    controls = _controls(**{"project:alpha.简报": False})
    projection = project_proactive_state(
        events=events, controls=controls, quiet_hours=QUIET_OFF,
        now=NOW_ACTIVE, manual_order=_manual_order(),
    )
    keys = {card["cluster_key"] for card in projection["cards"]}
    assert "cluster-alpha" not in keys, "a disabled project scope must not project a card"
    assert "cluster-global" in keys and "cluster-beta" in keys, (
        "other scopes must remain governed by their own controls"
    )


def test_quiet_hours_return_active_or_quiet_until():
    """Quiet hours produce quiet_until without scheduling any delivery."""
    _require_proactive()
    events = (_delta_event("cluster-1"),)
    quiet = project_proactive_state(
        events=events, controls=_controls(), quiet_hours=QUIET_HOURS,
        now=NOW_QUIET, manual_order=_manual_order(),
    )
    assert quiet["active"] is False
    assert quiet["quiet_until"] == "07:00", "quiet window must expose quiet_until without scheduling"
    active = project_proactive_state(
        events=events, controls=_controls(), quiet_hours=QUIET_HOURS,
        now=NOW_ACTIVE, manual_order=_manual_order(),
    )
    assert active["active"] is True and active["quiet_until"] is None
    off = project_proactive_state(
        events=events, controls=_controls(), quiet_hours=QUIET_OFF,
        now=NOW_QUIET, manual_order=_manual_order(),
    )
    assert off["active"] is True and off["quiet_until"] is None, (
        "disabled quiet hours never return quiet_until"
    )
    with pytest.raises(ProactiveError, match=ERR_QUIET_HOURS_INVALID):
        project_proactive_state(
            events=events, controls=_controls(),
            quiet_hours={"enabled": True, "start": "25:00", "end": "07:00"},
            now=NOW_ACTIVE, manual_order=_manual_order(),
        )


def test_one_card_per_evidence_cluster_with_merged_count_and_drilldown():
    """One evidence cluster renders one card with merged count + drilldown refs."""
    _require_proactive()
    events = (
        _delta_event("cluster-1", ordinal=1, occurred_at="2026-08-09T09:00:00.000Z"),
        _delta_event("cluster-1", ordinal=2, occurred_at="2026-08-09T09:05:00.000Z"),
        _delta_event("cluster-1", ordinal=3, occurred_at="2026-08-09T09:10:00.000Z"),
    )
    projection = project_proactive_state(
        events=events, controls=_controls(), quiet_hours=QUIET_OFF,
        now=NOW_ACTIVE, manual_order=_manual_order(),
    )
    cards = [card for card in projection["cards"] if card["cluster_key"] == "cluster-1"]
    assert len(cards) == 1, "one evidence cluster must yield exactly one card"
    card = cards[0]
    assert card["merged_count"] == 3
    merged = card["merged_evidence"]
    assert len(merged) == 3, "merged drilldown lists every merged evidence source/time/receipt"
    for item in merged:
        assert item["source"] and item["occurred_at"] and item["receipt_checksum"]
        assert item["support_refs"] and item["conflict_refs"]
    _assert_metadata_only(card)


def test_dismissal_is_append_only_and_idempotent():
    """Dismissal appends exactly one feedback entry; exact retry deduplicates."""
    _require_proactive()
    log: tuple = ()
    first = apply_dismissal(
        feedback_log=log, cluster_key="cluster-1", feedback_id="fb-1",
        actor_identity_hash="a" * 64, idempotency_key="pi-idem-dismiss-001",
        now="2026-08-09T10:00:00Z",
    )
    assert first["receipt"]["operation"] == "dismiss"
    log = first["feedback_log"]
    assert len(log) == 1
    replay = apply_dismissal(
        feedback_log=log, cluster_key="cluster-1", feedback_id="fb-1",
        actor_identity_hash="a" * 64, idempotency_key="pi-idem-dismiss-001",
        now="2026-08-09T10:00:00Z",
    )
    assert replay["existing"] is True
    assert len(replay["feedback_log"]) == 1, "an exact idempotent dismissal must not append twice"
    assert replay["receipt"]["feedback_id"] == first["receipt"]["feedback_id"]
    _assert_metadata_only(first["receipt"])


def test_undo_is_append_only_and_never_mutates_dismissal():
    """Undo appends a new entry and never deletes or mutates the dismissal."""
    _require_proactive()
    log: tuple = ()
    dismissed = apply_dismissal(
        feedback_log=log, cluster_key="cluster-1", feedback_id="fb-1",
        actor_identity_hash="a" * 64, idempotency_key="pi-idem-dismiss-001",
        now="2026-08-09T10:00:00Z",
    )
    log = dismissed["feedback_log"]
    original = log[0]
    undone = undo_dismissal(
        feedback_log=log, dismissal_feedback_id="fb-1", feedback_id="fb-2",
        actor_identity_hash="a" * 64, idempotency_key="pi-idem-undo-001",
        now="2026-08-09T10:05:00Z",
    )
    log = undone["feedback_log"]
    assert len(log) == 2, "undo appends a new feedback entry"
    assert log[0] == original, "undo must never mutate or delete the dismissal entry"
    assert log[1]["operation"] == "undo_dismissal"
    assert log[1]["dismissal_feedback_id"] == "fb-1"
    _assert_metadata_only(undone["receipt"])


def test_projection_never_reorders_manual_messages():
    """Proactive cards keep a quiet anchor and never rewrite manual ordering."""
    _require_proactive()
    manual = _manual_order(5)
    projection = project_proactive_state(
        events=(_delta_event("cluster-1"), _delta_event("cluster-2")),
        controls=_controls(), quiet_hours=QUIET_OFF,
        now=NOW_ACTIVE, manual_order=manual,
    )
    assert tuple(projection["manual_order"]) == manual, "manual message order must be preserved"
    for card in projection["cards"]:
        assert "anchor_before" in card, "each proactive card carries an anchor message id"
        assert card["anchor_before"] is None or card["anchor_before"] in manual


def test_no_scheduling_permission_value_or_authority_mutation(tmp_path):
    """Controls, dismissal and undo never change scheduling/permissions/values/authority."""
    _require_proactive()
    authority = tmp_path / "authority"
    authority.mkdir()
    files = {
        "canonical.sqlite": b"canonical-bytes",
        "active_pointer.txt": b"pointer-bytes",
        "schedule.json": b"{}",
        "permissions.json": b"{}",
        "values.json": b"{}",
    }
    for name, content in files.items():
        (authority / name).write_bytes(content)

    def fingerprints() -> dict[str, str]:
        return {name: hashlib.sha256((authority / name).read_bytes()).hexdigest() for name in files}

    before = fingerprints()
    project_proactive_state(
        events=(_delta_event("cluster-1"),),
        controls=_controls(**{"global.简报": False}),
        quiet_hours=QUIET_HOURS, now=NOW_QUIET, manual_order=_manual_order(),
    )
    log: tuple = ()
    dismissed = apply_dismissal(
        feedback_log=log, cluster_key="cluster-1", feedback_id="fb-1",
        actor_identity_hash="a" * 64, idempotency_key="pi-idem-dismiss-001",
        now="2026-08-09T10:00:00Z",
    )
    undo_dismissal(
        feedback_log=dismissed["feedback_log"], dismissal_feedback_id="fb-1",
        feedback_id="fb-2", actor_identity_hash="a" * 64,
        idempotency_key="pi-idem-undo-001", now="2026-08-09T10:05:00Z",
    )
    assert fingerprints() == before, (
        "proactive projection/controls/feedback must never change scheduling, "
        "permissions, values or authority state"
    )


def test_projection_is_metadata_only_no_body_or_secret():
    """Projected cards and receipts preserve no private body or credential."""
    _require_proactive()
    projection = project_proactive_state(
        events=(_delta_event("cluster-1"),),
        controls=_controls(), quiet_hours=QUIET_OFF,
        now=NOW_ACTIVE, manual_order=_manual_order(),
    )
    _assert_metadata_only(projection)
    _assert_metadata_only(projection["cards"][0])
    text = json.dumps(projection)
    for sentinel in SENTINELS:
        assert sentinel not in text, "proactive projection leaked a private sentinel"
