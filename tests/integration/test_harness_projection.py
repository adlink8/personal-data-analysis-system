"""Plan 61-09 Task 1 RED contract: versioned personal-model projection (HARNESS-07).

Only **confirmed accepted** versioned review state may derive a derived personal-
model projection; draft, ignored, mixed-snapshot and private Candidate content
is rejected. The read-only fixed ``personal.model_projection.get`` gateway
provider returns provenance, version, scope, valid/observed time,
confidence/uncertainty, source/snapshot/freshness binding, supporting and
conflicting evidence references/counts, conflicts, supersession, limitations
and status -- without raw Evidence bodies, drafts, ignored Candidates or any
canonical/promotion claim. A later real ``conversation.turn`` may inject only a
compatible current derived projection (the Kernel side is fixed by the Node test
``apps/personal_intelligence_kernel/test/conversation-turn.test.mjs``); stale,
unknown, conflicting, foreign-scope or mismatched-binding results are omitted
with a limitation rather than presented as truth (D-19-D-22, D-26, D-28-D-29).

This file is RED today: ``personal.model_projection.get`` is not registered in
the PiDomainGateway, so every projection expectation below fails pointing at the
missing Plan 61-09 Task 2 provider, never at a syntax error.

Implementation target (Plan 61-09 Task 2):
    src/personal_knowledge/services/pi_domain_gateway.py
      PROJECTION_GET_OPERATION = "personal.model_projection.get"
      OPERATIONS[PROJECTION_GET_OPERATION] -> {"kind": "read",
        "allowed": {"task_id", "idempotency_key", "binding", "scope"},
        "privacy": "R2"}   # capability stays a loopback header, never a field
      gateway.invoke() -> the provider branch derives ONLY from the confirmed
        accepted review state of the bound review adapter/ledger (never drafts,
        ignored Candidates, raw Evidence bodies or canonical/promotion data) and
        returns the safe projection data envelope below.
    src/personal_knowledge/intelligence/state_projection.py
      The existing normalization/validation path is the only way accepted review
      material becomes a projection; it must expose a versioned, time-aware
      surface carrying version/supersession/freshness/limitations
      (tests/unit/test_personal_state_projection.py).
    apps/personal_intelligence_kernel/src/kernel-host.mjs + server.mjs
      Fixed GET /v1/personal/model-projection -> host.getModelProjection ->
      domainBridge.invoke("personal.model_projection.get", ...) (Node test).

Safe projection data envelope (from the Plan 61-09 <interfaces> block):
    projection_id, version (>= 1), provenance_class: "inference", scope,
    valid_from / valid_to / observed_at, confidence (0..1), uncertainty,
    freshness (source_to_agentsview + agentsview_to_canonical legs),
    support_refs + support_count, conflict_refs + conflict_count, conflicts,
    supersession, limitations, status (current|uncertain|conflict|stale|
    expired|unknown|empty). Raw Evidence bodies, drafts, ignored Candidates,
    canonical/promotion claims and private fields never appear.

Fixtures are redacted and deterministic; no live data/ or var/ database and no
paid provider call is ever used.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from personal_knowledge.services.pi_domain_gateway import (  # noqa: E402
    OPERATIONS as PI_DOMAIN_OPERATIONS,
    PiDomainGateway,
)
from personal_knowledge.application.conversation.harness_reflection import (  # noqa: E402
    HarnessReflectionAdapter,
)
from personal_knowledge.application.conversation.harness_candidate_review import (  # noqa: E402
    CONFLICT_DISPOSITIONS,
    HarnessCandidateReviewAdapter,
)

PROJECTION_GET_OPERATION = "personal.model_projection.get"

# The exact declared input vocabulary from the Plan 61-09 <interfaces> block.
# ``capability`` is a loopback transport header, never a declared parameter.
PROJECTION_ALLOWED_FIELDS = frozenset({"task_id", "idempotency_key", "binding", "scope"})

# Endpoint/path/provider/authority override and private payload fields must never
# be accepted by the fixed projection provider.
PRIVATE_OVERRIDE_FIELDS = frozenset({
    "body", "content", "prompt", "completion", "credential", "secret",
    "sql", "statement", "token", "password", "path",
    "provider", "operation", "endpoint", "authority", "endpoint_override",
})

PROJECTION_STATUSES = frozenset({
    "current", "uncertain", "conflict", "stale", "expired", "unknown", "empty",
})

# Sentinel private values. If any reaches a projection response the test fails
# closed, exactly like the 61-06/61-07/61-08 privacy walkers.
SENTINELS = (
    "PRIVATE_PROJECTION_BODY_SENTINEL_4a1f2b",
    "PRIVATE_PROMPT_SENTINEL_9f3a1c",
    "PRIVATE_CREDENTIAL_SENTINEL_8a4c2d",
    "PRIVATE_SECRET_SENTINEL_1b5e7c",
)
FORBIDDEN_KEYS = (
    "body",
    "content",
    "prompt",
    "completion",
    "credential",
    "secret",
    "token",
    "password",
    "path",
    "sql",
    "query",
    "statement",
    "raw_evidence",
)


def _require_projection_registration() -> None:
    """Fail every provider test with a clear RED signal until the seam exists."""
    if PROJECTION_GET_OPERATION not in PI_DOMAIN_OPERATIONS:
        pytest.fail(
            "RED: PiDomainGateway must register personal.model_projection.get "
            "(expected for 61-09 Task 1 RED)",
            pytrace=False,
        )


def _walk_private(node: Any, path: str, errors: list[str]) -> None:
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


def _assert_metadata_only(value: Any) -> None:
    errors: list[str] = []
    _walk_private(value, "projection", errors)
    assert not errors, "projection response leaked private data: " + "; ".join(errors)


# ---------------------------------------------------------------------------
# Deterministic redacted fixtures (61-07 reflection staging and 61-08 review
# are GREEN and supply the real Candidate/review shape; the projection provider
# is the missing seam).
# ---------------------------------------------------------------------------

def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _freshness(*, statuses: tuple[str, str] = ("current", "current")) -> dict:
    legs = {}
    for name, status in zip(("source_to_agentsview", "agentsview_to_canonical"), statuses):
        legs[name] = {
            "leg": name,
            "status": status,
            "watermark": "2026-08-09T07:00:00Z" if status != "missing_watermark" else None,
            "observed_at": "2026-08-09T08:00:00Z",
            "backlog": 0,
            "limitation": f"{status}: fixture leg",
        }
    return legs


def _dispatcher_metadata(**overrides) -> dict:
    """Metadata the 61-06 dispatcher hands to its guarded staging seam."""
    canonical = _sha256("canonical:agent.conversation:projection-fixture")
    metadata = {
        "event_id": "pi_evt_" + _sha256("delta:projection:001"),
        "canonical_checksum": canonical,
        "watermark": canonical,
        "rule_version": "conversation-reflection-v1",
        "source": "pk-sync",
        "snapshot": "agentsview@" + _sha256("agentsview:sessions.db:projection-fixture"),
        "scope": "agent.conversation",
        "publication_version": "2026-08-09T09:00:00.000Z#1",
        "occurred_at": "2026-08-09T09:00:00.000Z",
        "freshness": _freshness(),
        "task_id": "task-model-projection-fixture",
        "idempotency_key": "pi-idem-projection-stage-001",
        "binding": {"scope": "agent.conversation", "role": "reflection-consumer"},
    }
    metadata.update(overrides)
    return metadata


def _candidate(tmp_path: Path, *, variant: int = 1, **overrides) -> dict:
    """Stage one real 61-07 reflection Candidate and decorate it for review."""
    seed = f"projection-variant:{variant}"
    metadata = _dispatcher_metadata(
        event_id="pi_evt_" + _sha256(f"delta:projection:{variant}"),
        canonical_checksum=_sha256(f"canonical:{seed}"),
        watermark=_sha256(f"canonical:{seed}"),
        snapshot="agentsview@" + _sha256(f"agentsview:{seed}"),
        idempotency_key=f"pi-idem-projection-stage-{variant:03d}",
    )
    result = HarnessReflectionAdapter(db_path=tmp_path / "reflection.sqlite").stage(**metadata)
    assert result["status"] == "staged", result
    candidate = dict(result["candidate"])
    candidate.update(overrides)
    return candidate


def _review_request(candidate_id: str, *, action: str = "accept", expected_version: int = 1, **overrides) -> dict:
    request = {
        "candidate_id": candidate_id,
        "action": action,
        "expected_version": expected_version,
        "task_id": "task-model-projection-review",
        "binding": {"role": "user-review", "source": "desktop"},
        "idempotency_key": "pi-idem-projection-review-001",
    }
    request.update(overrides)
    return request


def _accept(adapter: HarnessCandidateReviewAdapter, candidate: dict, *,
            action: str = "accept", disposition: str | None = None,
            variant: int = 1, edited_payload: Mapping[str, Any] | None = None) -> dict:
    """One explicitly confirmed review of a Candidate (accept/edit with token)."""
    request = _review_request(
        candidate["candidate_id"], action=action, expected_version=1,
        explicit_confirmation=True, confirmation_token="confirm-token-001",
        idempotency_key=f"pi-idem-projection-accept-{variant:03d}",
    )
    if disposition is not None:
        request["conflict_disposition"] = disposition
    if action == "edit":
        payload = dict(edited_payload or {
            "subject": candidate.get("subject", "conversation:agent.conversation"),
            "conclusion": "revised accepted conclusion",
            "confidence": 0.6,
            "valid_to": "9999-12-31T23:59:59.000Z",
        })
        request["edited_payload"] = payload
        request["edited_payload_checksum"] = _checksum(payload)
    return adapter.review(**request)


def _checksum(value: Any) -> str:
    return _sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))


def _accepted_ledger(tmp_path: Path, candidates: dict[str, dict], review_db: Path) -> HarnessCandidateReviewAdapter:
    adapter = HarnessCandidateReviewAdapter(db_path=review_db, candidates=candidates)
    for candidate in candidates.values():
        if bool(candidate.get("conflict_refs")) or bool(candidate.get("high_impact")):
            result = _accept(adapter, candidate, disposition="keep_existing")
        else:
            result = _accept(adapter, candidate)
        assert result["status"] == "reviewed", result
    return adapter


def _projection_request(scope: str, **overrides) -> dict:
    request = {
        "scope": scope,
        "task_id": "task-model-projection",
        "idempotency_key": "pi-idem-projection-001",
        "binding": {"role": "next-turn-context", "scope": scope},
    }
    request.update(overrides)
    return request


def _projection_gateway(review_adapter: HarnessCandidateReviewAdapter, review_db: Path) -> PiDomainGateway:
    """The provider reads only confirmed accepted review state from the bound
    review adapter/ledger; the projection provider branch is the 61-09 Task 2
    seam and is expected to reuse these existing constructor bindings (D-28)."""
    return PiDomainGateway(review_adapter=review_adapter, review_db=str(review_db), capability="cap")


def _derive(gateway: PiDomainGateway, scope: str, **overrides) -> dict:
    return gateway.invoke(PROJECTION_GET_OPERATION, _projection_request(scope, **overrides), capability="cap")


def _authority_fixture(tmp_path: Path):
    authority = tmp_path / "authority"
    authority.mkdir()
    files = {
        "canonical.sqlite": b"canonical-bytes",
        "active_pointer.txt": b"active-pointer-bytes",
        "watermark.json": b"{}",
        "permissions.json": b"{}",
        "values.json": b"{}",
    }
    for name, content in files.items():
        (authority / name).write_bytes(content)

    def fingerprints() -> dict:
        return {name: hashlib.sha256((authority / name).read_bytes()).hexdigest() for name in files}

    return fingerprints


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_gateway_registers_the_fixed_projection_provider():
    """The projection entry is the named read-only gateway provider, not a helper."""
    assert PROJECTION_GET_OPERATION in PI_DOMAIN_OPERATIONS, (
        "RED: PiDomainGateway must register personal.model_projection.get "
        "(expected for 61-09 Task 1 RED)"
    )
    spec = PI_DOMAIN_OPERATIONS[PROJECTION_GET_OPERATION]
    assert spec["kind"] == "read", "model projection retrieval is a read"
    missing = sorted(PROJECTION_ALLOWED_FIELDS - set(spec["allowed"]))
    assert not missing, f"RED: projection provider must accept scope/binding/task/idempotency: missing {missing}"
    extra = sorted(set(spec["allowed"]) - PROJECTION_ALLOWED_FIELDS)
    assert not extra, f"RED: projection provider must accept ONLY approved fields: unexpected {extra}"
    assert not (set(spec["allowed"]) & PRIVATE_OVERRIDE_FIELDS), (
        "personal.model_projection.get must never accept private/override fields"
    )


def test_gateway_projection_rejects_without_capability_binding_or_idempotency():
    """The gateway enforces the loopback capability and required input first."""
    _require_projection_registration()
    gateway = PiDomainGateway(capability="cap")
    request = _projection_request("agent.conversation")
    denied = gateway.invoke(PROJECTION_GET_OPERATION, request, capability="wrong")
    assert denied.get("error", {}).get("code") == "capability_invalid"
    no_binding = gateway.invoke(PROJECTION_GET_OPERATION, {**request, "binding": None}, capability="cap")
    assert no_binding.get("error", {}).get("code") == "binding_required"
    no_idem = gateway.invoke(PROJECTION_GET_OPERATION, {**request, "idempotency_key": ""}, capability="cap")
    assert no_idem.get("error", {}).get("code") == "idempotency_key_required"


def test_projection_derives_only_from_confirmed_accepted_versioned_review(tmp_path):
    """A confirmed accepted review is the only input that derives a projection."""
    _require_projection_registration()
    candidate = _candidate(tmp_path, variant=1)
    review_db = tmp_path / "review.sqlite"
    adapter = HarnessCandidateReviewAdapter(db_path=review_db, candidates={candidate["candidate_id"]: candidate})
    accepted = _accept(adapter, candidate)
    assert accepted["status"] == "reviewed" and accepted["action"] == "accept"

    result = _derive(_projection_gateway(adapter, review_db), "agent.conversation")
    assert result.get("ok") is True, result
    data = result["data"]
    assert data["projection_id"], "a confirmed accepted Candidate must derive a projection_id"
    assert data["status"] in PROJECTION_STATUSES, data["status"]
    _assert_metadata_only(data)


def test_projection_preserves_provenance_version_time_confidence_and_freshness(tmp_path):
    """The safe envelope retains every D-21/D-22 inference projection property."""
    _require_projection_registration()
    candidate = _candidate(tmp_path, variant=1)
    review_db = tmp_path / "review.sqlite"
    adapter = HarnessCandidateReviewAdapter(db_path=review_db, candidates={candidate["candidate_id"]: candidate})
    assert _accept(adapter, candidate)["status"] == "reviewed"
    gateway = _projection_gateway(adapter, review_db)

    first = _derive(gateway, "agent.conversation")
    assert first.get("ok") is True, first
    data = first["data"]
    assert isinstance(data["version"], int) and data["version"] >= 1, "projection must be versioned"
    assert data["provenance_class"] == "inference", "a projection is an inference, never a fact"
    assert data["scope"] == "agent.conversation"
    assert data["valid_from"] and data["valid_to"] and data["observed_at"], "valid/observed time must be retained"
    assert 0.0 <= float(data["confidence"]) <= 1.0
    assert data["uncertainty"], "every projection names its uncertainty"
    assert set(data["freshness"]) == {"source_to_agentsview", "agentsview_to_canonical"}, (
        "two typed freshness legs must be retained"
    )
    assert data["support_refs"] and data["support_count"] == len(data["support_refs"])
    assert data["conflict_refs"] is not None and data["conflict_count"] == len(data["conflict_refs"])
    assert "supersession" in data, "the projection records supersession"
    assert data["supersession"] is None, "a first accepted projection supersedes nothing"
    assert data["limitations"], "the projection states its limitations"
    _assert_metadata_only(data)

    # A versioned evidence-bound projection is reproducible: the same accepted
    # review state derives the same projection id/version on a second read.
    second = _derive(gateway, "agent.conversation")
    assert second["data"]["projection_id"] == data["projection_id"]
    assert second["data"]["version"] == data["version"]


def test_draft_ignored_and_undone_candidates_never_derive_projection(tmp_path):
    """Draft (unreviewed), ignored and undone candidates are never projection input."""
    _require_projection_registration()
    draft = _candidate(tmp_path, variant=2, status="candidate")
    ignored = _candidate(tmp_path, variant=3)
    candidates = {draft["candidate_id"]: draft, ignored["candidate_id"]: ignored}
    review_db = tmp_path / "review.sqlite"
    adapter = HarnessCandidateReviewAdapter(db_path=review_db, candidates=candidates)

    # Confirm-accept the draft path candidate so only "ignored" stays unaccepted.
    assert _accept(adapter, draft)["status"] == "reviewed"
    ignore_result = adapter.review(**{
        **_review_request(ignored["candidate_id"], action="ignore", expected_version=1),
        "idempotency_key": "pi-idem-projection-ignore-001",
    })
    assert ignore_result["status"] == "reviewed"
    undo_result = adapter.review(**{
        **_review_request(ignored["candidate_id"], action="undo", expected_version=2),
        "feedback_id": ignore_result["feedback_id"],
        "idempotency_key": "pi-idem-projection-undo-001",
    })
    assert undo_result["status"] == "reviewed", "undo of an ignore must be recorded"

    data = _derive(_projection_gateway(adapter, review_db), "agent.conversation")["data"]
    text = json.dumps(data)
    assert ignored["candidate_id"] not in text, "an ignored/undone Candidate must never reach a projection"
    assert data["status"] != "current", "only confirmed accepted content may present current derived context"
    _assert_metadata_only(data)

    # A scope holding nothing but draft/ignored candidates has no projection at all.
    no_accepted = _candidate(tmp_path, variant=4)
    other_db = tmp_path / "review-other.sqlite"
    other_adapter = HarnessCandidateReviewAdapter(
        db_path=other_db, candidates={no_accepted["candidate_id"]: no_accepted}
    )
    other_adapter.review(**{
        **_review_request(no_accepted["candidate_id"], action="ignore", expected_version=1),
        "idempotency_key": "pi-idem-projection-ignore-004",
    })
    empty = _derive(_projection_gateway(other_adapter, other_db), "agent.conversation")
    assert empty.get("ok") is True, empty
    empty_data = empty["data"]
    assert empty_data["status"] in {"unknown", "empty"}, (
        "draft/ignored-only content must state unknown/empty, never current"
    )
    assert empty_data["limitations"], "an empty projection states its limitation"
    _assert_metadata_only(empty_data)


def test_conflicting_and_superseding_accepted_content_stays_evidence_bound(tmp_path):
    """A newer accepted inference supersedes an older one and conflicts stay visible."""
    _require_projection_registration()
    first = _candidate(tmp_path, variant=5, subject="conversation:agent.conversation", conflict_refs=[])
    second = _candidate(
        tmp_path, variant=6, subject="conversation:agent.conversation",
        conflict_refs=["ref:conflict-projection-b"], high_impact=True,
    )
    candidates = {first["candidate_id"]: first, second["candidate_id"]: second}
    review_db = tmp_path / "review.sqlite"
    adapter = HarnessCandidateReviewAdapter(db_path=review_db, candidates=candidates)
    assert _accept(adapter, first)["status"] == "reviewed"
    assert _accept(adapter, second, disposition="replace_existing")["status"] == "reviewed"

    data = _derive(_projection_gateway(adapter, review_db), "agent.conversation")["data"]
    assert data["version"] >= 1
    assert "supersession" in data
    assert data["conflict_refs"] is not None and data["conflict_count"] >= 0
    text = json.dumps(data)
    assert first["candidate_id"] in text or data["supersession"], (
        "supersession must record the replaced accepted inference"
    )
    assert "promot" not in text and "rollback" not in text, (
        "the projection envelope must never claim authority mutation"
    )
    _assert_metadata_only(data)


def test_mixed_snapshot_and_private_content_are_rejected(tmp_path):
    """Mixed-snapshot and private Candidate content fails closed before projection."""
    _require_projection_registration()
    private = _candidate(tmp_path, variant=7)
    private["evidence"] = (
        {"ref": "agentsview.snapshot@abc", "checksum": _sha256("evidence:x"),
         "privacy_class": "R1", "serving_role": "source.agentsview",
         "artifact_version_id": "v1", "body": SENTINELS[0]},
    )
    mixed = _candidate(
        tmp_path, variant=8, snapshot_id="agentsview@foreign", snapshot_hash=_sha256("foreign:snapshot"),
    )
    candidates = {private["candidate_id"]: private, mixed["candidate_id"]: mixed}
    review_db = tmp_path / "review.sqlite"
    adapter = HarnessCandidateReviewAdapter(db_path=review_db, candidates=candidates)

    # A mixed-snapshot or private candidate must never produce a projection.
    for label, probe in (("mixed snapshot", mixed), ("private content", private)):
        result = _derive(_projection_gateway(adapter, review_db), probe["scope"], idempotency_key=f"pi-idem-{label}-001")
        if result.get("ok") is True:
            text = json.dumps(result["data"])
            assert probe["candidate_id"] not in text, f"{label} Candidate must never reach a projection"
        else:
            assert result.get("error", {}).get("code"), f"{label} rejection must state a safe code"
    _assert_metadata_only(result)


def test_unknown_scope_stale_and_foreign_results_never_present_current_truth(tmp_path):
    """Unknown/foreign scope and stale content are omitted, never stated as current."""
    _require_projection_registration()
    candidate = _candidate(tmp_path, variant=9)
    review_db = tmp_path / "review.sqlite"
    adapter = HarnessCandidateReviewAdapter(db_path=review_db, candidates={candidate["candidate_id"]: candidate})
    assert _accept(adapter, candidate)["status"] == "reviewed"
    gateway = _projection_gateway(adapter, review_db)

    unknown = _derive(gateway, "scope:not-approved", idempotency_key="pi-idem-unknown-scope-001")
    assert unknown.get("ok") is True, unknown
    assert unknown["data"]["status"] in {"unknown", "empty"}, (
        "a foreign scope must never be presented as current derived context"
    )
    assert unknown["data"]["limitations"], "a foreign scope must state its limitation"

    stale = _derive(gateway, "agent.conversation", binding={"role": "next-turn-context", "scope": "scope:foreign"},
                    idempotency_key="pi-idem-foreign-binding-001")
    if stale.get("ok") is True:
        assert stale["data"]["status"] != "current", (
            "a mismatched-binding result must never present current truth"
        )
    else:
        assert stale.get("error", {}).get("code"), "a mismatched binding must fail closed with a safe code"


def test_projection_read_never_mutates_authority_fingerprints(tmp_path):
    """Reading a projection changes no canonical/promotion/rollback/pointer state."""
    _require_projection_registration()
    candidate = _candidate(tmp_path, variant=10)
    review_db = tmp_path / "review.sqlite"
    adapter = HarnessCandidateReviewAdapter(db_path=review_db, candidates={candidate["candidate_id"]: candidate})
    assert _accept(adapter, candidate)["status"] == "reviewed"
    fingerprints = _authority_fixture(tmp_path)
    before = fingerprints()

    _derive(_projection_gateway(adapter, review_db), "agent.conversation")
    _derive(_projection_gateway(adapter, review_db), "scope:not-approved", idempotency_key="pi-idem-fp-foreign-001")

    assert fingerprints() == before, (
        "projection reads must never mutate canonical/promotion/watermark/"
        "active-pointer/permission/value state"
    )


def test_projection_contract_uses_only_declared_conflict_disposition_vocabulary():
    """The projection layer never invents dispositions outside the 61-08 enum."""
    assert CONFLICT_DISPOSITIONS == {
        "keep_existing", "replace_existing", "coexist_by_context", "defer_judgment",
    }, "projection conflict handling must reuse the existing disposition vocabulary"
