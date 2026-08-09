"""Plan 61-08 Task 1 RED contract: governed Candidate review (HARNESS-06).

The user review step (D-20) is governed: accept/edit/ignore/undo are
version-checked, explicitly confirmed where required, and retained as
append-only feedback/receipts. No Agent agreement or review gesture grants
canonical or promotion authority (D-19-D-22, D-25, D-26, D-28, D-29).

This file is RED today: the ``candidate.review`` gateway provider and the
``harness_candidate_review`` adapter do not exist yet. Every failure points at
the missing Plan 61-08 Task 2 implementation, never at a syntax error.

Implementation target (Plan 61-08 Task 2):
    src/personal_knowledge/application/conversation/harness_candidate_review.py
      REVIEW_ACTIONS                 -> frozenset({"accept","edit","ignore","undo"})
      REVIEW_OUTCOMES                -> frozenset({"reviewed","duplicate",
                                          "confirmation_required","stale_version",
                                          "conflict_disposition_required","rejected",
                                          "outcome_unknown"})
      CONFLICT_DISPOSITIONS          -> frozenset({"keep_existing","replace_existing",
                                          "coexist_by_context","defer_judgment"})
      CONFLICT_DISPOSITION_LABELS    -> {code: Chinese label}
      CONFLICT_DISPOSITION_CONSEQUENCES -> {code: consequence text}
      CandidateReviewError(code, detail)
      HarnessCandidateReviewAdapter(db_path=..., candidates=...) with .review(**request)
    src/personal_knowledge/services/pi_domain_gateway.py
      OPERATIONS["candidate.review"] -> guarded_write with the exact review shape

The ``candidate.review`` request is exactly
{candidate_id, action, expected_version, edited_payload?, edited_payload_checksum?,
 explicit_confirmation?, confirmation_token?, conflict_disposition?, feedback_id?,
 task_id, binding, idempotency_key, capability}. ``edited_payload`` plus its
SHA-256 checksum applies only to edit; accept/edit require confirmation/token;
undo requires a feedback ID. Safe no-store status is one of
reviewed|duplicate|confirmation_required|stale_version|conflict_disposition_required|
rejected|outcome_unknown, and receipts carry only IDs/checksums plus an
append-only feedback ID -- never a candidate/evidence body or projection content.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

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

try:  # RED until Plan 61-08 Task 2 creates the review adapter module.
    from personal_knowledge.application.conversation.harness_candidate_review import (  # noqa: F401
        CONFLICT_DISPOSITION_CONSEQUENCES,
        CONFLICT_DISPOSITION_LABELS,
        CONFLICT_DISPOSITIONS,
        REVIEW_ACTIONS,
        REVIEW_OUTCOMES,
        CandidateReviewError,
        HarnessCandidateReviewAdapter,
    )
    _REVIEW_AVAILABLE = True
    _REVIEW_IMPORT_ERROR = None
except (ImportError, AttributeError) as exc:  # expected RED: review adapter not implemented yet
    _REVIEW_AVAILABLE = False
    _REVIEW_IMPORT_ERROR = exc

CANDIDATE_REVIEW_OPERATION = "candidate.review"
REFLECTION_RULE_VERSION = "conversation-reflection-v1"

# The exact request shape from the Plan 61-08 interface. ``capability`` is a
# loopback transport header in the gateway, never a declared parameter.
REVIEW_ALLOWED_FIELDS = frozenset({
    "candidate_id", "action", "expected_version", "edited_payload",
    "edited_payload_checksum", "explicit_confirmation", "confirmation_token",
    "conflict_disposition", "feedback_id", "task_id", "binding", "idempotency_key",
})

PRIVATE_FIELDS = frozenset({
    "body", "content", "prompt", "completion", "credential", "secret", "sql",
    "statement", "token", "password", "path",
})

# Sentinel private value. If it reaches any review result, receipt or the review
# ledger the test fails closed, exactly like the Kernel privacy walker.
_PRIVATE_BODY = "PRIVATE_CANDIDATE_BODY_SENTINEL_6b7c9e"

EDITED_PAYLOAD = {
    "subject": "conversation:agent.conversation",
    "conclusion": "revised user conclusion",
    "confidence": 0.6,
    "valid_to": "9999-12-31T23:59:59.000Z",
}


def _require_review() -> None:
    """Fail each adapter test with a clear RED signal until the seam exists."""
    if not _REVIEW_AVAILABLE:
        pytest.fail(
            "RED: personal_knowledge.application.conversation.harness_candidate_review "
            f"missing (expected for 61-08 Task 1 RED): {_REVIEW_IMPORT_ERROR}",
            pytrace=False,
        )


def _require_gateway_registration() -> None:
    """Fail gateway tests with a clear RED signal until the provider is registered."""
    if CANDIDATE_REVIEW_OPERATION not in PI_DOMAIN_OPERATIONS:
        pytest.fail(
            "RED: PiDomainGateway must register candidate.review before the review "
            "contract can be enforced (expected for 61-08 Task 1 RED)",
            pytrace=False,
        )


# ---------------------------------------------------------------------------
# Deterministic fixtures (61-07 reflection staging is GREEN and supplies the
# real Candidate/Evidence shape; the review adapter is the missing seam).
# ---------------------------------------------------------------------------

def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _checksum(value) -> str:
    return _sha256(_canonical_json(value))


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
    canonical = _sha256("canonical:agent.conversation:fixture-v1")
    metadata = {
        "event_id": "pi_evt_" + _sha256("delta:fixture:001"),
        "canonical_checksum": canonical,
        "watermark": canonical,
        "rule_version": REFLECTION_RULE_VERSION,
        "source": "pk-sync",
        "snapshot": "agentsview@" + _sha256("agentsview:sessions.db:fixture-v1"),
        "scope": "agent.conversation",
        "publication_version": "2026-08-09T09:00:00.000Z#1",
        "occurred_at": "2026-08-09T09:00:00.000Z",
        "freshness": _freshness(),
        "task_id": "task-candidate-review-fixture",
        "idempotency_key": "pi-idem-candidate-stage-001",
        "binding": {"scope": "agent.conversation", "role": "reflection-consumer"},
    }
    metadata.update(overrides)
    return metadata


def _candidate(tmp_path, *, variant: int = 1, **overrides) -> dict:
    """Stage one real 61-07 reflection Candidate and decorate it for review."""
    seed = f"variant:{variant}"
    metadata = _dispatcher_metadata(
        event_id="pi_evt_" + _sha256(f"delta:fixture:{variant}"),
        canonical_checksum=_sha256(f"canonical:{seed}"),
        watermark=_sha256(f"canonical:{seed}"),
        snapshot="agentsview@" + _sha256(f"agentsview:{seed}"),
        idempotency_key=f"pi-idem-candidate-stage-{variant:03d}",
    )
    result = HarnessReflectionAdapter(db_path=tmp_path / "reflection.sqlite").stage(**metadata)
    assert result["status"] == "staged", result
    candidate = dict(result["candidate"])
    candidate.update(overrides)
    return candidate


def _review_request(candidate_id, *, action: str = "accept", expected_version: int = 1, **overrides) -> dict:
    request = {
        "candidate_id": candidate_id,
        "action": action,
        "expected_version": expected_version,
        "task_id": "task-candidate-review",
        "binding": {"role": "user-review", "source": "desktop"},
        "idempotency_key": "pi-idem-review-001",
    }
    request.update(overrides)
    return request


def _adapter(tmp_path, candidates: dict) -> "HarnessCandidateReviewAdapter":
    _require_review()
    return HarnessCandidateReviewAdapter(db_path=tmp_path / "review.sqlite", candidates=candidates)


def _authority_fixture(tmp_path) -> dict:
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

def test_gateway_registers_the_fixed_candidate_review_provider():
    """The review entry is the named gateway provider, not a helper."""
    assert CANDIDATE_REVIEW_OPERATION in PI_DOMAIN_OPERATIONS, (
        "RED: PiDomainGateway must register candidate.review (expected for 61-08 Task 1 RED)"
    )
    spec = PI_DOMAIN_OPERATIONS[CANDIDATE_REVIEW_OPERATION]
    assert spec["kind"] == "guarded_write", "candidate review is a guarded write"
    missing = sorted(REVIEW_ALLOWED_FIELDS - set(spec["allowed"]))
    assert not missing, f"RED: candidate.review provider must accept the review request shape: missing {missing}"
    assert not (set(spec["allowed"]) & PRIVATE_FIELDS), "candidate.review must never accept private payload fields"


def test_gateway_review_rejects_without_capability_binding_or_idempotency():
    """The gateway enforces the loopback capability before any review work."""
    _require_gateway_registration()
    gateway = PiDomainGateway(capability="cap")
    request = _review_request("cand_review_001")
    denied = gateway.invoke(CANDIDATE_REVIEW_OPERATION, request, capability="wrong")
    assert denied.get("error", {}).get("code") == "capability_invalid"
    no_binding = gateway.invoke(CANDIDATE_REVIEW_OPERATION, {**request, "binding": None}, capability="cap")
    assert no_binding.get("error", {}).get("code") == "binding_required"
    no_idem = gateway.invoke(CANDIDATE_REVIEW_OPERATION, {**request, "idempotency_key": ""}, capability="cap")
    assert no_idem.get("error", {}).get("code") == "idempotency_key_required"


def test_review_actions_and_safe_no_store_status_vocabulary(tmp_path):
    _require_review()
    assert REVIEW_ACTIONS == {"accept", "edit", "ignore", "undo"}
    assert REVIEW_OUTCOMES == {
        "reviewed", "duplicate", "confirmation_required", "stale_version",
        "conflict_disposition_required", "rejected", "outcome_unknown",
    }
    candidate = _candidate(tmp_path, variant=1)
    adapter = _adapter(tmp_path, {candidate["candidate_id"]: candidate})
    result = adapter.review(**{**_review_request(candidate["candidate_id"], action="approve", expected_version=1),
                               "idempotency_key": "pi-idem-vocab-001"})
    assert result["status"] in REVIEW_OUTCOMES, "every adapter result uses only the declared no-store statuses"
    assert result["status"] == "rejected", "an unknown action must fail closed"
    assert result.get("reason"), "a rejected review states a fail-closed reason"


def test_accept_with_confirmation_returns_reviewed_receipt_and_increments_version(tmp_path):
    _require_review()
    candidate = _candidate(tmp_path, variant=1)
    adapter = _adapter(tmp_path, {candidate["candidate_id"]: candidate})
    result = adapter.review(**_review_request(
        candidate["candidate_id"], action="accept", expected_version=1,
        explicit_confirmation=True, confirmation_token="confirm-token-001",
    ))
    assert result["status"] == "reviewed"
    assert result["candidate_id"] == candidate["candidate_id"]
    assert result["candidate_checksum"] == candidate["candidate_checksum"]
    assert result["action"] == "accept"
    assert result["version"] == 2, "a successful review advances the candidate review version"
    assert result["feedback_id"]
    receipt = result["receipt"]
    assert receipt["receipt_id"] and receipt["receipt_checksum"]
    assert receipt["feedback_id"] == result["feedback_id"], "the receipt binds the append-only feedback id"
    receipt_text = json.dumps(receipt).lower()
    for forbidden in ("evidence", "projection", "body", "payload", "prompt", "credential", "secret", "conclusion"):
        assert forbidden not in receipt_text, f"receipt leaked {forbidden}"


def test_accept_requires_explicit_confirmation_and_token(tmp_path):
    _require_review()
    candidate = _candidate(tmp_path, variant=1)
    adapter = _adapter(tmp_path, {candidate["candidate_id"]: candidate})
    base = _review_request(candidate["candidate_id"], action="accept", expected_version=1)
    no_confirm = adapter.review(**{**base, "idempotency_key": "pi-idem-confirm-none"})
    assert no_confirm["status"] == "confirmation_required", "accept without explicit confirmation must request confirmation"
    token_only = adapter.review(**{**base, "confirmation_token": "confirm-token-001",
                                   "idempotency_key": "pi-idem-confirm-token"})
    assert token_only["status"] == "confirmation_required", "explicit_confirmation=true is required even with a token"
    flag_only = adapter.review(**{**base, "explicit_confirmation": True,
                                  "idempotency_key": "pi-idem-confirm-flag"})
    assert flag_only["status"] == "confirmation_required", "a confirmation token is required even with the flag"
    assert adapter.feedback_history(candidate["candidate_id"]) == (), (
        "unconfirmed reviews must not append feedback"
    )


def test_edit_requires_payload_checksum_and_confirmation_only_for_edit(tmp_path):
    _require_review()
    candidate = _candidate(tmp_path, variant=1)
    adapter = _adapter(tmp_path, {candidate["candidate_id"]: candidate})
    base = _review_request(candidate["candidate_id"], action="edit", expected_version=1)
    mismatched = adapter.review(**{**base, "edited_payload": EDITED_PAYLOAD,
                                   "edited_payload_checksum": _sha256("different:payload"),
                                   "explicit_confirmation": True, "confirmation_token": "confirm-token-001",
                                   "idempotency_key": "pi-idem-edit-mismatch"})
    assert mismatched["status"] == "rejected", "a checksum mismatch must reject the edit"
    no_checksum = adapter.review(**{**base, "edited_payload": EDITED_PAYLOAD,
                                    "explicit_confirmation": True, "confirmation_token": "confirm-token-001",
                                    "idempotency_key": "pi-idem-edit-nochecksum"})
    assert no_checksum["status"] == "rejected", "an edit without its SHA-256 checksum must reject"
    no_payload = adapter.review(**{**base, "edited_payload_checksum": _checksum(EDITED_PAYLOAD),
                                   "explicit_confirmation": True, "confirmation_token": "confirm-token-001",
                                   "idempotency_key": "pi-idem-edit-nopayload"})
    assert no_payload["status"] == "rejected", "a checksum without an edited payload must reject"
    need_confirm = adapter.review(**{**base, "edited_payload": EDITED_PAYLOAD,
                                     "edited_payload_checksum": _checksum(EDITED_PAYLOAD),
                                     "idempotency_key": "pi-idem-edit-noconfirm"})
    assert need_confirm["status"] == "confirmation_required", "edit requires explicit confirmation like accept"
    ok = adapter.review(**{**base, "edited_payload": EDITED_PAYLOAD,
                           "edited_payload_checksum": _checksum(EDITED_PAYLOAD),
                           "explicit_confirmation": True, "confirmation_token": "confirm-token-001",
                           "idempotency_key": "pi-idem-edit-ok"})
    assert ok["status"] == "reviewed" and ok["action"] == "edit"
    wrong_action = adapter.review(**{**_review_request(candidate["candidate_id"], action="accept",
                                 expected_version=ok["version"],
                                 explicit_confirmation=True, confirmation_token="confirm-token-001"),
                                 "edited_payload": EDITED_PAYLOAD,
                                 "edited_payload_checksum": _checksum(EDITED_PAYLOAD),
                                 "idempotency_key": "pi-idem-accept-with-edit-payload"})
    assert wrong_action["status"] == "rejected", "edited_payload applies only to the edit action"


def test_stale_expected_version_reports_the_declared_safe_state(tmp_path):
    _require_review()
    candidate = _candidate(tmp_path, variant=1)
    adapter = _adapter(tmp_path, {candidate["candidate_id"]: candidate})
    first = adapter.review(**_review_request(
        candidate["candidate_id"], action="accept", expected_version=1,
        explicit_confirmation=True, confirmation_token="confirm-token-001",
        idempotency_key="pi-idem-version-001",
    ))
    assert first["status"] == "reviewed"
    stale = adapter.review(**_review_request(
        candidate["candidate_id"], action="accept", expected_version=1,
        explicit_confirmation=True, confirmation_token="confirm-token-001",
        idempotency_key="pi-idem-version-002",
    ))
    assert stale["status"] == "stale_version", "a stale expected version must not review"
    assert stale.get("current_version") == first["version"], "the safe state reports the current version"
    assert adapter.feedback_history(candidate["candidate_id"]) == (), "a stale review must not append feedback"


def test_exact_replay_is_duplicate_and_appends_nothing(tmp_path):
    _require_review()
    candidate = _candidate(tmp_path, variant=1)
    adapter = _adapter(tmp_path, {candidate["candidate_id"]: candidate})
    request = _review_request(
        candidate["candidate_id"], action="ignore", expected_version=1,
        idempotency_key="pi-idem-replay-001",
    )
    first = adapter.review(**request)
    assert first["status"] == "reviewed"
    replay = adapter.review(**request)
    assert replay["status"] == "duplicate", "an exact idempotent replay must be duplicate"
    assert replay["feedback_id"] == first["feedback_id"], "a duplicate returns the same feedback id"
    assert replay["receipt"]["receipt_checksum"] == first["receipt"]["receipt_checksum"]
    history = adapter.feedback_history(candidate["candidate_id"])
    assert len(history) == 1, "an exact replay must not append a second feedback entry"
    # idempotency is checked before version: a stale version replay still deduplicates
    stale_replay = adapter.review(**{**request, "expected_version": 99})
    assert stale_replay["status"] == "duplicate", "idempotency dedupe precedes version validation"


def test_undo_requires_an_existing_feedback_id(tmp_path):
    _require_review()
    candidate = _candidate(tmp_path, variant=1)
    adapter = _adapter(tmp_path, {candidate["candidate_id"]: candidate})
    no_feedback = adapter.review(**{**_review_request(candidate["candidate_id"], action="undo", expected_version=1),
                                    "idempotency_key": "pi-idem-undo-nofeedback"})
    assert no_feedback["status"] == "rejected", "undo without a feedback ID must reject"
    unknown = adapter.review(**{**_review_request(candidate["candidate_id"], action="undo", expected_version=1),
                                "feedback_id": "feedback_never_exists",
                                "idempotency_key": "pi-idem-undo-unknown"})
    assert unknown["status"] == "rejected", "undo of an unknown feedback must reject"
    ignore = adapter.review(**{**_review_request(candidate["candidate_id"], action="ignore", expected_version=1),
                               "idempotency_key": "pi-idem-undo-ignore"})
    assert ignore["status"] == "reviewed"
    undo = adapter.review(**{**_review_request(candidate["candidate_id"], action="undo", expected_version=2),
                             "feedback_id": ignore["feedback_id"], "idempotency_key": "pi-idem-undo-ok"})
    assert undo["status"] == "reviewed" and undo["action"] == "undo"
    assert undo["feedback_id"] != ignore["feedback_id"], "undo appends a new feedback entry"


def test_review_history_is_append_only_and_immutable(tmp_path):
    _require_review()
    candidate = _candidate(tmp_path, variant=1)
    adapter = _adapter(tmp_path, {candidate["candidate_id"]: candidate})
    ignore = adapter.review(**{**_review_request(candidate["candidate_id"], action="ignore", expected_version=1),
                               "idempotency_key": "pi-idem-hist-ignore"})
    undo = adapter.review(**{**_review_request(candidate["candidate_id"], action="undo", expected_version=2),
                             "feedback_id": ignore["feedback_id"], "idempotency_key": "pi-idem-hist-undo"})
    history = adapter.feedback_history(candidate["candidate_id"])
    assert [entry["action"] for entry in history] == ["ignore", "undo"], "history is append-only in review order"
    assert history[0]["feedback_id"] == ignore["feedback_id"]
    assert history[0]["receipt_checksum"] == ignore["receipt"]["receipt_checksum"], "history entries are immutable"
    assert history[1]["feedback_id"] == undo["feedback_id"]
    # exact replay of the undo returns duplicate without appending
    replay = adapter.review(**{**_review_request(candidate["candidate_id"], action="undo", expected_version=1),
                               "feedback_id": ignore["feedback_id"], "idempotency_key": "pi-idem-hist-undo"})
    assert replay["status"] == "duplicate"
    assert len(adapter.feedback_history(candidate["candidate_id"])) == 2, "replay must not append"


def test_conflict_disposition_enum_labels_and_consequence_text(tmp_path):
    _require_review()
    assert CONFLICT_DISPOSITIONS == {"keep_existing", "replace_existing", "coexist_by_context", "defer_judgment"}
    assert CONFLICT_DISPOSITION_LABELS == {
        "keep_existing": "保留旧结论",
        "replace_existing": "用新结论取代",
        "coexist_by_context": "按情境共存",
        "defer_judgment": "暂不判断",
    }
    for code in CONFLICT_DISPOSITIONS:
        assert CONFLICT_DISPOSITION_LABELS[code], f"{code} needs a Chinese label"
        assert CONFLICT_DISPOSITION_CONSEQUENCES.get(code), f"{code} needs consequence text"


def test_high_impact_conflict_candidate_requires_exact_disposition_and_per_option_views(tmp_path):
    _require_review()
    candidate = _candidate(tmp_path, variant=1, high_impact=True, conflict_refs=["ref:conflict-a"])
    adapter = _adapter(tmp_path, {candidate["candidate_id"]: candidate})
    base = _review_request(
        candidate["candidate_id"], action="accept", expected_version=1,
        explicit_confirmation=True, confirmation_token="confirm-token-001",
    )
    missing = adapter.review(**{**base, "idempotency_key": "pi-idem-disp-view"})
    assert missing["status"] == "conflict_disposition_required", (
        "a high-impact/conflicting Candidate must require an exact disposition"
    )
    view = missing["disposition"]
    assert {option["code"] for option in view} == CONFLICT_DISPOSITIONS, (
        "the safe preview/view model must list all four disposition options"
    )
    for option in view:
        assert option["label"] == CONFLICT_DISPOSITION_LABELS[option["code"]]
        assert option["consequence"], f"{option['code']} must carry consequence text"
    unknown = adapter.review(**{**base, "conflict_disposition": "auto_merge",
                                "idempotency_key": "pi-idem-disp-unknown"})
    assert unknown["status"] == "rejected", "an unknown disposition must fail closed"
    # each of the four exact values reviews successfully, per-item only
    version = 1
    for index, code in enumerate(sorted(CONFLICT_DISPOSITIONS), start=1):
        ok = adapter.review(**{**_review_request(candidate["candidate_id"], action="accept", expected_version=version,
                                explicit_confirmation=True, confirmation_token="confirm-token-001"),
                                "conflict_disposition": code, "idempotency_key": f"pi-idem-disp-{index:03d}"})
        assert ok["status"] == "reviewed", f"{code} must review successfully"
        assert ok.get("disposition_consequence") == CONFLICT_DISPOSITION_CONSEQUENCES[code], (
            "a successful disposition review supplies consequence text for the selected option"
        )
        version = ok["version"]
    # a missing disposition must never advance the version
    again = adapter.review(**{**base, "idempotency_key": "pi-idem-disp-again"})
    assert again["status"] == "conflict_disposition_required"


def test_batch_accept_is_forbidden_each_candidate_is_reviewed_individually(tmp_path):
    _require_review()
    candidates = {}
    for variant in (1, 2):
        candidate = _candidate(tmp_path, variant=variant, high_impact=True)
        candidates[candidate["candidate_id"]] = candidate
    adapter = _adapter(tmp_path, candidates)
    ids = sorted(candidates)
    batch = adapter.review(**{**_review_request(ids, action="accept", expected_version=1,
                             explicit_confirmation=True, confirmation_token="confirm-token-001"),
                             "conflict_disposition": "keep_existing",
                             "idempotency_key": "pi-idem-batch-accept"})
    assert batch["status"] == "rejected", "batch acceptance is prohibited; candidates are reviewed one at a time"
    for index, candidate_id in enumerate(ids, start=1):
        single = adapter.review(**{**_review_request(candidate_id, action="accept", expected_version=1,
                                explicit_confirmation=True, confirmation_token="confirm-token-001"),
                                "conflict_disposition": "keep_existing",
                                "idempotency_key": f"pi-idem-single-{index}"})
        assert single["status"] == "reviewed", "a per-item review succeeds individually"


def test_review_receipts_and_ledger_never_carry_candidate_or_evidence_body(tmp_path):
    _require_review()
    candidate = _candidate(tmp_path, variant=1)
    candidate["evidence"] = (
        {"ref": "agentsview.snapshot@abc", "checksum": _sha256("evidence:x"),
         "privacy_class": "R1", "serving_role": "source.agentsview",
         "artifact_version_id": "v1", "body": _PRIVATE_BODY},
    )
    adapter = _adapter(tmp_path, {candidate["candidate_id"]: candidate})
    result = adapter.review(**{**_review_request(candidate["candidate_id"], action="ignore", expected_version=1),
                               "idempotency_key": "pi-idem-redact-001"})
    assert result["status"] == "reviewed"
    assert _PRIVATE_BODY not in json.dumps(result), "a review result must never carry the candidate/evidence body"
    raw_ledger = (tmp_path / "review.sqlite").read_bytes()
    assert _PRIVATE_BODY.encode() not in raw_ledger, "the review ledger must be metadata-only"


def test_accept_edit_ignore_undo_preserve_candidate_and_authority_fingerprints(tmp_path):
    _require_review()
    candidate = _candidate(tmp_path, variant=1)
    candidates = {candidate["candidate_id"]: candidate}
    adapter = _adapter(tmp_path, candidates)
    fingerprints = _authority_fixture(tmp_path)
    before = fingerprints()

    version = 1
    undo_feedback = None
    steps = (
        ("accept", {"explicit_confirmation": True, "confirmation_token": "confirm-token-001"}),
        ("edit", {"edited_payload": EDITED_PAYLOAD, "edited_payload_checksum": _checksum(EDITED_PAYLOAD),
                  "explicit_confirmation": True, "confirmation_token": "confirm-token-001"}),
        ("ignore", {}),
        ("undo", {}),
    )
    for index, (action, extra) in enumerate(steps, start=1):
        if action == "undo":
            extra = {"feedback_id": undo_feedback}
        result = adapter.review(**{**_review_request(candidate["candidate_id"], action=action, expected_version=version, **extra),
                                   "idempotency_key": f"pi-idem-fp-{index}"})
        assert result["status"] == "reviewed", f"{action} must review successfully"
        if action == "ignore":
            undo_feedback = result["feedback_id"]
        version = result["version"]

    assert fingerprints() == before, (
        "accept/edit/ignore/undo must never mutate canonical/promotion/watermark/"
        "active-pointer/permission/value state"
    )
    assert candidates[candidate["candidate_id"]] == candidate, "review must preserve the Candidate/Evidence object"
    assert candidate["provenance_class"] == "inference" and candidate["status"] == "candidate", (
        "a reviewed Candidate never becomes a canonical fact by review alone"
    )
    for entry in adapter.feedback_history(candidate["candidate_id"]):
        text = json.dumps(entry)
        assert "promote" not in text and "rollback" not in text, "feedback must never claim authority mutation"
