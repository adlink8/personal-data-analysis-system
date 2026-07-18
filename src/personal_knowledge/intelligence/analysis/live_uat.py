"""Guarded one-call product UAT for the existing ChatGPT Codex login."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from personal_knowledge.intelligence.decision.context_binding import (
    create_decision_context_binding,
)

from .executor import ExecutionReceipt, execute_analysis
from .inputs import DEFAULT_POLICY_PATH, DEFAULT_SCHEMA_PATH, ConfirmationEvent
from .providers import CodexCliProvider, codex_cli_preflight
from .schema import EvidenceReference, canonical_json, checksum, from_exact_mapping


SPEC_VERSION = "decision_analysis_live_uat_v1"
SPEC_KEYS = frozenset({
    "schema_version", "model", "personal_db", "external_db", "analysis_db",
    "goal", "constraints", "weights", "risk_budget", "personal_evidence",
    "external_evidence", "region", "max_external_age_seconds", "temperature",
    "max_output_tokens", "max_total_tokens", "timeout_seconds",
})


class LiveUatError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _fingerprint(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_live_spec(path: Path | str) -> dict[str, Any]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveUatError("live_spec_invalid") from exc
    if not isinstance(raw, dict) or set(raw) != SPEC_KEYS:
        raise LiveUatError("live_spec_shape_invalid")
    if raw.get("schema_version") != SPEC_VERSION or raw.get("risk_budget") != "low":
        raise LiveUatError("live_spec_policy_invalid")
    if raw.get("model") != "gpt-5.5":
        raise LiveUatError("live_model_not_approved", str(raw.get("model")))
    for key in ("personal_db", "external_db", "analysis_db"):
        if not Path(str(raw[key])).is_file():
            raise LiveUatError("live_authority_missing", key)
    if (not isinstance(raw.get("constraints"), list)
            or not isinstance(raw.get("weights"), dict)
            or not isinstance(raw.get("personal_evidence"), list)
            or not isinstance(raw.get("external_evidence"), list)):
        raise LiveUatError("live_spec_shape_invalid")
    return raw


def confirmation_phrase(spec: Mapping[str, Any]) -> str:
    return f"ONE_CHATGPT_CALL:{spec['model']}:{checksum(spec)}"


def run_live_uat(
    spec: Mapping[str, Any],
    *,
    confirmed_at: str,
    confirmation_event_id: str,
    confirmation: str,
    write: bool,
    working_directory: Path | str,
    provider_factory: Callable[..., CodexCliProvider] = CodexCliProvider,
) -> dict[str, Any]:
    """Execute exactly one confirmed call; never retries or executes actions."""
    if not write:
        raise LiveUatError("write_flag_required")
    expected = confirmation_phrase(spec)
    if confirmation != expected:
        raise LiveUatError("live_confirmation_mismatch")
    try:
        parsed_time = datetime.fromisoformat(confirmed_at.removesuffix("Z") + "+00:00")
    except ValueError as exc:
        raise LiveUatError("confirmation_time_invalid") from exc
    if not confirmed_at.endswith("Z") or parsed_time.utcoffset() != timezone.utc.utcoffset(parsed_time):
        raise LiveUatError("confirmation_time_invalid")

    paths = {
        "personal": Path(str(spec["personal_db"])),
        "external": Path(str(spec["external_db"])),
        "analysis": Path(str(spec["analysis_db"])),
    }
    before = {name: _fingerprint(path) for name, path in paths.items()}
    preflight = codex_cli_preflight(str(spec["model"]))
    if not preflight["ok"]:
        raise LiveUatError(str(preflight["findings"][0]))
    binding = create_decision_context_binding(
        paths["personal"], paths["external"], region=str(spec["region"]),
        max_external_age_seconds=int(spec["max_external_age_seconds"]),
        now=confirmed_at,
    )
    personal_evidence = tuple(
        from_exact_mapping(EvidenceReference, item) for item in spec["personal_evidence"]
    )
    external_evidence = tuple(
        from_exact_mapping(EvidenceReference, item) for item in spec["external_evidence"]
    )
    provider = provider_factory(
        model=str(spec["model"]), output_schema_path=DEFAULT_SCHEMA_PATH,
        working_directory=working_directory, enabled=True,
        credential_present=bool(preflight["credential_present"]), max_calls=1,
    )
    receipt: ExecutionReceipt = execute_analysis(
        provider=provider, binding=binding, personal_db_path=paths["personal"],
        external_db_path=paths["external"], analysis_db_path=paths["analysis"],
        policy_path=DEFAULT_POLICY_PATH, goal=str(spec["goal"]),
        constraints=tuple(str(item) for item in spec["constraints"]),
        weights={str(key): float(value) for key, value in spec["weights"].items()},
        risk_budget="low",
        confirmation=ConfirmationEvent(
            event_id=confirmation_event_id, confirmed_at=confirmed_at, confirmed=True,
        ),
        personal_evidence=personal_evidence, external_evidence=external_evidence,
        temperature=float(spec["temperature"]),
        max_output_tokens=int(spec["max_output_tokens"]),
        max_total_tokens=int(spec["max_total_tokens"]),
        timeout_seconds=float(spec["timeout_seconds"]), max_attempts=1,
        write=True, now=confirmed_at,
    )
    after = {name: _fingerprint(path) for name, path in paths.items()}
    source_unchanged = all(before[name] == after[name] for name in ("personal", "external"))
    successful_live_output = (
        provider.calls == 1 and receipt.stage == "publish" and receipt.run_id is not None
        and receipt.response_checksum is not None
    )
    return {
        "ok": successful_live_output and source_unchanged,
        "spec_version": SPEC_VERSION,
        "spec_checksum": checksum(spec),
        "model": spec["model"],
        "binding_hash": binding.binding_hash,
        "confirmation_event_id": confirmation_event_id,
        "provider_calls": provider.calls,
        "receipt": asdict(receipt),
        "authority_fingerprints_before": before,
        "authority_fingerprints_after": after,
        "personal_unchanged": before["personal"] == after["personal"],
        "external_unchanged": before["external"] == after["external"],
        "analysis_changed": before["analysis"] != after["analysis"],
        "actions_executed": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--confirmed-at", required=True)
    parser.add_argument("--confirmation-event-id", required=True)
    parser.add_argument("--i-confirm", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        spec = load_live_spec(args.request)
        report = run_live_uat(
            spec, confirmed_at=args.confirmed_at,
            confirmation_event_id=args.confirmation_event_id,
            confirmation=args.i_confirm, write=args.write,
            working_directory=Path.cwd(),
        )
    except Exception as exc:
        report = {"ok": False, "error": str(getattr(exc, "code", "live_uat_failed"))}
    print(canonical_json(report))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "LiveUatError", "SPEC_VERSION", "confirmation_phrase", "load_live_spec",
    "main", "run_live_uat",
]
