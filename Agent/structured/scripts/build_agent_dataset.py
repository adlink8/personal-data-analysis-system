from __future__ import annotations

import csv
import hashlib
import json
import os
import shlex
import shutil
import sqlite3
import subprocess
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
AGENT = ROOT / "Agent"
RAW = AGENT / "原始数据"
STRUCTURED_ROOT = AGENT / "结构化数据"
ANALYSIS_ROOT = AGENT / "分析数据"
IDX = STRUCTURED_ROOT / "原始数据索引"
DETAILS = STRUCTURED_ROOT / "明细数据"
REPORTS = ANALYSIS_ROOT / "报告HTML"
DB_DIR = STRUCTURED_ROOT / "SQLite数据库"
BY_SOURCE = STRUCTURED_ROOT / "按来源分类"
BY_TYPE = STRUCTURED_ROOT / "按数据类型分类"
SCRIPTS = STRUCTURED_ROOT / "脚本"
WORK = ANALYSIS_ROOT / "旧工作文件"
DB = DB_DIR / "agent_data.sqlite"

HOME = Path.home()

SOURCE_ROOTS = [
    ("Codex", HOME / ".codex"),
    ("Claude", HOME / ".claude"),
    ("Claude_Home_Config", HOME / ".claude.json"),
    ("Cline", HOME / ".cline"),
    ("Cursor", HOME / ".cursor"),
    ("Gemini", HOME / ".gemini"),
    ("Cagent", HOME / ".cagent"),
    ("Ollama", HOME / ".ollama"),
    ("Codex_Roaming", HOME / "AppData" / "Roaming" / "Codex"),
    ("Claude_Roaming", HOME / "AppData" / "Roaming" / "Claude"),
    ("Codex_Local", HOME / "AppData" / "Local" / "Codex"),
    ("Claude_Local", HOME / "AppData" / "Local" / "Claude"),
    ("Claude3p_Local", HOME / "AppData" / "Local" / "Claude-3p"),
    ("AnthropicClaude_Local", HOME / "AppData" / "Local" / "AnthropicClaude"),
    ("ClaudeCli_Local", HOME / "AppData" / "Local" / "claude-cli-nodejs"),
    ("OpenAI_Local", HOME / "AppData" / "Local" / "OpenAI"),
    ("Agents", HOME / ".agents"),
    ("WorkBuddy", HOME / ".workbuddy"),
    ("WorkBuddy_Home", HOME / "WorkBuddy"),
    ("WorkBuddy_Roaming", HOME / "AppData" / "Roaming" / "WorkBuddy"),
    ("WorkBuddy_Local", HOME / "AppData" / "Local" / "WorkBuddy"),
    ("WorkBuddyExtension_Local", HOME / "AppData" / "Local" / "WorkBuddyExtension"),
    ("Hermes", HOME / ".hermes"),
    ("Hermes_Roaming", HOME / "AppData" / "Roaming" / "Hermes"),
    ("Hermes_Local", HOME / "AppData" / "Local" / "hermes"),
    ("HermesSetup_Local", HOME / "AppData" / "Local" / "com.nousresearch.hermes.setup"),
    ("Documents_Codex", HOME / "Documents" / "Codex"),
    ("Documents_Cline", HOME / "Documents" / "Cline"),
]

WSL_ARCHIVE_SOURCES = [
    {
        "source": "WSL_UbuntuD_AgentArchive",
        "distro": "Ubuntu-D",
        "home": "/home/li",
        "items": [
            ".codex",
            ".claude",
            ".claude.json",
            ".gemini",
            ".hermes",
            ".codebuddy",
            ".codebuddy.json",
            ".copilot",
            ".ollama",
        ],
    }
]

INCLUDE_DIRS = {
    "Codex": [
        "sessions",
        "archived_sessions",
        "memories",
        "skills",
        "agents",
        "rules",
        "hooks",
    ],
    "Claude": [
        "agents",
        "commands",
        "debug",
        "file-history",
        "get-shit-done",
        "hooks",
        "output-styles",
        "plans",
        "projects",
        "session-env",
        "sessions",
        "shell-snapshots",
        "skills",
        "tasks",
        "todos",
    ],
    "Cline": ["data", "Hooks", "Rules", "Workflows"],
    "Cursor": ["ai-tracking", "projects", "skills-cursor"],
    "Gemini": ["antigravity", "antigravity-backup", "antigravity-ide", "config", "history"],
    "Cagent": ["store"],
    "Ollama": [],
    "Agents": ["skills"],
    "WorkBuddy": [
        "sessions",
        "memory",
        "memery",
        "skills",
        "plans",
        "tasks",
        "todos",
        "projects",
        "file-history",
        "artifact-index",
        "media-index",
    ],
    "Hermes_Local": [
        "skills",
        "sessions",
        "memory",
        "memories",
        "plans",
        "tasks",
    ],
    "Hermes": ["cron", "logs", "memories", "sessions", "skills"],
    "Documents_Codex": [],
    "Documents_Cline": ["Hooks", "Rules", "Workflows"],
    "WSL_UbuntuD_Codex": [
        "sessions",
        "memories",
        "skills",
        "rules",
        "shell_snapshots",
        "log",
    ],
    "WSL_UbuntuD_Claude": [
        "agents",
        "commands",
        "debug",
        "file-history",
        "hooks",
        "plans",
        "projects",
        "session-env",
        "sessions",
        "shell-snapshots",
        "skills",
        "tasks",
        "todos",
    ],
    "WSL_UbuntuD_Gemini": ["history"],
    "WSL_UbuntuD_Hermes": ["cron", "logs", "memories", "sessions", "skills"],
    "WSL_UbuntuD_CodeBuddy": [],
    "WSL_UbuntuD_Copilot": [],
}

INCLUDE_EXTS = {
    ".json",
    ".jsonl",
    ".md",
    ".txt",
    ".toml",
    ".yaml",
    ".yml",
    ".csv",
    ".sqlite",
    ".db",
    ".log",
}

EXCLUDE_DIR_PARTS = {
    "node_modules",
    "cache",
    ".cache",
    "vendor",
    "binaries",
    "blobs",
    "plugins",
    "plugins-marketplace",
    "extensions",
    "connectors-marketplace",
    "clipboard-images",
    "generated_images",
    ".sandbox",
    ".tmp",
    "tmp",
    "worktrees",
    "leveldb_tmp",
    "leveldb_copy",
    ".git",
    "target",
    "dist",
    "build",
    "__pycache__",
}

ARCHIVE_EXCLUDES = [
    "*/node_modules/*",
    "*/cache/*",
    "*/.cache/*",
    "*/tmp/*",
    "*/.tmp/*",
    "*/vendor/*",
    "*/bin/*",
    "*/platforms/*",
    "*/sandboxes/*",
    "*/models/blobs/*",
    "*/models/manifests/*",
    "*/target/*",
    "*/dist/*",
    "*/build/*",
    "*/.git/*",
    "*/auth.json",
    "*credentials*",
    "*credential*",
    "*secret*",
    "*token*",
    "*oauth*",
    "*.env",
    "*id_ed25519*",
]

SECRET_NAME_PARTS = {
    "auth",
    "credential",
    "credentials",
    "secret",
    "token",
    "key",
    "oauth",
    "id_ed25519",
    ".env",
    "cap_sid",
}

TOP_LEVEL_FILES = {
    ".codex-global-state.json",
    "history.jsonl",
    "session_index.jsonl",
    "AGENTS.md",
    "config.toml",
    "config.json",
    "settings.json",
    "settings.local.json",
    "stats-cache.json",
    "models_cache.json",
    "external_agent_session_imports.json",
    "goals_1.sqlite",
    "logs_2.sqlite",
    "memories_1.sqlite",
    "state_5.sqlite",
    "workbuddy.db",
    "workspace-state.json",
    "settings.json",
    "models.json",
    "SOUL.md",
    "USER.md",
    "IDENTITY.md",
    "config.yaml",
    "state.db",
    "processes.json",
    "projects.json",
    "trustedFolders.json",
    "state.json",
    "channel_directory.json",
    "gateway_state.json",
    ".mcp.json",
    "mcp-config.json",
    "mcp.json",
    "mcp-approvals.json",
    "mcp-disabled-tools.json",
}

MAX_MESSAGE_ROWS = 20000
MAX_MESSAGES_PER_SESSION = 200
MAX_FULL_PARSE_BYTES = 10 * 1024 * 1024


def ensure_dirs() -> None:
    for path in [RAW, IDX, DETAILS, REPORTS, DB_DIR, BY_SOURCE, BY_TYPE, SCRIPTS, WORK]:
        path.mkdir(parents=True, exist_ok=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def has_secret_name(path: Path) -> bool:
    name = path.name.lower()
    return any(part in name for part in SECRET_NAME_PARTS)


def excluded_by_dir(path: Path) -> bool:
    parts = {p.lower() for p in path.parts}
    return bool(parts & EXCLUDE_DIR_PARTS)


def source_family(source: str) -> str:
    if source.startswith("WSL_UbuntuD_"):
        return source.replace("WSL_UbuntuD_", "WSL:")
    if source.startswith("Codex"):
        return "Codex"
    if source.startswith("Claude") or source.startswith("AnthropicClaude"):
        return "Claude"
    if source.startswith("Cline"):
        return "Cline"
    if source.startswith("Cursor"):
        return "Cursor"
    if source.startswith("Gemini"):
        return "Gemini"
    if source.startswith("Cagent"):
        return "Cagent"
    if source.startswith("Ollama"):
        return "Ollama"
    if source.startswith("OpenAI"):
        return "OpenAI"
    if source.startswith("Documents_Codex"):
        return "Documents:Codex"
    if source.startswith("Documents_Cline"):
        return "Documents:Cline"
    if source.startswith("WorkBuddy"):
        return "WorkBuddy"
    if source.startswith("Hermes"):
        return "Hermes"
    return source


def should_include(source: str, root: Path, path: Path) -> tuple[bool, str]:
    if not path.is_file():
        return False, "not_file"
    if has_secret_name(path):
        return False, "secret_name"
    rel = path.relative_to(root)
    if excluded_by_dir(rel):
        return False, "excluded_dir"
    if path.name in TOP_LEVEL_FILES and path.parent == root:
        return True, "top_level_file"
    if path.parent == root and path.suffix.lower() in INCLUDE_EXTS:
        return True, "root_structured_file"
    family = source_family(source)
    include_dirs = INCLUDE_DIRS.get(source, []) + INCLUDE_DIRS.get(family, [])
    if include_dirs and rel.parts:
        top = rel.parts[0]
        if top in include_dirs and path.suffix.lower() in INCLUDE_EXTS:
            return True, "included_dir"
    if path.suffix.lower() in {".sqlite", ".db"} and path.parent == root:
        return True, "root_database"
    if source.endswith("_Roaming") or source.endswith("_Local") or source.endswith("_Home"):
        if path.suffix.lower() in {".sqlite", ".db", ".json", ".jsonl", ".md", ".yaml", ".yml", ".toml"}:
            return True, "appdata_structured_file"
    if source.startswith("Documents_"):
        if path.suffix.lower() in INCLUDE_EXTS:
            return True, "documents_structured_file"
    return False, "not_selected"


def safe_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.stat().st_size == src.stat().st_size:
        return
    if src.suffix.lower() in {".sqlite", ".db"}:
        try:
            src_con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
            dst_con = sqlite3.connect(dst)
            with dst_con:
                src_con.backup(dst_con)
            src_con.close()
            dst_con.close()
            shutil.copystat(src, dst)
            return
        except Exception:
            pass
    shutil.copy2(src, dst)


def collect_files() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    for source, root in SOURCE_ROOTS:
        if not root.exists():
            continue
        if root.is_file():
            include, reason = should_include(source, root.parent, root)
            if include:
                target = RAW / source / root.name
                try:
                    safe_copy(root, target)
                    digest = sha256_file(target)
                    rows.append(
                        {
                            "source": source,
                            "family": source_family(source),
                            "source_root": str(root),
                            "relative_path": root.name,
                            "copied_path": str(target.relative_to(AGENT)),
                            "extension": root.suffix.lower(),
                            "size_bytes": target.stat().st_size,
                            "modified_at": datetime.fromtimestamp(root.stat().st_mtime).isoformat(timespec="seconds"),
                            "sha256": digest,
                            "include_reason": reason,
                        }
                    )
                except Exception as exc:
                    skipped[f"copy_error: {exc}"] += 1
            continue
        candidates: list[Path] = []
        for child in root.iterdir():
            if child.is_file():
                candidates.append(child)

        family = source_family(source)
        include_dirs = INCLUDE_DIRS.get(source, []) + INCLUDE_DIRS.get(family, [])
        if source.startswith("Documents_") or source in {"Cagent"}:
            for path in root.rglob("*"):
                if excluded_by_dir(path.relative_to(root)):
                    continue
                if path.is_file() and path.suffix.lower() in INCLUDE_EXTS:
                    candidates.append(path)
        for dir_name in sorted(set(include_dirs)):
            dir_path = root / dir_name
            if dir_path.exists() and dir_path.is_dir():
                for path in dir_path.rglob("*"):
                    if excluded_by_dir(path.relative_to(root)):
                        continue
                    if path.is_file():
                        candidates.append(path)

        for path in candidates:
            include, reason = should_include(source, root, path)
            if not include:
                skipped[reason] += 1
                continue
            rel = path.relative_to(root)
            target = RAW / source / rel
            try:
                safe_copy(path, target)
                digest = sha256_file(target)
                rows.append(
                    {
                        "source": source,
                        "family": source_family(source),
                        "source_root": str(root),
                        "relative_path": str(rel),
                        "copied_path": str(target.relative_to(AGENT)),
                        "extension": path.suffix.lower(),
                        "size_bytes": target.stat().st_size,
                        "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                        "sha256": digest,
                        "include_reason": reason,
                    }
                )
            except Exception as exc:
                rows.append(
                    {
                        "source": source,
                        "family": source_family(source),
                        "source_root": str(root),
                        "relative_path": str(rel),
                        "copied_path": "",
                        "extension": path.suffix.lower(),
                        "size_bytes": path.stat().st_size if path.exists() else 0,
                        "modified_at": "",
                        "sha256": "",
                        "include_reason": f"copy_error: {exc}",
                    }
                )
    skipped_rows = [{"reason": k, "count": v} for k, v in sorted(skipped.items())]
    write_csv(IDX / "skipped_file_reasons.csv", skipped_rows)
    return rows


def collect_wsl_archives() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for spec in WSL_ARCHIVE_SOURCES:
        source = spec["source"]
        distro = spec["distro"]
        out_dir = RAW / source
        out_dir.mkdir(parents=True, exist_ok=True)
        archive = out_dir / "agent_data.tar.gz"
        manifest = out_dir / "agent_file_manifest.tsv"
        items = " ".join(spec["items"])
        excludes = " ".join(f"--exclude={json.dumps(pattern)}" for pattern in ARCHIVE_EXCLUDES)
        archive_posix = str(archive).replace("\\", "/").replace("C:", "/mnt/c")
        manifest_posix = str(manifest).replace("\\", "/").replace("C:", "/mnt/c")
        command = (
            f"cd {shlex.quote(spec['home'])} && "
            f"mkdir -p {shlex.quote(str(out_dir).replace(chr(92), '/').replace('C:', '/mnt/c'))} && "
            f"tar --ignore-failed-read {excludes} -czf {shlex.quote(archive_posix)} {items} 2>/tmp/agent_tar_warnings.log; "
            f"find {items} -type f \\( -iname '*.json' -o -iname '*.jsonl' -o -iname '*.md' -o -iname '*.txt' -o -iname '*.toml' -o -iname '*.yaml' -o -iname '*.yml' -o -iname '*.csv' -o -iname '*.sqlite' -o -iname '*.db' -o -iname '*.log' \\) -printf '%p\\t%s\\t%T@\\n' 2>/dev/null | "
            "grep -Evi '(auth|credential|credentials|secret|token|oauth|id_ed25519|/node_modules/|/cache/|/\\.cache/|/tmp/|/\\.tmp/|/vendor/|/target/|/dist/|/build/|/\\.git/)' | "
            f"cat > {shlex.quote(manifest_posix)}"
        )
        try:
            subprocess.run(["wsl", "-d", distro, "--", "bash", "-lc", command], check=False)
        except Exception as exc:
            rows.append(
                {
                    "source": source,
                    "family": "WSL:Archive",
                    "source_root": f"{distro}:{spec['home']}",
                    "relative_path": "__archive_error__",
                    "copied_path": "",
                    "extension": "",
                    "size_bytes": 0,
                    "modified_at": "",
                    "sha256": "",
                    "include_reason": f"wsl_archive_error: {exc}",
                }
            )
            continue
        for path, reason in [(archive, "wsl_archive"), (manifest, "wsl_manifest")]:
            if not path.exists():
                continue
            rows.append(
                {
                    "source": source,
                    "family": "WSL:Archive",
                    "source_root": f"{distro}:{spec['home']}",
                    "relative_path": path.name,
                    "copied_path": str(path.relative_to(AGENT)),
                    "extension": path.suffix.lower(),
                    "size_bytes": path.stat().st_size,
                    "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                    "sha256": sha256_file(path),
                    "include_reason": reason,
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def read_text_excerpt(path: Path, limit: int = 4000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except Exception:
        return ""


def extract_skill_rows(file_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in file_rows:
        if Path(row["relative_path"]).name != "SKILL.md" or not row["copied_path"]:
            continue
        path = AGENT / row["copied_path"]
        text = read_text_excerpt(path, 12000)
        name = ""
        description = ""
        for line in text.splitlines()[:40]:
            if line.startswith("name:"):
                name = line.split(":", 1)[1].strip().strip('"')
            elif line.startswith("description:"):
                description = line.split(":", 1)[1].strip().strip('"')
        rows.append(
            {
                "source": row["source"],
                "family": row["family"],
                "skill_name": name or path.parent.name,
                "description": description,
                "copied_path": row["copied_path"],
                "size_bytes": row["size_bytes"],
                "sha256": row["sha256"],
            }
        )
    return rows


def classify_memory_path(rel: str) -> str:
    low = rel.lower()
    if "rollout_summaries" in low:
        return "rollout_summary"
    if "memory" in low or "memories" in low or "memery" in low:
        return "memory"
    if "session" in low:
        return "session"
    return "other"


def extract_memory_rows(file_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in file_rows:
        rel_low = row["relative_path"].lower()
        if not any(k in rel_low for k in ["memory", "memories", "memery", "rollout_summaries"]):
            continue
        rows.append(
            {
                "source": row["source"],
                "family": row["family"],
                "memory_type": classify_memory_path(row["relative_path"]),
                "relative_path": row["relative_path"],
                "copied_path": row["copied_path"],
                "size_bytes": row["size_bytes"],
                "modified_at": row["modified_at"],
                "sha256": row["sha256"],
                "excerpt": read_text_excerpt(AGENT / row["copied_path"], 1000) if row["copied_path"] and row["extension"] in {".md", ".txt", ".json", ".jsonl"} else "",
            }
        )
    return rows


def parse_json_line(line: str) -> dict[str, Any] | None:
    try:
        value = json.loads(line)
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def detect_role(obj: dict[str, Any]) -> str:
    for key in ["role", "author", "sender"]:
        value = obj.get(key)
        if isinstance(value, str):
            return value
    item = obj.get("item")
    if isinstance(item, dict):
        return detect_role(item)
    payload = obj.get("payload")
    if isinstance(payload, dict):
        return detect_role(payload)
    return ""


def extract_text(obj: Any, limit: int = 2000) -> str:
    texts: list[str] = []

    def walk(value: Any) -> None:
        if len(" ".join(texts)) > limit:
            return
        if isinstance(value, str):
            if len(value) > 20:
                texts.append(value)
        elif isinstance(value, list):
            for item in value[:10]:
                walk(item)
        elif isinstance(value, dict):
            for key in ["text", "content", "message", "input", "output"]:
                if key in value:
                    walk(value[key])
            if not texts:
                for v in list(value.values())[:8]:
                    walk(v)

    walk(obj)
    return " ".join(" ".join(texts).split())[:limit]


def extract_session_rows(file_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    sessions = []
    messages = []
    for row in file_rows:
        rel_low = row["relative_path"].lower()
        ext = row["extension"]
        if not row["copied_path"] or not ("session" in rel_low or "rollout" in rel_low):
            continue
        if ext not in {".jsonl", ".json"}:
            continue
        path = AGENT / row["copied_path"]
        role_counts: Counter[str] = Counter()
        message_count = 0
        first_text = ""
        session_id = Path(row["relative_path"]).stem
        if ext == ".jsonl":
            with path.open("r", encoding="utf-8", errors="replace") as f:
                for idx, line in enumerate(f):
                    message_count += 1
                    if int(row["size_bytes"] or 0) > MAX_FULL_PARSE_BYTES and idx >= MAX_MESSAGES_PER_SESSION:
                        continue
                    obj = parse_json_line(line)
                    if not obj:
                        continue
                    role = detect_role(obj)
                    text = extract_text(obj, 1200)
                    if role or text:
                        role_counts[role or "unknown"] += 1
                        if not first_text and text:
                            first_text = text[:500]
                        if len(messages) < MAX_MESSAGE_ROWS and idx < MAX_MESSAGES_PER_SESSION:
                            messages.append(
                                {
                                    "session_id": session_id,
                                    "source": row["source"],
                                    "family": row["family"],
                                    "message_index": idx,
                                    "role": role or "unknown",
                                    "text_excerpt": text[:1200],
                                }
                            )
        else:
            try:
                obj = json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")
                text = extract_text(obj, 1200)
                role = detect_role(obj) or "unknown"
                if text:
                    message_count = 1
                    role_counts[role] += 1
                    first_text = text[:500]
                    messages.append(
                        {
                            "session_id": session_id,
                            "source": row["source"],
                            "family": row["family"],
                            "message_index": 0,
                            "role": role,
                            "text_excerpt": text[:1200],
                        }
                    )
            except Exception:
                pass
        sessions.append(
            {
                "session_id": session_id,
                "source": row["source"],
                "family": row["family"],
                "relative_path": row["relative_path"],
                "copied_path": row["copied_path"],
                "size_bytes": row["size_bytes"],
                "modified_at": row["modified_at"],
                "message_count": message_count,
                "user_count": role_counts.get("user", 0),
                "assistant_count": role_counts.get("assistant", 0),
                "tool_count": role_counts.get("tool", 0) + role_counts.get("function", 0),
                "unknown_count": role_counts.get("unknown", 0),
                "first_text_excerpt": first_text,
            }
        )
    return sessions, messages


def inspect_sqlite_files(file_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in file_rows:
        if row["extension"] not in {".sqlite", ".db"} or not row["copied_path"]:
            continue
        path = AGENT / row["copied_path"]
        try:
            con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            for table, in con.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name"):
                try:
                    count = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                except Exception:
                    count = None
                rows.append(
                    {
                        "source": row["source"],
                        "family": row["family"],
                        "database_path": row["copied_path"],
                        "table_name": table,
                        "row_count": count,
                    }
                )
            con.close()
        except Exception as exc:
            rows.append(
                {
                    "source": row["source"],
                    "family": row["family"],
                    "database_path": row["copied_path"],
                    "table_name": "__error__",
                    "row_count": "",
                }
            )
    return rows


def build_db(file_rows: list[dict[str, Any]], skill_rows: list[dict[str, Any]], memory_rows: list[dict[str, Any]], session_rows: list[dict[str, Any]], message_rows: list[dict[str, Any]], sqlite_rows: list[dict[str, Any]]) -> None:
    if DB.exists():
        DB.unlink()
    con = sqlite3.connect(DB)
    try:
        con.executescript(
            """
            CREATE TABLE source_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                family TEXT,
                source_root TEXT,
                relative_path TEXT,
                copied_path TEXT,
                extension TEXT,
                size_bytes INTEGER,
                modified_at TEXT,
                sha256 TEXT,
                include_reason TEXT
            );
            CREATE TABLE skills (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                family TEXT,
                skill_name TEXT,
                description TEXT,
                copied_path TEXT,
                size_bytes INTEGER,
                sha256 TEXT
            );
            CREATE TABLE memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                family TEXT,
                memory_type TEXT,
                relative_path TEXT,
                copied_path TEXT,
                size_bytes INTEGER,
                modified_at TEXT,
                sha256 TEXT,
                excerpt TEXT
            );
            CREATE TABLE sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                source TEXT,
                family TEXT,
                relative_path TEXT,
                copied_path TEXT,
                size_bytes INTEGER,
                modified_at TEXT,
                message_count INTEGER,
                user_count INTEGER,
                assistant_count INTEGER,
                tool_count INTEGER,
                unknown_count INTEGER,
                first_text_excerpt TEXT
            );
            CREATE TABLE session_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                source TEXT,
                family TEXT,
                message_index INTEGER,
                role TEXT,
                text_excerpt TEXT
            );
            CREATE TABLE database_tables (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT,
                family TEXT,
                database_path TEXT,
                table_name TEXT,
                row_count INTEGER
            );
            CREATE INDEX idx_source_files_family ON source_files(family);
            CREATE INDEX idx_source_files_sha256 ON source_files(sha256);
            CREATE INDEX idx_skills_name ON skills(skill_name);
            CREATE INDEX idx_memories_type ON memories(memory_type);
            CREATE INDEX idx_sessions_family ON sessions(family);
            CREATE INDEX idx_session_messages_session ON session_messages(session_id);
            """
        )

        def insert(table: str, rows: list[dict[str, Any]]) -> None:
            if not rows:
                return
            keys = list(rows[0].keys())
            sql = f'INSERT INTO {table} ({",".join(keys)}) VALUES ({",".join(":" + k for k in keys)})'
            con.executemany(sql, rows)

        insert("source_files", file_rows)
        insert("skills", skill_rows)
        insert("memories", memory_rows)
        insert("sessions", session_rows)
        insert("session_messages", message_rows)
        insert("database_tables", sqlite_rows)
        con.commit()
    finally:
        con.close()


def write_summary(file_rows: list[dict[str, Any]], skill_rows: list[dict[str, Any]], memory_rows: list[dict[str, Any]], session_rows: list[dict[str, Any]], message_rows: list[dict[str, Any]], sqlite_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_family = Counter(row["family"] for row in file_rows)
    by_type = Counter(row["extension"] or "(none)" for row in file_rows)
    size_by_family: defaultdict[str, int] = defaultdict(int)
    for row in file_rows:
        size_by_family[row["family"]] += int(row["size_bytes"] or 0)

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "raw_files_copied": len(file_rows),
        "raw_size_mb": round(sum(int(r["size_bytes"] or 0) for r in file_rows) / 1024 / 1024, 2),
        "skills": len(skill_rows),
        "memory_files": len(memory_rows),
        "session_files": len(session_rows),
        "session_message_excerpt_rows": len(message_rows),
        "sqlite_table_rows": len(sqlite_rows),
        "by_family": dict(by_family),
        "size_mb_by_family": {k: round(v / 1024 / 1024, 2) for k, v in size_by_family.items()},
        "by_extension": dict(by_type),
        "database": "Agent/structured/sqlite/agent_data.sqlite",
    }
    (ANALYSIS_ROOT / "classification_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    table_rows = "".join(f"<tr><th>{k}</th><td>{json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v}</td></tr>" for k, v in summary.items())
    (REPORTS / "agent_data_summary.html").write_text(
        f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>Agent 数据纳入摘要</title>
<style>body{{font-family:Segoe UI,Microsoft YaHei,sans-serif;max-width:1040px;margin:32px auto;line-height:1.6}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ddd;padding:8px;text-align:left;vertical-align:top}}th{{width:260px;background:#f7f7f7}}</style></head>
<body><h1>Agent 数据纳入摘要</h1><table>{table_rows}</table></body></html>
""",
        encoding="utf-8",
    )
    return summary


def main() -> None:
    ensure_dirs()
    file_rows = collect_files()
    file_rows.extend(collect_wsl_archives())
    write_csv(IDX / "agent_source_files.csv", file_rows)

    skill_rows = extract_skill_rows(file_rows)
    memory_rows = extract_memory_rows(file_rows)
    session_rows, message_rows = extract_session_rows(file_rows)
    sqlite_rows = inspect_sqlite_files(file_rows)

    write_csv(DETAILS / "agent_skills.csv", skill_rows)
    write_csv(DETAILS / "agent_memories.csv", memory_rows)
    write_csv(DETAILS / "agent_sessions.csv", session_rows)
    write_csv(DETAILS / "agent_session_message_excerpts.csv", message_rows)
    write_csv(DETAILS / "agent_sqlite_tables.csv", sqlite_rows)

    build_db(file_rows, skill_rows, memory_rows, session_rows, message_rows, sqlite_rows)
    summary = write_summary(file_rows, skill_rows, memory_rows, session_rows, message_rows, sqlite_rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
