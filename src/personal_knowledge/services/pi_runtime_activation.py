"""Auditable Pi runtime mode authority; fresh state is always legacy."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODES = ("legacy", "shadow", "canary", "primary")
UPGRADES = {"legacy": {"shadow"}, "shadow": {"canary"}, "canary": {"primary"}}
DOWNGRADES = {"primary": {"canary", "shadow", "legacy"}, "canary": {"shadow", "legacy"}, "shadow": {"legacy"}, "legacy": set()}

def _now() -> str: return datetime.now(timezone.utc).isoformat()
def _checksum(value: Any) -> str: return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

class ActivationError(Exception):
    def __init__(self, code: str): super().__init__(code); self.code = code

class RuntimeActivation:
    def __init__(self, database_path: Path | str = "var/db/pi_runtime_activation.sqlite", pointer_path: Path | str | None = None, policy_path: Path | str | None = None) -> None:
        self.database_path = Path(database_path); self.database_path.parent.mkdir(parents=True, exist_ok=True); self.pointer_path = Path(pointer_path or self.database_path.with_suffix(".pointer.json"))
        self.policy_path = Path(policy_path or Path(__file__).resolve().parents[3] / "governance/manifests/ai/pi-runtime-policy.json")
        try: self.policy = json.loads(self.policy_path.read_text(encoding="utf-8"))
        except (OSError, ValueError): self.policy = {}
        self.db = sqlite3.connect(self.database_path); self.db.execute("PRAGMA foreign_keys=ON"); self.db.execute("CREATE TABLE IF NOT EXISTS activation_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, mode TEXT NOT NULL, previous_mode TEXT NOT NULL, event_checksum TEXT NOT NULL UNIQUE, actor TEXT NOT NULL, reason TEXT NOT NULL, evidence_checksum TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL)"); self.db.commit()
    def current(self) -> dict[str, Any]:
        row = self.db.execute("SELECT sequence,mode,previous_mode,event_checksum,actor,reason,evidence_checksum,created_at FROM activation_events ORDER BY sequence DESC LIMIT 1").fetchone()
        if not row: return {"mode": "legacy", "sequence": 0, "event_checksum": None}
        return {"sequence": row[0], "mode": row[1], "previous_mode": row[2], "event_checksum": row[3], "actor": row[4], "reason": row[5], "evidence_checksum": row[6], "created_at": row[7]}
    def prepare(self, target: str, *, evidence_checksum: str, actor: str = "user", reason: str = "", cohort: str = "", budget: int = 0, window: str = "", stop_conditions: tuple[str, ...] | list[str] = (), rollback_target: str = "legacy", readiness: bool = False) -> dict[str, Any]:
        current = self.current(); if_invalid = target not in MODES
        if if_invalid: raise ActivationError("mode_invalid")
        if target not in UPGRADES.get(current["mode"], set()) and target not in DOWNGRADES.get(current["mode"], set()) and target != current["mode"]: raise ActivationError("transition_illegal")
        if target in {"canary", "primary"} and self.policy.get("phase53_decision") != "proceed": raise ActivationError("phase53_decision_not_proceed")
        if target == "primary" and not readiness: raise ActivationError("primary_readiness_required")
        if rollback_target != "legacy": raise ActivationError("rollback_target_invalid")
        if target in UPGRADES.get(current["mode"], set()) and not evidence_checksum: raise ActivationError("evidence_required")
        preview = {"from": current["mode"], "to": target, "actor": actor, "reason": reason, "evidence_checksum": evidence_checksum, "cohort": cohort, "window": window, "budget": int(budget), "stop_conditions": list(stop_conditions), "rollback_target": rollback_target, "readiness": bool(readiness)}
        return {"preview": preview, "preview_checksum": _checksum(preview), "confirmation_phrase": f"CONFIRM {target.upper()} {_checksum(preview)[:12]}"}
    def confirm(self, prepared: dict[str, Any], *, confirmation_phrase: str, idempotency_key: str, actor: str = "user") -> dict[str, Any]:
        preview = prepared.get("preview") or {}; checksum = prepared.get("preview_checksum")
        if checksum != _checksum(preview) or confirmation_phrase != f"CONFIRM {preview.get('to','').upper()} {checksum[:12]}": raise ActivationError("confirmation_mismatch")
        current = self.current(); target = preview.get("to")
        if target in UPGRADES.get(current["mode"], set()) and preview.get("evidence_checksum") in {"", None, "blocked"}: raise ActivationError("evidence_required")
        event_checksum = _checksum({"preview_checksum": checksum, "idempotency_key": idempotency_key, "sequence": current["sequence"] + 1})
        old_pointer = self.pointer_path.read_bytes() if self.pointer_path.exists() else None
        temp_pointer = self.pointer_path.with_name(self.pointer_path.name + ".tmp")
        try:
            self.db.execute("BEGIN IMMEDIATE")
            self.db.execute("INSERT INTO activation_events(mode,previous_mode,event_checksum,actor,reason,evidence_checksum,idempotency_key,created_at) VALUES(?,?,?,?,?,?,?,?)", (target,current["mode"],event_checksum,actor,preview.get("reason", ""),preview.get("evidence_checksum", ""),idempotency_key,_now()))
            state = self.current()
            temp_pointer.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
            os.replace(temp_pointer, self.pointer_path)
            self.db.commit()
            return state
        except sqlite3.IntegrityError:
            self.db.rollback()
            raise ActivationError("idempotency_conflict")
        except Exception as exc:
            self.db.rollback()
            try:
                if old_pointer is None: self.pointer_path.unlink(missing_ok=True)
                else: self.pointer_path.write_bytes(old_pointer)
                temp_pointer.unlink(missing_ok=True)
            except OSError: pass
            raise ActivationError("activation_atomicity_failed") from exc
    def downgrade(self, reason: str, *, actor: str = "automatic-stop", evidence_checksum: str = "stop-condition") -> dict[str, Any]:
        current = self.current(); target = "legacy"
        if current["mode"] == target: return current
        preview = self.prepare(target, evidence_checksum=evidence_checksum, actor=actor, reason=reason)
        return self.confirm(preview, confirmation_phrase=preview["confirmation_phrase"], idempotency_key=f"downgrade:{current['sequence']+1}", actor=actor)
    def close(self) -> None: self.db.close()
