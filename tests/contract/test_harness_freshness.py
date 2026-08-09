"""Plan 61-05 Task 1 RED contract: dual-watermark harness freshness (HARNESS-04).

Two independently truthful freshness legs, never collapsed into one number:
    source -> AgentsView    (source probe + AgentsView watermark/backlog)
    AgentsView -> canonical (canonical watermark/backlog)

A scalar `current`/`complete` claim is forbidden whenever either leg lacks
proof. stale, unknown, missing watermark and nonzero backlog each carry their
own status value and a limitation string. Fixtures are deterministic
metadata-only; live data/ and var/ databases are never touched.

Implementation target (Plan 61-05 Task 2):
    src/personal_knowledge/application/conversation/harness_freshness.py
      project_freshness(*, source_probe, source_watermark, source_backlog,
                        canonical_watermark, canonical_backlog, now,
                        stale_after_seconds=3600) -> DualFreshness
      DualFreshness  frozen dataclass: .source_to_agentsview,
                     .agentsview_to_canonical, .as_of,
                     .overall_status (property), .to_dict()
      FreshnessLeg   frozen dataclass: .leg, .status, .watermark,
                     .observed_at, .backlog, .limitation, .to_dict()

Leg classification contract:
    probe missing or not ok        -> status "unknown"
    watermark is None              -> status "missing_watermark"
    backlog > 0                    -> status "backlog_pending"
    now - watermark > stale_after  -> status "stale"
    otherwise                      -> status "current"

overall_status contract:
    both legs current             -> "current"
    any leg unknown               -> "unknown"
    any leg missing_watermark     -> "missing_watermark"
    any leg backlog_pending       -> "backlog_pending"
    otherwise                     -> "stale"

Every non-current leg/overall state is never presented as "current" or
"complete". A limitation string is required and must name the state so stale,
unknown, missing watermark and backlog stay distinguishable in the UI.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from personal_knowledge.adapters.agentsview import REQUIRED_TABLES, SourceProbe  # noqa: E402

try:  # RED until Plan 61-05 Task 2 creates the module.
    from personal_knowledge.application.conversation.harness_freshness import (  # noqa: F401
        DualFreshness,
        FreshnessLeg,
        project_freshness,
    )
    _HARNESS_FRESHNESS_AVAILABLE = True
    _HARNESS_FRESHNESS_IMPORT_ERROR = None
except ModuleNotFoundError as exc:  # expected RED: module not implemented yet
    _HARNESS_FRESHNESS_AVAILABLE = False
    _HARNESS_FRESHNESS_IMPORT_ERROR = exc


def _require_freshness() -> None:
    """Fail each freshness test with a clear RED signal until the module exists."""
    if not _HARNESS_FRESHNESS_AVAILABLE:
        pytest.fail(
            "RED: src/personal_knowledge/application/conversation/harness_freshness.py "
            f"missing (expected for 61-05 Task 1 RED): {_HARNESS_FRESHNESS_IMPORT_ERROR}",
            pytrace=False,
        )


NOW = "2026-08-09T08:00:00Z"
STALE_AFTER_SECONDS = 3600


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _is_stale(watermark: str | None, now: str = NOW, stale_after_seconds: int = STALE_AFTER_SECONDS) -> bool:
    if watermark is None:
        return False
    return (_parse_ts(now) - _parse_ts(watermark)).total_seconds() > stale_after_seconds


def _probe(ok: bool = True) -> SourceProbe:
    if ok:
        return SourceProbe(
            source_path="/tmp/fixture/agentsview_sessions.db",
            integrity_check="ok",
            user_version=1,
            journal_mode="wal",
            table_count=len(REQUIRED_TABLES),
            required_tables_present=list(REQUIRED_TABLES),
            required_tables_missing=[],
            missing_columns={},
            counts={"sessions": 3, "messages": 9},
        )
    return SourceProbe(
        source_path="/tmp/fixture/agentsview_sessions.db",
        integrity_check="not ok",
        user_version=1,
        journal_mode="wal",
        table_count=0,
        required_tables_present=[],
        required_tables_missing=list(REQUIRED_TABLES),
        missing_columns={"messages": ["content"]},
        counts={},
    )


def _leg_facts(
    *,
    probe_ok: bool = True,
    watermark: str | None = "2026-08-09T07:00:00Z",
    backlog: int = 0,
) -> dict:
    """Raw leg facts the projector must classify deterministically."""
    if not probe_ok:
        return {"status": "unknown", "probe_ok": False}
    if watermark is None:
        return {"status": "missing_watermark", "probe_ok": True}
    if backlog > 0:
        return {"status": "backlog_pending", "probe_ok": True}
    if _is_stale(watermark):
        return {"status": "stale", "probe_ok": True}
    return {"status": "current", "probe_ok": True}


def _expected_overall(source_facts: dict, canonical_facts: dict) -> str:
    if source_facts["status"] == "current" and canonical_facts["status"] == "current":
        return "current"
    if "unknown" in (source_facts["status"], canonical_facts["status"]):
        return "unknown"
    if "missing_watermark" in (source_facts["status"], canonical_facts["status"]):
        return "missing_watermark"
    if "backlog_pending" in (source_facts["status"], canonical_facts["status"]):
        return "backlog_pending"
    return "stale"


def _project(source_facts: dict, canonical_facts: dict) -> object:
    """Invoke the not-yet-implemented projector with deterministic facts."""
    _require_freshness()
    source_probe = _probe(ok=source_facts.get("probe_ok", True))
    canonical_probe = _probe(ok=canonical_facts.get("probe_ok", True))
    source_watermark = "2026-08-09T07:00:00Z" if source_facts["status"] != "missing_watermark" else None
    canonical_watermark = "2026-08-09T07:00:00Z" if canonical_facts["status"] != "missing_watermark" else None
    if source_facts["status"] == "stale":
        source_watermark = "2026-08-09T06:00:00Z"
    if canonical_facts["status"] == "stale":
        canonical_watermark = "2026-08-09T06:00:00Z"
    source_backlog = 3 if source_facts["status"] == "backlog_pending" else 0
    canonical_backlog = 3 if canonical_facts["status"] == "backlog_pending" else 0
    return project_freshness(
        source_probe=source_probe,
        canonical_probe=canonical_probe,
        source_watermark=source_watermark,
        source_backlog=source_backlog,
        canonical_watermark=canonical_watermark,
        canonical_backlog=canonical_backlog,
        now=NOW,
        stale_after_seconds=STALE_AFTER_SECONDS,
    )


# Sentinel private values. If any reaches a projected freshness dict the test
# fails closed, exactly like the Kernel-side privacy walker.
SENTINELS = (
    "PRIVATE_PROMPT_SENTINEL_9f3a1c",
    "PRIVATE_TOOL_INPUT_SENTINEL_7d2b4e",
    "PRIVATE_COMPLETION_SENTINEL_3e6f0b",
    "PRIVATE_CREDENTIAL_SENTINEL_8a4c2d",
    "PRIVATE_SECRET_SENTINEL_1b5e7c",
)
FORBIDDEN_KEYS = ("body", "content", "prompt", "completion", "credential", "secret")


def _walk_private(node, path, errors):
    if node is None:
        return
    if isinstance(node, dict):
        for key, value in node.items():
            if any(fragment in key.lower() for fragment in FORBIDDEN_KEYS):
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
    _walk_private(value, "freshness", errors)
    assert not errors, "freshness projection leaked private data: " + "; ".join(errors)


def _leg(dual: object, name: str) -> FreshnessLeg:
    if name == "source_to_agentsview":
        return dual.source_to_agentsview
    return dual.agentsview_to_canonical


def _assert_leg_contract(leg: FreshnessLeg, *, leg_name: str) -> None:
    assert leg.leg == leg_name, f"leg {leg_name} must carry its own identity"
    assert leg.status in {"current", "stale", "unknown", "missing_watermark", "backlog_pending"}, f"unexpected leg status {leg.status!r}"
    assert isinstance(leg.watermark, (str, type(None)))
    assert isinstance(leg.observed_at, str) and leg.observed_at
    assert isinstance(leg.backlog, int) and leg.backlog >= 0
    assert isinstance(leg.limitation, str) and leg.limitation, "every leg needs a limitation string"
    assert leg.status != "current" or leg.limitation, "current legs may still carry a limitation"
    assert leg.status not in {"current", "complete"} or leg.backlog == 0, "a leg with backlog is never current/complete"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_two_legs_are_independent_and_typed():
    """A healthy two-leg projection returns two typed legs, never one number."""
    dual = _project({"status": "current"}, {"status": "current"})
    _assert_leg_contract(_leg(dual, "source_to_agentsview"), leg_name="source_to_agentsview")
    _assert_leg_contract(_leg(dual, "agentsview_to_canonical"), leg_name="agentsview_to_canonical")
    assert dual.overall_status == "current"
    assert dual.as_of == NOW


def test_healthy_source_probe_does_not_imply_canonical_current():
    """A healthy source leg must never upgrade a stale canonical leg."""
    dual = _project({"status": "current"}, {"status": "stale"})
    assert dual.overall_status == "stale"
    assert _leg(dual, "source_to_agentsview").status == "current"
    assert _leg(dual, "agentsview_to_canonical").status == "stale"


def test_scalar_current_is_forbidden_when_any_leg_lacks_proof():
    """Whenever either leg lacks proof the projection is never current/complete."""
    combos = [
        ({"status": "stale"}, {"status": "current"}),
        ({"status": "current"}, {"status": "stale"}),
        ({"status": "unknown", "probe_ok": False}, {"status": "current"}),
        ({"status": "current"}, {"status": "unknown", "probe_ok": False}),
        ({"status": "missing_watermark"}, {"status": "current"}),
        ({"status": "current"}, {"status": "missing_watermark"}),
        ({"status": "backlog_pending"}, {"status": "current"}),
        ({"status": "current"}, {"status": "backlog_pending"}),
        ({"status": "unknown", "probe_ok": False}, {"status": "stale"}),
        ({"status": "stale"}, {"status": "backlog_pending"}),
        ({"status": "missing_watermark"}, {"status": "unknown", "probe_ok": False}),
    ]
    for source_facts, canonical_facts in combos:
        dual = _project(source_facts, canonical_facts)
        expected = _expected_overall(source_facts, canonical_facts)
        assert dual.overall_status == expected, f"{source_facts} / {canonical_facts} -> {dual.overall_status!r}"
        assert dual.overall_status != "current", f"non-proof leg hidden: {source_facts} / {canonical_facts}"
        assert "complete" not in dual.overall_status


def test_overall_current_only_when_both_legs_current():
    """'current' overall is only legal when both legs prove current."""
    dual = _project({"status": "current"}, {"status": "current"})
    assert dual.overall_status == "current"
    payload = dual.to_dict()
    assert isinstance(payload, dict)
    assert "source_to_agentsview" in payload and "agentsview_to_canonical" in payload
    assert payload["overall_status"] == "current"


def test_stale_leg_has_own_status_and_limitation():
    """An old watermark is stale, keeps its watermark, and names staleness."""
    dual = _project({"status": "current"}, {"status": "stale"})
    canonical_leg = _leg(dual, "agentsview_to_canonical")
    assert canonical_leg.status == "stale"
    assert canonical_leg.watermark == "2026-08-09T06:00:00Z", "stale leg keeps its watermark"
    assert "stale" in canonical_leg.limitation.lower(), "stale limitation must name staleness"


def test_unknown_leg_has_own_status_and_limitation():
    """A failed source probe yields an unknown leg, never current."""
    dual = _project({"status": "unknown", "probe_ok": False}, {"status": "current"})
    source_leg = _leg(dual, "source_to_agentsview")
    assert source_leg.status == "unknown"
    assert "unknown" in source_leg.limitation.lower(), "unknown limitation must name the unknown state"


def test_missing_watermark_has_own_status_and_limitation():
    """A missing watermark is its own state, not 'current'."""
    dual = _project({"status": "current"}, {"status": "missing_watermark"})
    canonical_leg = _leg(dual, "agentsview_to_canonical")
    assert canonical_leg.status == "missing_watermark"
    assert canonical_leg.watermark is None
    assert "watermark" in canonical_leg.limitation.lower(), "missing-watermark limitation must mention watermark"


def test_nonzero_backlog_is_visible_and_never_current():
    """A pending backlog is visible, counted, and never labelled current."""
    dual = _project({"status": "current"}, {"status": "backlog_pending"})
    canonical_leg = _leg(dual, "agentsview_to_canonical")
    assert canonical_leg.status == "backlog_pending"
    assert canonical_leg.backlog == 3, "backlog count must be visible"
    assert "backlog" in canonical_leg.limitation.lower(), "backlog limitation must mention backlog"
    assert "3" in canonical_leg.limitation, "backlog limitation must carry the count"
    assert dual.overall_status == "backlog_pending"
    assert dual.overall_status != "current"


def test_all_four_states_are_distinct_statuses():
    """stale/unknown/missing_watermark/backlog_pending are four distinct statuses."""
    states = {
        _project({"status": "current"}, {"status": "stale"}).overall_status,
        _project({"status": "unknown", "probe_ok": False}, {"status": "current"}).overall_status,
        _project({"status": "missing_watermark"}, {"status": "current"}).overall_status,
        _project({"status": "current"}, {"status": "backlog_pending"}).overall_status,
    }
    assert states == {"stale", "unknown", "missing_watermark", "backlog_pending"}


def test_freshness_is_metadata_only_no_sentinels_or_forbidden_keys():
    """Projected freshness carries only safe metadata; sentinels never appear."""
    dual = _project({"status": "current"}, {"status": "current"})
    _assert_metadata_only(dual.to_dict())
    for leg_name in ("source_to_agentsview", "agentsview_to_canonical"):
        _assert_metadata_only(_leg(dual, leg_name).to_dict())
    stale = _project({"status": "current"}, {"status": "stale"})
    _assert_metadata_only(stale.to_dict())


def test_probe_failure_is_not_an_exception_but_an_unknown_leg():
    """A broken source probe must surface as a safe unknown leg, not a crash."""
    dual = _project({"status": "unknown", "probe_ok": False}, {"status": "current"})
    assert dual.overall_status == "unknown"
    _assert_metadata_only(dual.to_dict())


def test_limitation_is_a_string_for_every_state():
    """Every state carries a string limitation suitable for the UI copy contract."""
    for source_facts, canonical_facts in [
        ({"status": "current"}, {"status": "current"}),
        ({"status": "current"}, {"status": "stale"}),
        ({"status": "unknown", "probe_ok": False}, {"status": "current"}),
        ({"status": "current"}, {"status": "missing_watermark"}),
        ({"status": "current"}, {"status": "backlog_pending"}),
    ]:
        dual = _project(source_facts, canonical_facts)
        for leg in (dual.source_to_agentsview, dual.agentsview_to_canonical):
            assert isinstance(leg.limitation, str) and leg.limitation
