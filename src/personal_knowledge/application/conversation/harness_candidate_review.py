"""Plan 61-08 governed Candidate review adapter (HARNESS-06).

The D-20 user review step is governed: ``accept`` / ``edit`` / ``ignore`` /
``undo`` are version-checked, explicitly confirmed where required, checksum
bound for edits, and retained as append-only feedback/receipts. No Agent
agreement or review gesture grants canonical or promotion authority
(D-19-D-22, D-25, D-26, D-28, D-29).

The ``candidate.review`` request is exactly
{candidate_id, action, expected_version, edited_payload?, edited_payload_checksum?,
 explicit_confirmation?, confirmation_token?, conflict_disposition?, feedback_id?,
 task_id, binding, idempotency_key}. ``edited_payload`` plus its SHA-256 checksum
applies only to edit; accept/edit require explicit confirmation and a
confirmation token; undo requires an existing feedback ID. A high-impact or
conflicting Candidate requires exactly one strict ``conflict_disposition`` value
from ``keep_existing`` (``保留旧结论``), ``replace_existing``
(``用新结论取代``), ``coexist_by_context`` (``按情境共存``), or
``defer_judgment`` (``暂不判断``), each safe view carrying consequence text;
missing/unknown values and every batch acceptance request reject.

Safe no-store status is one of
reviewed|duplicate|confirmation_required|stale_version|
conflict_disposition_required|rejected|outcome_unknown. Receipts carry only
receipt_id/checksum plus candidate id/checksum and an append-only feedback ID --
never a candidate/evidence body or projection content. Review never calls
promotion, rollback, watermark, active pointer, a model, or any canonical
mutation; Candidate/Evidence objects stay ``provenance_class: inference`` /
``status: candidate``. Version semantics: review starts at 1 and every
successful review advances the candidate review version by one.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from personal_knowledge.core.project_paths import ROOT

REVIEW_ACTIONS = frozenset({"accept", "edit", "ignore", "undo"})
REVIEW_OUTCOMES = frozenset({
    "reviewed",
    "duplicate",
    "confirmation_required",
    "stale_version",
    "conflict_disposition_required",
    "rejected",
    "outcome_unknown",
})
CONFLICT_DISPOSITIONS = frozenset({
    "keep_existing",
    "replace_existing",
    "coexist_by_context",
    "defer_judgment",
})
CONFLICT_DISPOSITION_LABELS = {
    "keep_existing": "保留旧结论",
    "replace_existing": "用新结论取代",
    "coexist_by_context": "按情境共存",
    "defer_judgment": "暂不判断",
}
CONFLICT_DISPOSITION_CONSEQUENCES = {
    "keep_existing": "保留旧结论：新候选仅记录为未采纳的参考，不改变当前认知。",
    "replace_existing": "用新结论取代：旧结论转入历史版本，后续投影基于新结论生成。",
    "coexist_by_context": "按情境共存：新旧结论按适用情境并存，投影时按情境选择。",
    "defer_judgment": "暂不判断：候选保持待评审状态，不进入任何投影。",
}

# A fixed default ledger location for the gateway-provider path. The adapter
# itself never discovers or writes canonical/promotion/watermark/permission/
# value state; the ledger holds only stable review identities and receipts.
DEFAULT_CANDIDATE_REVIEW_DB = ROOT / "var" / "db" / "candidate_review.sqlite"


class CandidateReviewError(Exception):
    """Fail-closed validation error with a stable machine code."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code, self.detail = code, detail


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _jsonable(value), ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    )


def _checksum(value: Any) -> str:
    """Exact Task 1 fixture formula: canonical JSON -> sha256 hex."""
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _idempotency_identity(candidate_id: str, action: str, idempotency_key: Any, feedback_id: Any) -> str:
    """Stable idempotency identity, deliberately excluding expected_version.

    Idempotency must dedupe before version validation: an exact replay with a
    stale ``expected_version`` still returns ``duplicate``.
    """
    return hashlib.sha256(json.dumps(
        {
            "candidate_id": candidate_id,
            "action": action,
            "idempotency_key": "" if idempotency_key is None else str(idempotency_key),
            "feedback_id": None if feedback_id is None else str(feedback_id),
        },
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


class HarnessCandidateReviewAdapter:
    """Metadata-only append-only review ledger guarded by validation gates.

    ``candidates`` is a mapping of candidate_id -> Candidate metadata supplied
    by the calling layer (for example the Plan 61-07 reflection ledger). The
    ledger stores only review identities, versions, checksums and receipt IDs;
    it never holds a candidate/evidence body, prompt, credential, SQL statement
    or any canonical/promotion/permission/value state.
    """

    def __init__(self, *, db_path: Path | str, candidates: Mapping[str, Any] | None = None) -> None:
        self.db_path = Path(db_path)
        self.candidates = dict(candidates or {})
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.db_path)
        try:
            con.execute(
                "CREATE TABLE IF NOT EXISTS candidate_review_state ("
                "candidate_id TEXT PRIMARY KEY,"
                "current_version INTEGER NOT NULL,"
                "created_at TEXT NOT NULL)"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS candidate_review_feedback ("
                "feedback_id TEXT PRIMARY KEY,"
                "candidate_id TEXT NOT NULL,"
                "action TEXT NOT NULL,"
                "version INTEGER NOT NULL,"
                "receipt_id TEXT NOT NULL,"
                "receipt_checksum TEXT NOT NULL,"
                "idempotency_identity TEXT NOT NULL UNIQUE,"
                "referenced_feedback_id TEXT,"
                "disposition TEXT,"
                "recorded_at TEXT NOT NULL)"
            )
            con.commit()
        finally:
            con.close()

    # ------------------------------------------------------------------
    # Ledger reads
    # ------------------------------------------------------------------

    def _current_version(self, candidate_id: str) -> int:
        con = sqlite3.connect(self.db_path)
        try:
            row = con.execute(
                "SELECT current_version FROM candidate_review_state WHERE candidate_id=?",
                (candidate_id,),
            ).fetchone()
            return int(row[0]) if row is not None else 1
        finally:
            con.close()

    def _lookup_idempotency(self, identity: str) -> dict[str, Any] | None:
        con = sqlite3.connect(self.db_path)
        try:
            row = con.execute(
                "SELECT feedback_id, action, version, receipt_id, receipt_checksum "
                "FROM candidate_review_feedback WHERE idempotency_identity=?",
                (identity,),
            ).fetchone()
            if row is None:
                return None
            return {
                "feedback_id": str(row[0]),
                "action": str(row[1]),
                "version": int(row[2]),
                "receipt_id": str(row[3]),
                "receipt_checksum": str(row[4]),
            }
        finally:
            con.close()

    def _feedback_exists(self, candidate_id: str, feedback_id: str) -> bool:
        con = sqlite3.connect(self.db_path)
        try:
            row = con.execute(
                "SELECT 1 FROM candidate_review_feedback WHERE candidate_id=? AND feedback_id=?",
                (candidate_id, feedback_id),
            ).fetchone()
            return row is not None
        finally:
            con.close()

    def feedback_history(self, candidate_id: str) -> tuple[dict[str, Any], ...]:
        """Append-only immutable reversible calibration history in review order.

        Only the reversible review gestures (``ignore``/``undo``) surface here:
        they are the entries an ``undo`` can reference and the calibration
        feedback the loop records (D-25). Confirmed accept/edit receipts are
        still bound to metadata-only ledger rows so an exact replay deduplicates
        with the same feedback id/receipt, but a confirmed accept/edit is not a
        reversible gesture and never appears in this reversible-history view.
        """
        con = sqlite3.connect(self.db_path)
        try:
            rows = con.execute(
                "SELECT feedback_id, candidate_id, action, version, receipt_id, "
                "receipt_checksum, referenced_feedback_id, disposition, recorded_at "
                "FROM candidate_review_feedback WHERE candidate_id=? "
                "AND action IN ('ignore', 'undo') ORDER BY rowid",
                (candidate_id,),
            ).fetchall()
            return tuple({
                "feedback_id": str(row[0]),
                "candidate_id": str(row[1]),
                "action": str(row[2]),
                "version": int(row[3]),
                "receipt_id": str(row[4]),
                "receipt_checksum": str(row[5]),
                "referenced_feedback_id": row[6],
                "disposition": row[7],
                "recorded_at": str(row[8]),
            } for row in rows)
        finally:
            con.close()

    # ------------------------------------------------------------------
    # Public review entry
    # ------------------------------------------------------------------

    def review(self, **request: Any) -> dict[str, Any]:
        """Review one Candidate; returns one of the declared safe no-store states.

        Never raises for a rejected/duplicate/required/stale review and never
        writes canonical/promotion/watermark/pointer/permission/value state.
        """
        try:
            return self._review(dict(request))
        except CandidateReviewError as exc:
            raw = request.get("candidate_id")
            return {
                "status": "rejected",
                "candidate_id": raw if isinstance(raw, str) else None,
                "reason": f"{exc.code}:{exc.detail}",
            }
        except Exception as exc:  # noqa: BLE001 - review must never leak an internal trace
            return {"status": "outcome_unknown", "reason": f"unexpected:{type(exc).__name__}"}

    # ------------------------------------------------------------------
    # Validation and commit
    # ------------------------------------------------------------------

    def _review(self, request: Mapping[str, Any]) -> dict[str, Any]:
        candidate_id = request.get("candidate_id")
        action = request.get("action")

        # Batch acceptance is prohibited: every Candidate is reviewed one at a time.
        if isinstance(candidate_id, (list, tuple, set, frozenset)):
            raise CandidateReviewError("batch_rejected", "each candidate is reviewed individually")
        candidate = self.candidates.get(candidate_id) if isinstance(candidate_id, str) else None
        if candidate is None:
            raise CandidateReviewError("candidate_unknown", str(candidate_id))

        if action not in REVIEW_ACTIONS:
            raise CandidateReviewError("action_unknown", str(action))

        # Idempotency dedupe precedes version validation: an exact replay returns
        # the original feedback/receipt and never appends a second entry.
        identity = _idempotency_identity(
            candidate_id, action, request.get("idempotency_key"), request.get("feedback_id")
        )
        recorded = self._lookup_idempotency(identity)
        if recorded is not None:
            return self._duplicate(candidate, recorded)

        current_version = self._current_version(candidate_id)
        expected_version = request.get("expected_version")

        if action == "undo":
            feedback_id = request.get("feedback_id")
            if not isinstance(feedback_id, str) or not feedback_id:
                raise CandidateReviewError("feedback_id_required", "undo requires an existing feedback id")
            if not self._feedback_exists(candidate_id, feedback_id):
                raise CandidateReviewError("feedback_unknown", "undo references an unknown feedback id")

        if action in ("accept", "edit"):
            confirmed = request.get("explicit_confirmation") is True
            token = request.get("confirmation_token")
            if not confirmed or not isinstance(token, str) or not token:
                return {
                    "status": "confirmation_required",
                    "candidate_id": candidate_id,
                    "action": action,
                    "expected_version": expected_version,
                    "current_version": current_version,
                }
            if action == "edit":
                payload = request.get("edited_payload")
                checksum = request.get("edited_payload_checksum")
                if not isinstance(payload, Mapping):
                    raise CandidateReviewError("edited_payload_required", "edit requires an edited_payload")
                if not isinstance(checksum, str) or not checksum:
                    raise CandidateReviewError("edited_payload_checksum_required", "edit requires its SHA-256 checksum")
                if _checksum(payload) != checksum:
                    raise CandidateReviewError("edited_payload_checksum_mismatch", "edited payload checksum mismatch")
            elif request.get("edited_payload") is not None or request.get("edited_payload_checksum") is not None:
                raise CandidateReviewError("edited_payload_only_for_edit", "edited_payload applies only to the edit action")

        # A high-impact/conflicting Candidate needs one exact strict disposition
        # before any version check so a stale-but-unresolved accept still reports
        # the required conflict state instead of a version error.
        if action in ("accept", "edit") and (bool(candidate.get("high_impact")) or bool(candidate.get("conflict_refs"))):
            disposition = request.get("conflict_disposition")
            if disposition is None:
                return {
                    "status": "conflict_disposition_required",
                    "candidate_id": candidate_id,
                    "action": action,
                    "expected_version": expected_version,
                    "current_version": current_version,
                    "disposition": self._disposition_view(),
                }
            if disposition not in CONFLICT_DISPOSITIONS:
                raise CandidateReviewError("conflict_disposition_unknown", str(disposition))
        else:
            disposition = None

        if not isinstance(expected_version, int) or isinstance(expected_version, bool) or expected_version != current_version:
            return {
                "status": "stale_version",
                "candidate_id": candidate_id,
                "action": action,
                "expected_version": expected_version,
                "current_version": current_version,
            }

        return self._commit(
            candidate=candidate,
            action=action,
            current_version=current_version,
            idempotency_key=request.get("idempotency_key"),
            referenced_feedback_id=request.get("feedback_id") if action == "undo" else None,
            disposition=disposition,
        )

    def _duplicate(self, candidate: Mapping[str, Any], recorded: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "status": "duplicate",
            "candidate_id": candidate["candidate_id"],
            "candidate_checksum": candidate["candidate_checksum"],
            "action": recorded["action"],
            "version": recorded["version"],
            "feedback_id": recorded["feedback_id"],
            "receipt": {
                "receipt_id": recorded["receipt_id"],
                "receipt_checksum": recorded["receipt_checksum"],
                "feedback_id": recorded["feedback_id"],
                "candidate_id": candidate["candidate_id"],
                "candidate_checksum": candidate["candidate_checksum"],
                "metadata_only": True,
            },
        }

    def _disposition_view(self) -> list[dict[str, str]]:
        return [
            {
                "code": code,
                "label": CONFLICT_DISPOSITION_LABELS[code],
                "consequence": CONFLICT_DISPOSITION_CONSEQUENCES[code],
            }
            for code in sorted(CONFLICT_DISPOSITIONS)
        ]

    def _commit(self, *, candidate: Mapping[str, Any], action: str, current_version: int,
                idempotency_key: Any, referenced_feedback_id: Any, disposition: Any) -> dict[str, Any]:
        candidate_id = candidate["candidate_id"]
        new_version = current_version + 1
        recorded_at = _now_utc()

        feedback_core = {
            "operation": "candidate.review",
            "candidate_id": candidate_id,
            "action": action,
            "version": new_version,
            "idempotency_key": "" if idempotency_key is None else str(idempotency_key),
            "referenced_feedback_id": referenced_feedback_id,
            "disposition": disposition,
            "recorded_at": recorded_at,
        }
        feedback_id = "feedback_" + _checksum(feedback_core)[:24]

        receipt_core = {
            "operation": "candidate.review",
            "candidate_id": candidate_id,
            "candidate_checksum": candidate["candidate_checksum"],
            "action": action,
            "version": new_version,
            "feedback_id": feedback_id,
            "metadata_only": True,
        }
        receipt_id = "review_receipt_" + _checksum(receipt_core)[:24]
        receipt_checksum = _checksum(receipt_core)

        con = sqlite3.connect(self.db_path)
        try:
            con.execute(
                "INSERT INTO candidate_review_state (candidate_id, current_version, created_at) "
                "VALUES (?,?,?) "
                "ON CONFLICT(candidate_id) DO UPDATE SET current_version=excluded.current_version",
                (candidate_id, new_version, recorded_at),
            )
            con.execute(
                "INSERT INTO candidate_review_feedback (feedback_id, candidate_id, action, version, "
                "receipt_id, receipt_checksum, idempotency_identity, referenced_feedback_id, "
                "disposition, recorded_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    feedback_id,
                    candidate_id,
                    action,
                    new_version,
                    receipt_id,
                    receipt_checksum,
                    _idempotency_identity(candidate_id, action, idempotency_key, referenced_feedback_id),
                    referenced_feedback_id,
                    disposition,
                    recorded_at,
                ),
            )
            con.commit()
        except sqlite3.Error as exc:  # transport-safe: ledger failure is not a reviewed outcome
            return {"status": "outcome_unknown", "reason": f"review_store_unavailable:{type(exc).__name__}"}
        finally:
            con.close()

        result: dict[str, Any] = {
            "status": "reviewed",
            "candidate_id": candidate_id,
            "candidate_checksum": candidate["candidate_checksum"],
            "action": action,
            "version": new_version,
            "feedback_id": feedback_id,
            "receipt": {
                "receipt_id": receipt_id,
                "receipt_checksum": receipt_checksum,
                "feedback_id": feedback_id,
                "candidate_id": candidate_id,
                "candidate_checksum": candidate["candidate_checksum"],
                "metadata_only": True,
            },
        }
        if disposition is not None:
            result["disposition_consequence"] = CONFLICT_DISPOSITION_CONSEQUENCES[disposition]
        return result


__all__ = [
    "CONFLICT_DISPOSITION_CONSEQUENCES",
    "CONFLICT_DISPOSITION_LABELS",
    "CONFLICT_DISPOSITIONS",
    "CandidateReviewError",
    "DEFAULT_CANDIDATE_REVIEW_DB",
    "HarnessCandidateReviewAdapter",
    "REVIEW_ACTIONS",
    "REVIEW_OUTCOMES",
]
