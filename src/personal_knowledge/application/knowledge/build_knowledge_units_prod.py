"""Phase 14 Plan 02 Task 2：可恢复 batch + 分类 retry + 内容寻址 cache。

production backfill engine，支持 --start / --resume、item ledger 状态机、
内容寻址 response cache、分类 retry（429/500/503 重试，400 fail-fast）。

核心契约（RESEARCH）：
  - 新建 run 与恢复 run 分成两个显式入口
  - resume 不调用 begin_staging()（不删除已完成结果）
  - cache hit 仍重跑当前 Pydantic/evidence/privacy gate
  - SQLite 单 writer：worker 只返回纯响应，主线程提交
  - model 从 CLI/config 注入，写 manifest，不可用则 abort
  - 多线程并行：ThreadPoolExecutor 并发 LLM，主线程串行写库

用法::

    # 新 run
    python build_knowledge_units_prod.py --start --inventory <id> --model gemini-3.5-flash --limit 50

    # 恢复（默认 8 路并发）
    python build_knowledge_units_prod.py --resume <run_id> --model gemini-3.5-flash --workers 8

    # 检查状态
    python build_knowledge_units_prod.py --status <run_id>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sqlite3
import sys
import threading
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
_THIS_DIR = _SCRIPTS_DIR  # legacy alias: scripts root for resource paths

from personal_knowledge.core.project_paths import UNIFIED_DB, AGENT_CONVERSATIONS_DB  # noqa: E402
from personal_knowledge.core.runtime_config import gcloud_access_token, vertex_config  # noqa: E402
from personal_knowledge.domains.knowledge.knowledge_unit_pipeline import RunManifest  # noqa: E402
from personal_knowledge.domains.knowledge.build_knowledge_units import (  # noqa: E402
    KnowledgeUnit, ExtractionResult, strip_system_injections, is_meaningful,
    _clean_json, PROMPT_PATH, PROMPT_VERSION,
)

_VERTEX = vertex_config()
GCP_PROJECT = _VERTEX.project
DEFAULT_WORKERS = 4
# 跨线程全局起步间隔：默认约 20 RPM（与原串行 sleep(3) 同量级，避免 429）
DEFAULT_MIN_REQUEST_INTERVAL = 3.0
# 同 item 累计 attempt 超过此值后，retryable 升格 terminal，避免死循环
MAX_ITEM_ATTEMPTS = 6

# === 错误分类 ===

RETRYABLE_STATUS = {429, 500, 502, 503}
TERMINAL_STATUS = {400, 401, 403, 404}


def classify_error(status: int | None, exc: Exception | None) -> str:
    """分类 HTTP 错误为 retryable / terminal。"""
    if status and status in RETRYABLE_STATUS:
        return "retryable"
    if status and status in TERMINAL_STATUS:
        return "terminal"
    if isinstance(exc, urllib.error.HTTPError) and exc.code in RETRYABLE_STATUS:
        return "retryable"
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return "retryable"
    return "terminal"


# === Cache ===

def compute_cache_key(model: str, prompt_hash: str, schema_hash: str,
                      input_hash: str, config_hash: str) -> str:
    """内容寻址 cache key。"""
    payload = f"{model}|{prompt_hash}|{schema_hash}|{input_hash}|{config_hash}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def get_cached_response(con: sqlite3.Connection, cache_key: str) -> str | None:
    """从 cache 读原始 LLM 响应。"""
    row = con.execute(
        "SELECT response_text FROM knowledge_response_cache WHERE cache_key=?",
        (cache_key,),
    ).fetchone()
    return row[0] if row else None


def put_cached_response(con: sqlite3.Connection, cache_key: str, model: str,
                        prompt_hash: str, schema_hash: str, input_hash: str,
                        config_hash: str, response_text: str, response_hash: str,
                        run_id: str, tokens_total: int = 0) -> None:
    """写 cache。"""
    con.execute(
        "INSERT OR REPLACE INTO knowledge_response_cache VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?)",
        (cache_key, run_id, model, prompt_hash, schema_hash, input_hash,
         config_hash, response_text, response_hash,
         datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         tokens_total),
    )


# === LLM 调用（分类 retry + token refresh）===

class TokenProvider:
    """run-scoped gcloud token provider（线程安全）。"""

    def __init__(self) -> None:
        self._token: str | None = None
        self._expires: float = 0
        self._lock = threading.Lock()

    def get(self) -> str:
        with self._lock:
            if self._token and time.time() < self._expires:
                return self._token
            self._token = self._fetch()
            self._expires = time.time() + 3000  # 50 min
            return self._token

    def refresh(self) -> str:
        with self._lock:
            self._token = None
        return self.get()

    @staticmethod
    def _fetch() -> str:
        return gcloud_access_token(_VERTEX)


class RequestRateLimiter:
    """跨线程最小请求间隔限速，支持 429 自适应减速。"""

    def __init__(self, min_interval: float) -> None:
        self._base_interval = max(0.0, float(min_interval))
        self._min_interval = self._base_interval
        self._lock = threading.Lock()
        self._next_at = 0.0
        self._consecutive_429 = 0

    def wait(self) -> None:
        if self._min_interval <= 0:
            return
        with self._lock:
            now = time.monotonic()
            delay = self._next_at - now
            if delay > 0:
                time.sleep(delay)
                now = time.monotonic()
            self._next_at = now + self._min_interval

    def note_success(self) -> None:
        with self._lock:
            self._consecutive_429 = 0
            # 缓慢回到 base interval
            self._min_interval = max(
                self._base_interval,
                self._min_interval * 0.9,
            )

    def note_429(self) -> None:
        with self._lock:
            self._consecutive_429 += 1
            # 最多扩到 base * 4（默认 12s ≈ 5 RPM）
            self._min_interval = min(
                self._base_interval * 4.0,
                max(self._base_interval, self._min_interval * 1.5),
            )
            # 立刻插入冷却，避免雪崩
            cooldown = min(30.0, 3.0 * self._consecutive_429)
            self._next_at = max(self._next_at, time.monotonic() + cooldown)


def call_llm_with_retry(
    system_prompt: str,
    user_content: str,
    model: str,
    token_provider: TokenProvider,
    max_retries: int = 4,
    base_backoff: float = 2.0,
    max_backoff: float = 60.0,
    rate_limiter: RequestRateLimiter | None = None,
) -> dict:
    """调用 Vertex AI，分类 retry。返回 {"text":..., "usage":...} 或 {"error":..., "error_class":...}。"""
    url = (f"https://aiplatform.googleapis.com/v1/projects/{GCP_PROJECT}"
           f"/locations/us-central1/publishers/google/models/{model}:generateContent")
    user_text = f"{system_prompt}\n\n---\n用户对话证据（role=user）：\n{user_content}\n\n---\n请提取知识单元，输出JSON："
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {"maxOutputTokens": 2048, "temperature": 0, "thinkingConfig": {"thinkingBudget": 0}},
    }).encode()

    for attempt in range(max_retries + 1):
        if rate_limiter is not None:
            rate_limiter.wait()
        token = token_provider.get()
        req = urllib.request.Request(url, data=body, headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }, method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=120)
            data = json.loads(resp.read().decode())
            # extract text
            parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts if p.get("text") and not p.get("thought"))
            usage = data.get("usageMetadata", {})
            if rate_limiter is not None:
                rate_limiter.note_success()
            return {"text": text, "usage": usage}
        except urllib.error.HTTPError as e:
            error_class = classify_error(e.code, e)
            if e.code == 429 and rate_limiter is not None:
                rate_limiter.note_429()
            if error_class == "retryable" and attempt < max_retries:
                # Retry-After + jitter
                retry_after = e.headers.get("Retry-After")
                if retry_after:
                    wait = min(float(retry_after), max_backoff)
                else:
                    wait = min(base_backoff * (2 ** attempt), max_backoff)
                wait += int(hashlib.sha256(f"{attempt}".encode()).hexdigest()[:2], 16) % 16  # jitter 0-15
                time.sleep(float(wait))
                if e.code == 401:
                    token_provider.refresh()
                continue
            return {"error": f"HTTP {e.code}", "error_class": error_class,
                    "detail": e.read().decode()[:200], "attempts": attempt + 1}
        except (TimeoutError, ConnectionError) as e:
            if attempt < max_retries:
                wait = min(base_backoff * (2 ** attempt), max_backoff)
                time.sleep(wait)
                continue
            return {"error": str(e), "error_class": "retryable", "attempts": attempt + 1}
        except Exception as e:
            error_class = classify_error(None, e)
            if error_class == "retryable" and attempt < max_retries:
                wait = min(base_backoff * (2 ** attempt), max_backoff)
                wait += int(hashlib.sha256(f"{attempt}".encode()).hexdigest()[:2], 16) % 16
                time.sleep(float(wait))
                continue
            return {"error": f"{type(e).__name__}: {str(e)[:150]}", "error_class": error_class, "attempts": attempt + 1}
    return {"error": "max retries exceeded", "error_class": "retryable", "attempts": max_retries + 1}


# === Item ledger 状态机 ===

def init_run_items(con: sqlite3.Connection, run_id: str, inventory_id: str) -> int:
    """为 run 的每个 inventory item 创建 pending work-item。返回 item 数。"""
    items = con.execute(
        "SELECT position, evidence_ref FROM knowledge_inventory_items "
        "WHERE inventory_id=? ORDER BY position",
        (inventory_id,),
    ).fetchall()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for pos, ref in items:
        con.execute(
            "INSERT OR IGNORE INTO knowledge_run_items "
            "(run_id, inventory_id, position, evidence_ref, status, attempt_count, "
            "lease_started_at, last_error_class, cache_key, response_hash, unit_count, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, inventory_id, pos, ref, "pending", 0, None, None, None, None, 0, now),
        )
    con.commit()
    return len(items)


def recover_expired_leases(
    con: sqlite3.Connection,
    run_id: str,
    lease_timeout: float = 600,
    force_all: bool = False,
) -> int:
    """恢复过期 in_flight lease 为 retryable。返回恢复数。

    force_all=True 时回收本 run 全部 in_flight（单 writer resume 场景）。
    """
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cutoff = datetime.now(timezone.utc).timestamp() - lease_timeout
    rows = con.execute(
        "SELECT id, lease_started_at FROM knowledge_run_items "
        "WHERE run_id=? AND status='in_flight'",
        (run_id,),
    ).fetchall()
    recovered = 0
    for item_id, lease_iso in rows:
        should_recover = force_all
        if not should_recover and lease_iso:
            try:
                lease_ts = datetime.fromisoformat(lease_iso.replace("Z", "+00:00")).timestamp()
                should_recover = lease_ts < cutoff
            except ValueError:
                should_recover = True
        elif not should_recover and not lease_iso:
            should_recover = True
        if should_recover:
            con.execute(
                "UPDATE knowledge_run_items SET status='retryable', updated_at=? WHERE id=?",
                (now_iso, item_id),
            )
            recovered += 1
    con.commit()
    return recovered


def get_pending_items(con: sqlite3.Connection, run_id: str, batch_size: int = 50) -> list[dict]:
    """获取 pending + retryable 的 items。

    优先低 attempt_count，避免 429 后反复抽同一批高失败项。
    """
    rows = con.execute(
        "SELECT id, position, evidence_ref, status, attempt_count "
        "FROM knowledge_run_items WHERE run_id=? AND status IN ('pending','retryable') "
        "ORDER BY attempt_count ASC, position ASC LIMIT ?",
        (run_id, batch_size),
    ).fetchall()
    return [{"row_id": r[0], "position": r[1], "evidence_ref": r[2],
             "status": r[3], "attempt_count": r[4]} for r in rows]


def get_run_stats(con: sqlite3.Connection, run_id: str) -> dict:
    """run 的 item 状态统计。"""
    counts = {}
    for row in con.execute(
        "SELECT status, COUNT(*) FROM knowledge_run_items WHERE run_id=? GROUP BY status",
        (run_id,),
    ):
        counts[row[0]] = row[1]
    return counts


# === 主引擎 ===

def start_run(
    model: str,
    inventory_id: str,
    db_path: Path = UNIFIED_DB,
    limit: int | None = None,
    batch_size: int = 50,
    pilot_positions: list[int] | None = None,
) -> str:
    """启动新 production extraction run。返回 run_id。

    pilot_positions: 如果提供，只处理这些 position 的 items，其余标记 abstained。
    """
    con = sqlite3.connect(str(db_path))

    # 读 inventory
    inv = con.execute(
        "SELECT dataset_hash, source_checksum, item_count FROM knowledge_inventory WHERE inventory_id=?",
        (inventory_id,),
    ).fetchone()
    if not inv:
        raise ValueError(f"inventory 不存在: {inventory_id}")
    dataset_hash, source_checksum, item_count = inv

    prompt_text = PROMPT_PATH.read_text(encoding="utf-8")
    prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()[:16]
    schema_hash = "v1_extra_forbid"
    config = {"batch_size": batch_size, "limit": limit,
              "pilot_positions": pilot_positions is not None}
    config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:16]

    manifest = RunManifest.create(
        run_type="extraction",
        source_build_id=source_checksum,
        input_data={"inventory_id": inventory_id, "dataset_hash": dataset_hash},
        prompt_version=PROMPT_VERSION,
        model=model,
        config=config,
    )

    # 写 manifest（status=staging）
    con.execute(
        "INSERT OR REPLACE INTO knowledge_build_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (manifest.run_id, "extraction", manifest.generated_at, source_checksum,
         manifest.input_hash, PROMPT_VERSION, "v1", model, "", config_hash,
         "", "", "staging", "", ""),
    )

    # init item ledger
    init_run_items(con, manifest.run_id, inventory_id)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if pilot_positions is not None:
        # pilot 模式：只保留 pilot positions 为 pending，其余 abstained
        pilot_set = set(pilot_positions)
        con.execute(
            "UPDATE knowledge_run_items SET status='abstained', updated_at=? "
            "WHERE run_id=?",
            (now, manifest.run_id),
        )
        for pos in pilot_positions:
            con.execute(
                "UPDATE knowledge_run_items SET status='pending', updated_at=? "
                "WHERE run_id=? AND position=?",
                (now, manifest.run_id, pos),
            )
    elif limit and limit < item_count:
        # limit 模式：超出范围的 abstained
        con.execute(
            "UPDATE knowledge_run_items SET status='abstained', updated_at=? "
            "WHERE run_id=? AND position >= ?",
            (now, manifest.run_id, limit),
        )

    con.commit()
    con.close()
    return manifest.run_id


def resume_run(run_id: str, model: str, db_path: Path = UNIFIED_DB,
               batch_size: int = 50) -> dict:
    """恢复 production extraction run。不调用 begin_staging（不删除旧结果）。"""
    con = sqlite3.connect(str(db_path))

    # 验证 run 存在
    run = con.execute(
        "SELECT status, input_hash FROM knowledge_build_runs WHERE run_id=?",
        (run_id,),
    ).fetchone()
    if not run:
        raise ValueError(f"run 不存在: {run_id}")

    # 单 writer：resume 时强制回收全部 in_flight（进程中断后可继续）
    recovered = recover_expired_leases(con, run_id, force_all=True)
    stats = get_run_stats(con, run_id)

    con.close()
    return {"run_id": run_id, "recovered_leases": recovered, "stats": stats}


def _commit_item_result(
    con: sqlite3.Connection,
    run_id: str,
    item: dict,
    work: dict,
    model: str,
    prompt_hash: str,
    schema_hash: str,
    config_hash: str,
    stats: dict,
) -> None:
    """主线程：把 worker 结果写入 SQLite（单 writer）。"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    row_id = item["row_id"]
    cache_key = work["cache_key"]
    input_hash = work["input_hash"]

    if work.get("kind") == "llm_error":
        error_class = work.get("error_class", "terminal")
        error_text = str(work.get("error") or "")
        is_429 = "429" in error_text
        # 429 不计入 attempt 额度：限流是环境问题，不是样本质量
        attempt_count = item.get("attempt_count", 0) + (0 if is_429 else 1)
        if is_429:
            # 回退 attempt_count 增量（claim 时 +1 了），避免 429 烧尽重试次数
            con.execute(
                "UPDATE knowledge_run_items SET attempt_count=MAX(attempt_count-1, 0) WHERE id=?",
                (row_id,),
            )
            new_status = "retryable"
            error_class = "retryable"
            stats["rate_limited"] = stats.get("rate_limited", 0) + 1
        elif error_class == "retryable" and attempt_count < MAX_ITEM_ATTEMPTS:
            new_status = "retryable"
        else:
            new_status = "terminal_failed"
            if error_class == "retryable":
                error_class = "max_attempts"
        con.execute(
            "UPDATE knowledge_run_items SET status=?, last_error_class=?, "
            "cache_key=?, updated_at=? WHERE id=?",
            (new_status, error_class, cache_key, now, row_id),
        )
        con.commit()
        stats["failed"] += 1
        return

    raw_text = work["raw_text"]
    if work.get("write_cache"):
        response_hash = hashlib.sha256(raw_text.encode()).hexdigest()[:32]
        put_cached_response(
            con, cache_key, model, prompt_hash, schema_hash,
            input_hash, config_hash, raw_text, response_hash, run_id,
        )

    try:
        parsed = json.loads(_clean_json(raw_text))
        result = ExtractionResult(**parsed)
    except (json.JSONDecodeError, ValidationError):
        con.execute(
            "UPDATE knowledge_run_items SET status='terminal_failed', "
            "last_error_class='schema_invalid', cache_key=?, updated_at=? WHERE id=?",
            (cache_key, now, row_id),
        )
        con.commit()
        stats["failed"] += 1
        return

    response_hash = hashlib.sha256(raw_text.encode()).hexdigest()[:32]
    if result.abstain:
        con.execute(
            "UPDATE knowledge_run_items SET status='abstained', cache_key=?, "
            "response_hash=?, unit_count=0, updated_at=? WHERE id=?",
            (cache_key, response_hash, now, row_id),
        )
        stats["abstained"] += 1
    else:
        for ordinal, unit in enumerate(result.units, 1):
            ev_ref = item["evidence_ref"]
            unit_id = "v1|" + hashlib.sha256(
                f"{run_id}|{ev_ref}|{ordinal}".encode()
            ).hexdigest()[:32]
            lifecycle = unit.lifecycle if unit.lifecycle in (
                "current", "deprecated", "superseded", "conflict"
            ) else "current"
            con.execute(
                "INSERT OR REPLACE INTO knowledge_units "
                "(unit_id, run_id, unit_type, subject, question, answer, confidence, "
                "evidence_quote, lifecycle, source_session_id, source_message_ref, "
                "source_agent, evidence_scope, status, version, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (unit_id, run_id, unit.unit_type, unit.subject, unit.question,
                 unit.answer, unit.confidence, unit.evidence_quote, lifecycle,
                 "", item["evidence_ref"], "", "user", "staging", 1, now),
            )
            con.execute(
                "INSERT OR IGNORE INTO knowledge_unit_evidence (unit_id, evidence_ref) VALUES (?,?)",
                (unit_id, item["evidence_ref"]),
            )
        con.execute(
            "UPDATE knowledge_run_items SET status='succeeded', cache_key=?, "
            "response_hash=?, unit_count=?, updated_at=? WHERE id=?",
            (cache_key, response_hash, len(result.units), now, row_id),
        )
        stats["succeeded"] += 1
        stats["units"] += len(result.units)

    stats["processed"] += 1
    con.commit()


def process_run(
    run_id: str,
    model: str,
    db_path: Path = UNIFIED_DB,
    canonical_db: Path = AGENT_CONVERSATIONS_DB,
    batch_size: int = 50,
    max_items: int | None = None,
    workers: int = DEFAULT_WORKERS,
    min_request_interval: float = DEFAULT_MIN_REQUEST_INTERVAL,
) -> dict:
    """处理 run 的 pending/retryable items。

    多线程：worker 只调 LLM 返回纯响应；主线程单 writer 提交 SQLite。
    """
    con = sqlite3.connect(str(db_path), timeout=60)
    token_provider = TokenProvider()
    rate_limiter = RequestRateLimiter(min_request_interval)
    prompt_text = PROMPT_PATH.read_text(encoding="utf-8")
    prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()[:16]
    schema_hash = "v1_extra_forbid"
    # 与串行路径保持同一 cache 命名空间（workers 只影响调度，不参与 cache key）
    config_hash = hashlib.sha256(
        json.dumps({"batch_size": batch_size}, sort_keys=True).encode()
    ).hexdigest()[:16]

    inv_row = con.execute(
        "SELECT inventory_id FROM knowledge_run_items WHERE run_id=? LIMIT 1",
        (run_id,),
    ).fetchone()
    if not inv_row:
        # Incremental prepare should have seeded items; fail closed instead of NPE
        con.close()
        raise ValueError(
            f"run {run_id} has no knowledge_run_items — refuse to process empty ledger"
        )
    inventory_id = inv_row[0]
    _ = inventory_id  # reserved for future inventory-side joins

    canon_con = sqlite3.connect(f"file:{canonical_db.as_posix()}?mode=ro", uri=True)
    canon_con.row_factory = sqlite3.Row

    stats = {
        "processed": 0, "succeeded": 0, "abstained": 0, "failed": 0,
        "cache_hits": 0, "units": 0, "workers": max(1, workers),
        "rate_limited": 0, "stopped_reason": "",
    }
    workers = max(1, int(workers))
    # claim 窗口与并发对齐，避免一次挂起过多 in_flight
    claim_size = max(workers * 2, min(batch_size, workers * 4))
    t0 = time.time()
    consecutive_all_retryable = 0
    consecutive_zero_success = 0
    print(
        f"[process] run={run_id} workers={workers} "
        f"min_interval={min_request_interval}s claim_size={claim_size}",
        flush=True,
    )

    def _llm_worker(payload: dict) -> dict:
        """worker：只做 LLM 调用，不碰 SQLite。"""
        resp = call_llm_with_retry(
            prompt_text,
            payload["cleaned"],
            model,
            token_provider,
            max_retries=2,  # 并行路径少重试，把节奏交给 rate limiter / 下一批
            rate_limiter=rate_limiter,
        )
        if "error" in resp:
            return {
                "row_id": payload["row_id"],
                "kind": "llm_error",
                "error_class": resp.get("error_class", "terminal"),
                "error": resp.get("error"),
                "cache_key": payload["cache_key"],
                "input_hash": payload["input_hash"],
            }
        return {
            "row_id": payload["row_id"],
            "kind": "ok",
            "raw_text": resp["text"],
            "cache_key": payload["cache_key"],
            "input_hash": payload["input_hash"],
            "write_cache": True,
        }

    with ThreadPoolExecutor(max_workers=workers) as executor:
        while True:
            if max_items and stats["processed"] >= max_items:
                break
            take = claim_size
            if max_items:
                take = min(take, max_items - stats["processed"])
            items = get_pending_items(con, run_id, take)
            if not items:
                break

            # 1) 主线程：claim + 读 content + cache 判定
            ready_cache: list[tuple[dict, dict]] = []
            llm_payloads: list[dict] = []
            for item in items:
                now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                con.execute(
                    "UPDATE knowledge_run_items SET status='in_flight', "
                    "lease_started_at=?, attempt_count=attempt_count+1, updated_at=? "
                    "WHERE id=?",
                    (now, now, item["row_id"]),
                )
                con.commit()

                row = canon_con.execute(
                    "SELECT content FROM canonical_messages WHERE canonical_message_id=?",
                    (item["evidence_ref"],),
                ).fetchone()
                if not row or not row["content"]:
                    con.execute(
                        "UPDATE knowledge_run_items SET status='terminal_failed', "
                        "last_error_class='missing_evidence', updated_at=? WHERE id=?",
                        (now, item["row_id"]),
                    )
                    con.commit()
                    stats["failed"] += 1
                    continue

                cleaned = strip_system_injections(row["content"])
                if not is_meaningful(cleaned):
                    con.execute(
                        "UPDATE knowledge_run_items SET status='abstained', updated_at=? WHERE id=?",
                        (now, item["row_id"]),
                    )
                    con.commit()
                    stats["abstained"] += 1
                    continue

                input_hash = hashlib.sha256(cleaned.encode()).hexdigest()[:32]
                cache_key = compute_cache_key(
                    model, prompt_hash, schema_hash, input_hash, config_hash
                )
                cached = get_cached_response(con, cache_key)
                if cached is not None:
                    stats["cache_hits"] += 1
                    ready_cache.append((item, {
                        "kind": "ok",
                        "raw_text": cached,
                        "cache_key": cache_key,
                        "input_hash": input_hash,
                        "write_cache": False,
                    }))
                else:
                    llm_payloads.append({
                        "row_id": item["row_id"],
                        "item": item,
                        "cleaned": cleaned,
                        "cache_key": cache_key,
                        "input_hash": input_hash,
                    })

            # 2) 主线程先消化 cache hit
            for item, work in ready_cache:
                _commit_item_result(
                    con, run_id, item, work, model,
                    prompt_hash, schema_hash, config_hash, stats,
                )

            # 3) worker 并发 LLM；主线程按完成顺序写库
            if llm_payloads:
                batch_retryable = 0
                batch_ok_before = stats["succeeded"]
                batch_abs_before = stats["abstained"]
                future_map = {
                    executor.submit(_llm_worker, p): p for p in llm_payloads
                }
                for fut in as_completed(future_map):
                    payload = future_map[fut]
                    item = payload["item"]
                    try:
                        work = fut.result()
                    except Exception as e:  # noqa: BLE001 — 保护单条，不拖垮 batch
                        work = {
                            "kind": "llm_error",
                            "error_class": "retryable",
                            "error": f"{type(e).__name__}: {e}",
                            "cache_key": payload["cache_key"],
                            "input_hash": payload["input_hash"],
                        }
                    if work.get("kind") == "llm_error" and work.get("error_class") == "retryable":
                        batch_retryable += 1
                    _commit_item_result(
                        con, run_id, item, work, model,
                        prompt_hash, schema_hash, config_hash, stats,
                    )
                    done = stats["processed"] + stats["failed"] + stats["abstained"]
                    if done % 10 == 0 or done == 1:
                        elapsed = time.time() - t0
                        print(
                            f"[progress] done≈{done} "
                            f"ok={stats['succeeded']} fail={stats['failed']} "
                            f"abs={stats['abstained']} units={stats['units']} "
                            f"cache_hit={stats['cache_hits']} "
                            f"elapsed={elapsed:.0f}s "
                            f"interval={rate_limiter._min_interval:.1f}s",
                            flush=True,
                        )
                batch_success_delta = (
                    (stats["succeeded"] - batch_ok_before)
                    + (stats["abstained"] - batch_abs_before)
                )
                # batch 内大量 429/retryable：冷却后再取下一批，避免热循环
                if llm_payloads and batch_retryable / len(llm_payloads) >= 0.5:
                    cool = min(120.0, 20.0 + 5.0 * batch_retryable)
                    print(
                        f"[cooldown] batch retryable={batch_retryable}/"
                        f"{len(llm_payloads)} sleep {cool:.0f}s "
                        f"rate_limited={stats.get('rate_limited', 0)}",
                        flush=True,
                    )
                    time.sleep(cool)
                # 连续全 retryable（典型 429）→ 冷却后干净退出
                if llm_payloads and batch_retryable == len(llm_payloads):
                    consecutive_all_retryable += 1
                    extra = min(180.0, 30.0 * consecutive_all_retryable)
                    print(
                        f"[cooldown] all-retryable batch "
                        f"#{consecutive_all_retryable}, extra {extra:.0f}s",
                        flush=True,
                    )
                    time.sleep(extra)
                else:
                    consecutive_all_retryable = 0
                # 连续 0 成功 batch（含 terminal 烧穿）→ 熔断，避免把样本打成 terminal
                if llm_payloads and batch_success_delta == 0:
                    consecutive_zero_success += 1
                    print(
                        f"[warn] zero-success batch #{consecutive_zero_success}/"
                        f"{len(llm_payloads)}",
                        flush=True,
                    )
                else:
                    consecutive_zero_success = 0
                if consecutive_all_retryable >= 2 or consecutive_zero_success >= 3:
                    stats["stopped_reason"] = (
                        "rate_limit_circuit_breaker"
                        if consecutive_all_retryable >= 2
                        else "zero_success_circuit_breaker"
                    )
                    print(
                        f"[stop] circuit breaker ({stats['stopped_reason']}); "
                        "exit for later resume",
                        flush=True,
                    )
                    break

    canon_con.close()
    con.close()
    stats["elapsed_sec"] = round(time.time() - t0, 1)
    return stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Phase 14 Plan 02: production backfill engine")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--start", action="store_true", help="启动新 run")
    g.add_argument("--resume", metavar="RUN_ID", help="恢复 run")
    g.add_argument("--status", metavar="RUN_ID", help="查看 run 状态")
    p.add_argument("--inventory", help="inventory ID（--start 时必须）")
    p.add_argument("--pilot-manifest", help="pilot manifest JSON 路径（--start 时用分层 sample positions）")
    p.add_argument("--model", required=False, default="gemini-3.5-flash", help="模型 ID")
    p.add_argument("--limit", type=int, default=None, help="只处理前 N 条")
    p.add_argument("--batch-size", type=int, default=50)
    p.add_argument("--max-items", type=int, default=None, help="单次最多处理 N 条（分批模式）")
    p.add_argument(
        "--workers", type=int, default=DEFAULT_WORKERS,
        help=f"LLM 并发线程数（默认 {DEFAULT_WORKERS}）",
    )
    p.add_argument(
        "--min-request-interval", type=float, default=DEFAULT_MIN_REQUEST_INTERVAL,
        help=f"跨线程最小请求间隔秒数（默认 {DEFAULT_MIN_REQUEST_INTERVAL}）",
    )
    p.add_argument("--db", type=Path, default=UNIFIED_DB)
    args = p.parse_args(argv)

    if args.status:
        con = sqlite3.connect(str(args.db))
        stats = get_run_stats(con, args.status)
        con.close()
        print(json.dumps({"run_id": args.status, "item_stats": stats}, ensure_ascii=False, indent=2))
        return 0

    if args.start:
        if not args.inventory:
            print("[error] --start 需要 --inventory", file=sys.stderr)
            return 2
        pilot_positions = None
        if args.pilot_manifest:
            import json as _json
            manifest = _json.loads(Path(args.pilot_manifest).read_text(encoding="utf-8"))
            pilot_positions = manifest.get("sample_positions", [])
            print(f"[pilot] {len(pilot_positions)} positions from manifest")
        run_id = start_run(args.model, args.inventory, args.db, args.limit,
                           args.batch_size, pilot_positions=pilot_positions)
        print(f"[start] run_id: {run_id}")
        stats = process_run(
            run_id, args.model, args.db,
            max_items=args.max_items,
            batch_size=args.batch_size,
            workers=args.workers,
            min_request_interval=args.min_request_interval,
        )
        print(f"[done] {json.dumps(stats, ensure_ascii=False)}")
        return 0

    if args.resume:
        info = resume_run(args.resume, args.model, args.db, args.batch_size)
        print(f"[resume] {json.dumps(info, ensure_ascii=False)}")
        stats = process_run(
            args.resume, args.model, args.db,
            max_items=args.max_items,
            batch_size=args.batch_size,
            workers=args.workers,
            min_request_interval=args.min_request_interval,
        )
        print(f"[done] {json.dumps(stats, ensure_ascii=False)}")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
