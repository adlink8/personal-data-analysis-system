"""Auditable Pi runtime mode authority; fresh state is always legacy."""
from __future__ import annotations

import hashlib
import json
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
    def __init__(self, database_path: Path | str = "var/db/pi_runtime_activation.sqlite", pointer_path: Path | str | None = None) -> None:
        self.database_path = Path(database_path); self.database_path.parent.mkdir(parents=True, exist_ok=True); self.pointer_path = Path(pointer_path or self.database_path.with_suffix(".pointer.json"))
        self.db = sqlite3.connect(self.database_path); self.db.execute("PRAGMA foreign_keys=ON"); self.db.execute("CREATE TABLE IF NOT EXISTS activation_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, mode TEXT NOT NULL, previous_mode TEXT NOT NULL, event_checksum TEXT NOT NULL UNIQUE, actor TEXT NOT NULL, reason TEXT NOT NULL, evidence_checksum TEXT NOT NULL, idempotency_key TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL)"); self.db.commit()
    def current(self) -> dict[str, Any]:
        row = self.db.execute("SELECT sequence,mode,previous_mode,event_checksum,actor,reason,evidence_checksum,created_at FROM activation_events ORDER BY sequence DESC LIMIT 1").fetchone()
        if not row: return {"mode": "legacy", "sequence": 0, "event_checksum": None}
        return {"sequence": row[0], "mode": row[1], "previous_mode": row[2], "event_checksum": row[3], "actor": row[4], "reason": row[5], "evidence_checksum": row[6], "created_at": row[7]}
    def prepare(self, target: str, *, evidence_checksum: str, actor: str = "user", reason: str = "", cohort: str = "", budget: int = 0) -> dict[str, Any]:
        current = self.current(); if_invalid = target not in MODES
        if if_invalid: raise ActivationError("mode_invalid")
        if target not in UPGRADES.get(current["mode"], set()) and target not in DOWNGRADES.get(current["mode"], set()) and target != current["mode"]: raise ActivationError("transition_illegal")
        preview = {"from": current["mode"], "to": target, "actor": actor, "reason": reason, "evidence_checksum": evidence_checksum, "cohort": cohort, "budget": budget, "rollback_target": "legacy"}
        return {"preview": preview, "preview_checksum": _checksum(preview), "confirmation_phrase": f"CONFIRM {target.upper()} {_checksum(preview)[:12]}"}
    def confirm(self, prepared: dict[str, Any], *, confirmation_phrase: str, idempotency_key: str, actor: str = "user") -> dict[str, Any]:
        preview = prepared.get("preview") or {}; checksum = prepared.get("preview_checksum")
        if checksum != _checksum(preview) or confirmation_phrase != f"CONFIRM {preview.get('to','').upper()} {checksum[:12]}": raise ActivationError("confirmation_mismatch")
        current = self.current(); target = preview.get("to")
        if target in UPGRADES.get(current["mode"], set()) and preview.get("evidence_checksum") in {"", None, "blocked"}: raise ActivationError("evidence_required")
        event_checksum = _checksum({"preview_checksum": checksum, "idempotency_key": idempotency_key, "sequence": current["sequence"] + 1})
        try: self.db.execute("INSERT INTO activation_events(mode,previous_mode,event_checksum,actor,reason,evidence_checksum,idempotency_key,created_at) VALUES(?,?,?,?,?,?,?,?)", (target,current["mode"],event_checksum,actor,preview.get("reason", ""),preview.get("evidence_checksum", ""),idempotency_key,_now())); self.db.commit()
        except sqlite3.IntegrityError: raise ActivationError("idempotency_conflict")
        state = self.current(); self.pointer_path.write_text(json.dumps(state, sort_keys=True), encoding="utf-8"); return state
    def downgrade(self, reason: str, *, actor: str = "automatic-stop", evidence_checksum: str = "stop-condition") -> dict[str, Any]:
        current = self.current(); target = "legacy"
        if current["mode"] == target: return current
        preview = self.prepare(target, evidence_checksum=evidence_checksum, actor=actor, reason=reason)
        return self.confirm(preview, confirmation_phrase=preview["confirmation_phrase"], idempotency_key=f"downgrade:{current['sequence']+1}", actor=actor)
    def close(self) -> None: self.db.close()
