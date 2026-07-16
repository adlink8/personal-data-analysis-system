"""Phase 22-04: read-only product health checks for KU daily ops.

Never promotes, advances watermark, or mutates knowledge rows.

Usage::

    python -m personal_knowledge.application.knowledge.doctor_ku
    pk-ku doctor
    pk-ku doctor --json
    pk-ku doctor --skip-ports
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from personal_knowledge.core.project_paths import (
    AGENT_CONVERSATIONS_DB,
    KNOWLEDGE_ACTIVE_POINTER,
    PACKAGE_DIR,
    ROOT,
    SRC_DIR,
    UNIFIED_DB,
)

# Ports used by product REST / MCP (warn-only when down).
DEFAULT_HEALTH_ENDPOINTS: tuple[tuple[str, int, str], ...] = (
    ("rest_api", 8000, "http://127.0.0.1:8000/health"),
    ("mcp_app", 8789, "http://127.0.0.1:8789/health"),
)

CRITICAL_CHECK_IDS = frozenset(
    {
        "import_personal_knowledge",
        "unified_db",
        "active_pointer",
    }
)


@dataclass
class CheckResult:
    id: str
    ok: bool
    severity: str  # critical | warn | info
    message: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class DoctorReport:
    ok: bool
    exit_code: int
    checks: list[CheckResult] = field(default_factory=list)
    facade: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, int] = field(default_factory=dict)
    paths: dict[str, str] = field(default_factory=dict)
    note: str = (
        "read-only doctor: no promote, no watermark --write, no knowledge DELETE"
    )


def _check_import() -> CheckResult:
    try:
        import personal_knowledge  # noqa: F401

        pk_file = getattr(personal_knowledge, "__file__", None) or ""
        return CheckResult(
            id="import_personal_knowledge",
            ok=True,
            severity="critical",
            message="personal_knowledge importable",
            detail={
                "module_file": pk_file,
                "pythonpath_has_src": str(SRC_DIR) in sys.path
                or str(SRC_DIR.resolve()) in {str(Path(p).resolve()) for p in sys.path if p},
                "sys_path_head": [p for p in sys.path[:5] if p],
            },
        )
    except Exception as exc:  # noqa: BLE001 — surface any import failure
        return CheckResult(
            id="import_personal_knowledge",
            ok=False,
            severity="critical",
            message=f"cannot import personal_knowledge: {exc}",
            detail={"error": str(exc), "hint": f'Set PYTHONPATH="{SRC_DIR}"'},
        )


def _check_path_exists(
    check_id: str,
    path: Path,
    *,
    severity: str,
    label: str,
) -> CheckResult:
    exists = path.exists()
    return CheckResult(
        id=check_id,
        ok=exists,
        severity=severity,
        message=f"{label} {'present' if exists else 'MISSING'}: {path}",
        detail={"path": str(path), "exists": exists},
    )


def _check_active_pointer(pointer_path: Path) -> CheckResult:
    if not pointer_path.exists():
        return CheckResult(
            id="active_pointer",
            ok=False,
            severity="critical",
            message=f"active pointer missing: {pointer_path}",
            detail={"path": str(pointer_path), "exists": False},
        )
    try:
        raw = pointer_path.read_text(encoding="utf-8")
        name = raw.strip()
    except OSError as exc:
        return CheckResult(
            id="active_pointer",
            ok=False,
            severity="critical",
            message=f"active pointer unreadable: {exc}",
            detail={"path": str(pointer_path), "error": str(exc)},
        )
    if not name:
        return CheckResult(
            id="active_pointer",
            ok=False,
            severity="critical",
            message="active pointer is empty",
            detail={"path": str(pointer_path), "collection": ""},
        )
    return CheckResult(
        id="active_pointer",
        ok=True,
        severity="critical",
        message=f"active collection: {name}",
        detail={"path": str(pointer_path), "collection": name},
    )


def _check_watermark(
    *,
    db_path: Path,
    canonical_db: Path,
) -> CheckResult:
    """Informational: committed watermark vs current source checksum."""
    detail: dict[str, Any] = {
        "db": str(db_path),
        "canonical_db": str(canonical_db),
    }
    if not db_path.exists():
        return CheckResult(
            id="watermark",
            ok=True,  # non-critical; unified_db check already fails hard
            severity="info",
            message="watermark skipped (unified db missing)",
            detail=detail,
        )
    try:
        from personal_knowledge.application.knowledge.refresh_knowledge_units import (
            compute_source_checksum,
            get_committed_watermark,
        )

        committed = get_committed_watermark(db_path)
        current = (
            compute_source_checksum(canonical_db) if canonical_db.exists() else ""
        )
        matches = bool(committed and current and committed == current)
        detail.update(
            {
                "committed": committed,
                "current_source_checksum": current,
                "source_matches_watermark": matches,
            }
        )
        if not committed:
            msg = "no committed watermark (info)"
        elif matches:
            msg = "watermark matches current source checksum"
        else:
            msg = "watermark differs from current source (delta may be pending)"
        return CheckResult(
            id="watermark",
            ok=True,
            severity="info",
            message=msg,
            detail=detail,
        )
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            id="watermark",
            ok=True,
            severity="warn",
            message=f"watermark check failed: {exc}",
            detail={**detail, "error": str(exc)},
        )


def _tcp_listening(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_health(url: str, timeout: float = 1.5) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            body = resp.read(256).decode("utf-8", errors="replace")
            return True, f"HTTP {resp.status} {body[:80]!r}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def _check_ports(
    endpoints: tuple[tuple[str, int, str], ...] = DEFAULT_HEALTH_ENDPOINTS,
) -> list[CheckResult]:
    results: list[CheckResult] = []
    for name, port, url in endpoints:
        listening = _tcp_listening("127.0.0.1", port)
        detail: dict[str, Any] = {
            "name": name,
            "port": port,
            "url": url,
            "listening": listening,
        }
        if not listening:
            results.append(
                CheckResult(
                    id=f"port_{port}",
                    ok=True,  # warn-only: do not fail doctor
                    severity="warn",
                    message=f"{name} :{port} not listening (start services if needed)",
                    detail=detail,
                )
            )
            continue
        healthy, info = _http_health(url)
        detail["health"] = info
        detail["healthy"] = healthy
        results.append(
            CheckResult(
                id=f"port_{port}",
                ok=True,  # still warn-only even if HTTP fails
                severity="info" if healthy else "warn",
                message=(
                    f"{name} :{port} healthy"
                    if healthy
                    else f"{name} :{port} listening but health check weak: {info}"
                ),
                detail=detail,
            )
        )
    return results


_DOMAIN_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+personal_knowledge\.domains\b"
)


def scan_facade_imports(
    application_root: Path | None = None,
) -> dict[str, Any]:
    """Count ``personal_knowledge.domains`` imports under application/."""
    root = application_root or (PACKAGE_DIR / "application")
    per_file: dict[str, int] = {}
    total = 0
    if not root.is_dir():
        return {
            "total_import_lines": 0,
            "files_with_imports": 0,
            "top_files": [],
            "application_root": str(root),
            "error": "application root missing",
        }
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        count = 0
        for line in text.splitlines():
            if _DOMAIN_IMPORT_RE.search(line):
                count += 1
        if count:
            rel = path.relative_to(root).as_posix()
            per_file[rel] = count
            total += count
    ranked = sorted(per_file.items(), key=lambda kv: (-kv[1], kv[0]))
    top = [{"path": p, "count": c} for p, c in ranked[:10]]
    return {
        "total_import_lines": total,
        "files_with_imports": len(per_file),
        "top_files": top,
        "application_root": str(root),
        "retire_window": "2026-08-13",
    }


def run_doctor(
    *,
    unified_db: Path | None = None,
    conversations_db: Path | None = None,
    active_pointer: Path | None = None,
    skip_ports: bool = False,
    include_facade: bool = True,
    application_root: Path | None = None,
) -> DoctorReport:
    """Run read-only product checks. Never mutates state."""
    db = unified_db or UNIFIED_DB
    conv = conversations_db or AGENT_CONVERSATIONS_DB
    pointer = active_pointer or KNOWLEDGE_ACTIVE_POINTER

    checks: list[CheckResult] = []
    checks.append(_check_import())
    checks.append(
        _check_path_exists(
            "unified_db",
            db,
            severity="critical",
            label="UNIFIED_DB",
        )
    )
    # Conversations DB missing is warn if import/db OK — product can still run
    # with stale knowledge, but daily sync needs it. Plan: "report missing".
    # Treat as critical for product daily ops integrity.
    checks.append(
        _check_path_exists(
            "agent_conversations_db",
            conv,
            severity="critical",
            label="AGENT_CONVERSATIONS_DB",
        )
    )
    checks.append(_check_active_pointer(pointer))
    checks.append(_check_watermark(db_path=db, canonical_db=conv))

    if not skip_ports:
        checks.extend(_check_ports())

    facade: dict[str, Any] = {}
    if include_facade:
        facade = scan_facade_imports(application_root)

    critical_failed = [
        c for c in checks if c.severity == "critical" and not c.ok
    ]
    # Plan: exit 1 if active pointer missing or DB missing
    hard_fail_ids = {
        "import_personal_knowledge",
        "unified_db",
        "agent_conversations_db",
        "active_pointer",
    }
    hard_failed = [c for c in checks if c.id in hard_fail_ids and not c.ok]
    ok = not hard_failed
    exit_code = 0 if ok else 1

    summary = {
        "total": len(checks),
        "critical_ok": sum(
            1 for c in checks if c.severity == "critical" and c.ok
        ),
        "critical_fail": len(critical_failed),
        "warn": sum(1 for c in checks if c.severity == "warn"),
        "info": sum(1 for c in checks if c.severity == "info"),
    }

    return DoctorReport(
        ok=ok,
        exit_code=exit_code,
        checks=checks,
        facade=facade,
        summary=summary,
        paths={
            "root": str(ROOT),
            "src": str(SRC_DIR),
            "unified_db": str(db),
            "agent_conversations_db": str(conv),
            "active_pointer": str(pointer),
            "python": sys.executable,
            "cwd": str(Path.cwd()),
        },
    )


def report_to_dict(report: DoctorReport) -> dict[str, Any]:
    return {
        "ok": report.ok,
        "exit_code": report.exit_code,
        "note": report.note,
        "summary": report.summary,
        "paths": report.paths,
        "checks": [asdict(c) for c in report.checks],
        "facade": report.facade,
    }


def format_human(report: DoctorReport) -> str:
    lines: list[str] = [
        "pk-ku doctor (read-only)",
        "========================",
        f"status: {'OK' if report.ok else 'FAIL'}  exit={report.exit_code}",
        "",
    ]
    for c in report.checks:
        mark = "OK" if c.ok else "FAIL"
        if c.severity == "warn" and c.ok:
            mark = "WARN"
        elif c.severity == "info" and c.ok:
            mark = "INFO"
        lines.append(f"  [{mark}] {c.id}: {c.message}")
    if report.facade:
        lines.append("")
        lines.append(
            f"facade imports (application → domains): "
            f"{report.facade.get('total_import_lines', 0)} lines in "
            f"{report.facade.get('files_with_imports', 0)} files"
        )
        for item in report.facade.get("top_files") or []:
            lines.append(f"  - {item['path']}: {item['count']}")
        lines.append(
            f"  retire window: {report.facade.get('retire_window', 'n/a')}"
        )
    lines.append("")
    lines.append(report.note)
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pk-ku-doctor",
        description="Read-only KU product health checks (no promote / no write).",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Emit full JSON report only",
    )
    p.add_argument(
        "--skip-ports",
        action="store_true",
        help="Skip TCP/HTTP checks for :8000/:8789",
    )
    p.add_argument(
        "--no-facade",
        action="store_true",
        help="Skip domains facade import inventory",
    )
    p.add_argument("--db", type=Path, default=None, help="Override UNIFIED_DB")
    p.add_argument(
        "--canonical-db",
        type=Path,
        default=None,
        help="Override AGENT_CONVERSATIONS_DB",
    )
    p.add_argument(
        "--active-pointer",
        type=Path,
        default=None,
        help="Override knowledge_index_active.txt path",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run_doctor(
        unified_db=args.db,
        conversations_db=args.canonical_db,
        active_pointer=args.active_pointer,
        skip_ports=args.skip_ports,
        include_facade=not args.no_facade,
    )
    if args.json:
        print(json.dumps(report_to_dict(report), ensure_ascii=False, indent=2))
    else:
        print(format_human(report))
        # Also dump compact JSON line for scripting when not --json
        if os.environ.get("PK_KU_DOCTOR_JSON_SIDE") == "1":
            print(json.dumps(report_to_dict(report), ensure_ascii=False))
    return int(report.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
