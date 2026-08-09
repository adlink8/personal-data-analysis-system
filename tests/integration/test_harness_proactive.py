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

from personal_knowledge.services.pi_domain_gateway import (  # noqa: E402
    OPERATIONS as PI_DOMAIN_OPERATIONS,
    PiDomainGateway,
)


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


# ---------------------------------------------------------------------------
# Plan 61-10 Task 1 RED contract: four fixed proactive Gateway providers
# (HARNESS-05, T-61-PROACTIVE-02/-03).
#
# The Kernel routes (Node test) dispatch ONLY the named providers
# proactive.state.get / proactive.controls.update / proactive.dismiss /
# proactive.dismiss.undo through the KernelHost -> PiDomainGateway boundary.
# This Python contract pins the gateway registration, the deterministic
# no-store metadata-only envelopes and the fail-closed semantics: scope is
# exactly "global" or an approved project identifier; category is exactly
# 同步/简报/反思候选; state returns active/quiet status, quiet_until, one card
# per evidence cluster with merged count and source/time/receipt/support/
# conflict refs, control state and an append-only feedback ID. Controls,
# dismiss and undo keep feedback append-only and idempotent, never reorder
# manual messages, never invoke learned scheduling and never write
# canonical/promotion/rollback/watermark/active-pointer/permission/value state
# (D-23-D-26, D-29).
#
# This section is RED today: none of the four providers are registered in the
# PiDomainGateway, so every expectation below fails pointing at the missing
# Plan 61-10 Task 2 provider wiring, never at a syntax error. The 61-07 tests
# above stay green.
#
# Implementation target (Plan 61-10 Task 2):
#   src/personal_knowledge/services/pi_domain_gateway.py
#     PROACTIVE_STATE_OPERATION    = "proactive.state.get"     (read)
#     PROACTIVE_CONTROLS_OPERATION = "proactive.controls.update" (guarded_write)
#     PROACTIVE_DISMISS_OPERATION  = "proactive.dismiss"       (guarded_write)
#     PROACTIVE_UNDO_OPERATION     = "proactive.dismiss.undo"  (guarded_write)
#     OPERATIONS[...] -> exact allowed field vocabularies below; capability is
#       the loopback header and never a declared parameter; the safe_codes list
#       gains unknown_scope / declared_category / quiet_hours_invalid /
#       dismissal_not_found so provider errors surface redacted, never crash.
#   The provider branches call only the deterministic Plan 61-07 adapter
#   functions (project_proactive_state / apply_dismissal / undo_dismissal)
#   after validating scope/category/quiet-hour/item-identity and normalize the
#   no-store metadata-only envelope below.
# ---------------------------------------------------------------------------

PROACTIVE_STATE_OPERATION = "proactive.state.get"
PROACTIVE_CONTROLS_OPERATION = "proactive.controls.update"
PROACTIVE_DISMISS_OPERATION = "proactive.dismiss"
PROACTIVE_UNDO_OPERATION = "proactive.dismiss.undo"

PROACTIVE_OPERATIONS = (
    PROACTIVE_STATE_OPERATION,
    PROACTIVE_CONTROLS_OPERATION,
    PROACTIVE_DISMISS_OPERATION,
    PROACTIVE_UNDO_OPERATION,
)

# The exact declared request vocabulary per provider (Plan 61-10 <interfaces>).
# ``capability`` stays a loopback transport header and never a declared field.
PROACTIVE_STATE_ALLOWED_FIELDS = frozenset({
    "scope", "events", "controls", "quiet_hours", "now", "manual_order",
    "task_id", "idempotency_key", "binding",
})
PROACTIVE_CONTROLS_ALLOWED_FIELDS = frozenset({
    "scope", "category", "enabled", "quiet_hours",
    "task_id", "idempotency_key", "binding",
})
PROACTIVE_DISMISS_ALLOWED_FIELDS = frozenset({
    "cluster_key", "feedback_id", "actor_identity_hash", "now", "feedback_log",
    "task_id", "idempotency_key", "binding",
})
PROACTIVE_UNDO_ALLOWED_FIELDS = frozenset({
    "dismissal_feedback_id", "feedback_id", "actor_identity_hash", "now", "feedback_log",
    "task_id", "idempotency_key", "binding",
})

# Endpoint/path/provider/authority override plus learned-scheduling/permission/
# personal-value/canonical command fields must never enter a proactive provider
# (T-61-PROACTIVE-03).
PRIVATE_PROACTIVE_FIELDS = frozenset({
    "body", "content", "prompt", "completion", "credential", "secret", "token",
    "password", "path", "sql", "statement", "raw_evidence",
    "provider", "operation", "endpoint", "authority",
    "schedule", "schedule_at", "permission", "value",
    "canonical", "promotion", "rollback", "active_pointer", "watermark",
})

# Safe fail-closed codes the providers must surface (never a crash or leak).
ERR_UNKNOWN_SCOPE = "unknown_scope"
ERR_DISMISSAL_NOT_FOUND = "dismissal_not_found"


def _require_proactive_registration() -> None:
    """Fail each 61-10 gateway test with a clear RED signal until the providers exist."""
    missing = [operation for operation in PROACTIVE_OPERATIONS if operation not in PI_DOMAIN_OPERATIONS]
    if missing:
        pytest.fail(
            "RED: PiDomainGateway must register the four proactive providers before the "
            f"61-10 contract can be enforced (expected for 61-10 Task 1 RED): missing {missing}",
            pytrace=False,
        )


def _proactive_gateway() -> PiDomainGateway:
    return PiDomainGateway(capability="cap")


def _proactive_state_request(**overrides) -> dict[str, Any]:
    """Deterministic state request through the gateway boundary (no helper call)."""
    return {
        "scope": "global",
        "events": (_delta_event("cluster-1"), _delta_event("cluster-1", ordinal=2)),
        "controls": _controls(),
        "quiet_hours": QUIET_OFF,
        "now": NOW_ACTIVE,
        "manual_order": _manual_order(),
        "task_id": "task-proactive-state",
        "idempotency_key": "pi-idem-proactive-state-001",
        "binding": "pi_kernel_proactive_state",
        **overrides,
    }


def _proactive_controls_request(**overrides) -> dict[str, Any]:
    return {
        "scope": "global",
        "category": "同步",
        "enabled": True,
        "task_id": "task-proactive-controls",
        "idempotency_key": "pi-idem-proactive-controls-001",
        "binding": "pi_kernel_proactive_controls",
        **overrides,
    }


def _proactive_dismiss_request(**overrides) -> dict[str, Any]:
    return {
        "cluster_key": "cluster-1",
        "feedback_id": "feedback_proactive_dismiss_001",
        "actor_identity_hash": "a" * 64,
        "now": "2026-08-09T10:00:00Z",
        "feedback_log": (),
        "task_id": "task-proactive-dismiss",
        "idempotency_key": "pi-idem-proactive-dismiss-001",
        "binding": "pi_kernel_proactive_dismiss",
        **overrides,
    }


def _proactive_undo_request(**overrides) -> dict[str, Any]:
    return {
        "dismissal_feedback_id": "feedback_proactive_dismiss_001",
        "feedback_id": "feedback_proactive_undo_001",
        "actor_identity_hash": "a" * 64,
        "now": "2026-08-09T10:05:00Z",
        "feedback_log": (),
        "task_id": "task-proactive-undo",
        "idempotency_key": "pi-idem-proactive-undo-001",
        "binding": "pi_kernel_proactive_undo",
        **overrides,
    }


def test_gateway_registers_the_four_fixed_proactive_providers():
    """The four proactive entries are named gateway providers with exact vocabularies."""
    specs = {
        PROACTIVE_STATE_OPERATION: ("read", PROACTIVE_STATE_ALLOWED_FIELDS),
        PROACTIVE_CONTROLS_OPERATION: ("guarded_write", PROACTIVE_CONTROLS_ALLOWED_FIELDS),
        PROACTIVE_DISMISS_OPERATION: ("guarded_write", PROACTIVE_DISMISS_ALLOWED_FIELDS),
        PROACTIVE_UNDO_OPERATION: ("guarded_write", PROACTIVE_UNDO_ALLOWED_FIELDS),
    }
    for operation, (kind, allowed) in specs.items():
        assert operation in PI_DOMAIN_OPERATIONS, (
            f"RED: PiDomainGateway must register {operation} (expected for 61-10 Task 1 RED)"
        )
        spec = PI_DOMAIN_OPERATIONS[operation]
        assert spec["kind"] == kind, f"{operation} must be a {kind} provider"
        missing = sorted(allowed - set(spec["allowed"]))
        assert not missing, (
            f"RED: {operation} provider must accept its declared request shape: missing {missing}"
        )
        assert not (set(spec["allowed"]) & PRIVATE_PROACTIVE_FIELDS), (
            f"{operation} must never accept private/override/schedule/permission/canonical fields"
        )


def test_gateway_proactive_rejects_without_capability_binding_or_idempotency():
    """The gateway enforces the loopback capability before any proactive work."""
    _require_proactive_registration()
    gateway = _proactive_gateway()
    request = _proactive_state_request()
    denied = gateway.invoke(PROACTIVE_STATE_OPERATION, request, capability="wrong")
    assert denied.get("error", {}).get("code") == "capability_invalid"
    no_binding = gateway.invoke(PROACTIVE_STATE_OPERATION, {**request, "binding": None}, capability="cap")
    assert no_binding.get("error", {}).get("code") == "binding_required"
    no_idem = gateway.invoke(PROACTIVE_STATE_OPERATION, {**request, "idempotency_key": ""}, capability="cap")
    assert no_idem.get("error", {}).get("code") == "idempotency_key_required"
    undeclared = gateway.invoke(PROACTIVE_STATE_OPERATION, {**request, "provider": "model.wake"}, capability="cap")
    assert undeclared.get("error", {}).get("code") == "undeclared_input"


def test_gateway_state_returns_deterministic_quiet_global_project_category_cluster_metadata():
    """State through the gateway keeps active/quiet, one-card-per-cluster, control state and feedback id."""
    _require_proactive_registration()
    gateway = _proactive_gateway()
    manual = _manual_order(3)
    result = gateway.invoke(
        PROACTIVE_STATE_OPERATION, _proactive_state_request(manual_order=manual), capability="cap",
    )
    assert result["ok"] is True, result
    data = result["data"]
    assert data["active"] is True
    assert data["quiet_until"] is None
    cards = [card for card in data["cards"] if card["cluster_key"] == "cluster-1"]
    assert len(cards) == 1, "one evidence cluster must yield exactly one card"
    card = cards[0]
    assert card["merged_count"] == 2
    merged = card["merged_evidence"]
    assert len(merged) == 2, "merged drilldown lists every merged evidence source/time/receipt"
    for item in merged:
        assert item["source"] and item["occurred_at"] and item["receipt_checksum"]
        assert item["support_refs"] and item["conflict_refs"]
    assert tuple(data["manual_order"]) == manual, "manual message order must be preserved"
    assert data.get("metadata_only") is True
    assert data.get("feedback", {}).get("feedback_id"), "the state envelope carries the append-only feedback id"
    _assert_metadata_only(data)

    quiet = gateway.invoke(
        PROACTIVE_STATE_OPERATION,
        _proactive_state_request(quiet_hours=QUIET_HOURS, now=NOW_QUIET),
        capability="cap",
    )
    assert quiet["data"]["active"] is False
    assert quiet["data"]["quiet_until"] == "07:00", "quiet window must expose quiet_until without scheduling"

    project = gateway.invoke(
        PROACTIVE_STATE_OPERATION,
        _proactive_state_request(
            scope="project:alpha",
            events=(_delta_event("cluster-alpha", scope="project:alpha", category="简报"),),
        ),
        capability="cap",
    )
    keys = {card["cluster_key"] for card in project["data"]["cards"]}
    assert "cluster-alpha" in keys, "an approved project scope card must project"
    assert project["data"]["cards"][0]["scope"] == "project:alpha"
    assert project["data"]["cards"][0]["category"] == "简报"


def test_gateway_state_rejects_foreign_scope_undeclared_category_and_malformed_quiet_hours():
    """Scope, category and quiet hours are exact and fail closed at the provider boundary."""
    _require_proactive_registration()
    gateway = _proactive_gateway()
    foreign = gateway.invoke(
        PROACTIVE_STATE_OPERATION, _proactive_state_request(scope="scope:not-approved"), capability="cap",
    )
    assert foreign["ok"] is False
    assert foreign.get("error", {}).get("code") == ERR_UNKNOWN_SCOPE, foreign

    unknown_category = gateway.invoke(
        PROACTIVE_STATE_OPERATION,
        _proactive_state_request(events=(_delta_event("cluster-1", category="autonomous"),)),
        capability="cap",
    )
    assert unknown_category["ok"] is False
    assert unknown_category.get("error", {}).get("code") == ERR_UNDECLARED_CATEGORY, unknown_category

    malformed = gateway.invoke(
        PROACTIVE_STATE_OPERATION,
        _proactive_state_request(quiet_hours={"enabled": True, "start": "25:00", "end": "07:00"}),
        capability="cap",
    )
    assert malformed["ok"] is False
    assert malformed.get("error", {}).get("code") == ERR_QUIET_HOURS_INVALID, malformed


def test_gateway_controls_update_returns_control_state_and_rejects_unknown_category_and_quiet_shape():
    """Controls update is a bounded metadata envelope and validates category/quiet hours exactly."""
    _require_proactive_registration()
    gateway = _proactive_gateway()
    ok = gateway.invoke(PROACTIVE_CONTROLS_OPERATION, _proactive_controls_request(), capability="cap")
    assert ok["ok"] is True, ok
    data = ok["data"]
    assert data.get("scope") == "global"
    assert data.get("category") == "同步"
    assert data.get("enabled") is True
    assert data.get("metadata_only") is True
    assert data.get("feedback", {}).get("feedback_id"), "the controls envelope carries the append-only feedback id"
    _assert_metadata_only(data)

    unknown_category = gateway.invoke(
        PROACTIVE_CONTROLS_OPERATION, _proactive_controls_request(category="autonomous"), capability="cap",
    )
    assert unknown_category["ok"] is False
    assert unknown_category.get("error", {}).get("code") == ERR_UNDECLARED_CATEGORY, unknown_category

    malformed = gateway.invoke(
        PROACTIVE_CONTROLS_OPERATION,
        _proactive_controls_request(quiet_hours={"enabled": True}),
        capability="cap",
    )
    assert malformed["ok"] is False
    assert malformed.get("error", {}).get("code") == ERR_QUIET_HOURS_INVALID, malformed


def test_gateway_dismiss_is_append_only_and_exactly_idempotent():
    """Dismiss appends exactly one feedback entry through the gateway; an exact retry appends nothing."""
    _require_proactive_registration()
    gateway = _proactive_gateway()
    first = gateway.invoke(PROACTIVE_DISMISS_OPERATION, _proactive_dismiss_request(), capability="cap")
    assert first["ok"] is True, first
    data = first["data"]
    assert data.get("operation") == "dismiss"
    assert data.get("existing") is False
    log = data.get("feedback_log")
    assert len(log) == 1, "dismiss appends exactly one feedback entry"
    assert data.get("feedback_count") == 1
    assert data.get("metadata_only") is True
    _assert_metadata_only(first)

    replay = gateway.invoke(
        PROACTIVE_DISMISS_OPERATION, _proactive_dismiss_request(feedback_log=log), capability="cap",
    )
    assert replay["ok"] is True, replay
    assert replay["data"].get("existing") is True, "an exact idempotent dismissal must not append twice"
    assert len(replay["data"].get("feedback_log")) == 1
    assert replay["data"]["receipt"]["feedback_id"] == data["receipt"]["feedback_id"]


def test_gateway_undo_appends_new_entry_and_never_mutates_the_dismissal():
    """Undo through the gateway appends a new entry and preserves the original dismissal immutably."""
    _require_proactive_registration()
    gateway = _proactive_gateway()
    dismissed = gateway.invoke(PROACTIVE_DISMISS_OPERATION, _proactive_dismiss_request(), capability="cap")
    log = dismissed["data"]["feedback_log"]
    original = log[0]

    undone = gateway.invoke(
        PROACTIVE_UNDO_OPERATION, _proactive_undo_request(feedback_log=log), capability="cap",
    )
    assert undone["ok"] is True, undone
    log = undone["data"]["feedback_log"]
    assert len(log) == 2, "undo appends a new feedback entry"
    assert log[0] == original, "undo must never mutate or delete the dismissal entry"
    assert log[1]["operation"] == "undo_dismissal"
    assert log[1]["dismissal_feedback_id"] == "feedback_proactive_dismiss_001"
    assert undone["data"].get("metadata_only") is True
    _assert_metadata_only(undone)

    missing = gateway.invoke(
        PROACTIVE_UNDO_OPERATION,
        _proactive_undo_request(dismissal_feedback_id="feedback_never_exists"),
        capability="cap",
    )
    assert missing["ok"] is False
    assert missing.get("error", {}).get("code") == ERR_DISMISSAL_NOT_FOUND, missing


def test_proactive_gateway_never_writes_authority_or_invokes_learned_scheduling(tmp_path):
    """State/controls/dismiss/undo through the gateway never mutate authority state."""
    _require_proactive_registration()
    gateway = _proactive_gateway()
    authority = tmp_path / "authority"
    authority.mkdir()
    files = {
        "canonical.sqlite": b"canonical-bytes",
        "active_pointer.txt": b"pointer-bytes",
        "watermark.json": b"{}",
        "schedule.json": b"{}",
        "permissions.json": b"{}",
        "values.json": b"{}",
    }
    for name, content in files.items():
        (authority / name).write_bytes(content)

    def fingerprints() -> dict[str, str]:
        return {name: hashlib.sha256((authority / name).read_bytes()).hexdigest() for name in files}

    before = fingerprints()
    gateway.invoke(PROACTIVE_STATE_OPERATION, _proactive_state_request(), capability="cap")
    gateway.invoke(PROACTIVE_CONTROLS_OPERATION, _proactive_controls_request(), capability="cap")
    dismissed = gateway.invoke(PROACTIVE_DISMISS_OPERATION, _proactive_dismiss_request(), capability="cap")
    gateway.invoke(
        PROACTIVE_UNDO_OPERATION,
        _proactive_undo_request(feedback_log=dismissed["data"]["feedback_log"]),
        capability="cap",
    )
    assert fingerprints() == before, (
        "proactive state/controls/dismiss/undo must never change scheduling, permissions, values, "
        "canonical, promotion/rollback, watermark or active-pointer state"
    )


def test_proactive_error_envelopes_are_redacted_and_no_store_metadata_only():
    """Every rejection and success envelope is safe, redacted and carries no authority claim."""
    _require_proactive_registration()
    gateway = _proactive_gateway()
    responses = [
        gateway.invoke(
            PROACTIVE_STATE_OPERATION, _proactive_state_request(scope="scope:not-approved"), capability="cap",
        ),
        gateway.invoke(
            PROACTIVE_STATE_OPERATION,
            _proactive_state_request(quiet_hours={"enabled": True, "start": "25:00", "end": "07:00"}),
            capability="cap",
        ),
        gateway.invoke(
            PROACTIVE_CONTROLS_OPERATION, _proactive_controls_request(category="autonomous"), capability="cap",
        ),
        gateway.invoke(PROACTIVE_DISMISS_OPERATION, _proactive_dismiss_request(), capability="cap"),
        gateway.invoke(
            PROACTIVE_UNDO_OPERATION,
            _proactive_undo_request(dismissal_feedback_id="feedback_never_exists"),
            capability="cap",
        ),
    ]
    for response in responses:
        text = json.dumps(response)
        for sentinel in SENTINELS:
            assert sentinel not in text, "proactive envelope leaked a private sentinel"
        assert "promote" not in text and "rollback" not in text, "proactive envelope must never claim authority mutation"
        _assert_metadata_only(response)
