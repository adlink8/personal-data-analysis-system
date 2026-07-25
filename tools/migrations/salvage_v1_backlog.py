"""一次性迁移：salvage v1| staging 积压 unit（dry-run 优先）。

背景：knowledge_units 有约 1.6 万条 `v1|%` status='staging' 的旧版 prod 抽取
unit（无 evidence gate 时代）。抽查发现大量 evidence_quote 对不上
source_message_ref，但 quote 内容多数能在别的 canonical 消息里逐字找到
（证据链接指错消息，内容真实）。同时 canonical_knowledge_units 有 15249 条
status='current' 的"影子行"，其成员正是这些 staging unit —— 链接已存在，
只是 unit 状态导致影子行"无 current 成员"，正被检索索引服务。

三阶段（--dry-run 默认，--write 才落库）：

Phase 1 证据链修复（repair）
  用 evidence_quote 反查正确的 canonical 消息：先搜原 source_session_id
  同 session 的消息，未命中再全局兜底（quote 前/后 12 字做候选粗筛）。
  命中判定复用 extract_knowledge_units_l2_session._evidence_supported；
  多命中取"精确包含优先、内容最长"（同 L2 _best_message_for_quote 打分）。
  命中 → 更新 source_message_ref / source_session_id / source_agent /
  evidence_scope（按消息实际 role 映射）。
  未命中 → 不动，计 unrepairable。

Phase 2 并账（heal + merge，仅 --write；dry-run 只统计/抽样估算）
  - repairable 且已是某 current canonical 成员 → status='current'（影子行愈合）。
  - repairable 但不是任何 canonical 成员 → attach-or-create：对 current
    canonical 跑 merge_l2_into_canonical.find_match（按 unit_type 分桶，
    阈值沿用 ANSWER_SIM=0.85 / SUBJECT_SIM=0.5，未校准的 char 4-gram 沿用），
    命中挂 canonical_unit_members + unit 置 current；未命中新建 canonical 行
    （run_id='salvage_v1_backlog'，merge_reason='salvage_import'）+ 成员链接
    + unit 置 current。
  - unrepairable → status='rejected'。

Phase 3 清理（仅 --write）
  Phase 2 后仍无任何 current 成员、且成员含本批 v1 unit 的 current canonical
  → status='rejected'（内容不可救的影子行）。

--write 安全：先把 UNIFIED_DB 复制备份到
var/backups/personal_system_<UTC>.sqlite（当天已有备份则不重复拷贝）；
所有写操作在一个事务里，异常整体回滚。

用法:
    python tools/migrations/salvage_v1_backlog.py            # dry-run 完整报告
    python tools/migrations/salvage_v1_backlog.py --write    # 备份后一次性落库
"""

from __future__ import annotations

import argparse
import random
import shutil
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from personal_knowledge.core.project_paths import (  # noqa: E402
    AGENT_CONVERSATIONS_DB,
    UNIFIED_DB,
    VAR_DIR,
)
from personal_knowledge.application.knowledge.extract_knowledge_units_l2_session import (  # noqa: E402
    _evidence_supported,
)
from personal_knowledge.application.knowledge.merge_l2_into_canonical import (  # noqa: E402
    find_match,
    load_current_canonical,
)
from personal_knowledge.application.knowledge.build_canonical_knowledge_units import (  # noqa: E402
    _canonical_id,
)

BACKUP_DIR = VAR_DIR / "backups"
SALVAGE_RUN_ID = "salvage_v1_backlog"
MERGE_REASON = "salvage_import"
GLOBAL_PROBE_LEN = 12
DRY_SAMPLE_SIZE = 500


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _scope_for_role(role: str | None) -> str:
    """canonical_messages.role → knowledge_units.evidence_scope（CHECK 约束内）。"""
    if role == "assistant":
        return "assistant"
    if role == "user":
        return "user"
    return "system"  # system/tool/developer/其他 → system


# ---------------------------------------------------------------- 消息索引

def load_message_index(canonical_db: Path) -> dict:
    """把 canonical 消息一次读入内存：by_session 分桶 + by_id + 全局列表。"""
    con = sqlite3.connect(f"file:{canonical_db.as_posix()}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT m.canonical_message_id, m.canonical_session_id, m.role, m.content, s.agent "
        "FROM canonical_messages m "
        "LEFT JOIN canonical_sessions s ON s.canonical_session_id = m.canonical_session_id"
    ).fetchall()
    con.close()
    by_session: dict[str, list[dict]] = defaultdict(list)
    by_id: dict[str, dict] = {}
    all_msgs: list[dict] = []
    for mid, sid, role, content, agent in rows:
        msg = {
            "mid": mid,
            "sid": sid or "",
            "role": role or "",
            "agent": agent or "",
            "content": content or "",
        }
        by_session[msg["sid"]].append(msg)
        by_id[mid] = msg
        all_msgs.append(msg)
    return {"by_session": dict(by_session), "by_id": by_id, "all": all_msgs}


def _best_in_messages(quote: str, msgs: list[dict]) -> dict | None:
    """多命中取"精确包含优先、内容最长"（同 L2 _best_message_for_quote 打分）。"""
    best = None
    best_key = None
    for m in msgs:
        content = m["content"]
        if not _evidence_supported(quote, content):
            continue
        key = (2 if quote in content else 1, len(content))
        if best_key is None or key > best_key:
            best_key = key
            best = m
    return best


def global_search(quote: str, all_msgs: list[dict]) -> dict | None:
    """全局兜底：先用 quote 前 12 字粗筛候选（未命中再用后 12 字），再精确判定。

    启发式：_evidence_supported 允许任一 ≥10 字连续片段命中，而粗筛要求
    首/尾 12 字逐字出现；首尾都残缺的 quote 会被漏判为 unrepairable。
    一次性迁移可接受，dry-run 报告里体现 unrepairable 规模。
    """
    q = quote.strip()
    if not q:
        return None
    probes = [q[:GLOBAL_PROBE_LEN]]
    if len(q) > GLOBAL_PROBE_LEN:
        probes.append(q[-GLOBAL_PROBE_LEN:])
    for probe in probes:
        candidates = [m for m in all_msgs if probe in m["content"]]
        hit = _best_in_messages(quote, candidates)
        if hit:
            return hit
    return None


# ---------------------------------------------------------------- Phase 1

def load_v1_units(db: Path) -> list[dict]:
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT unit_id, run_id, unit_type, subject, question, answer, confidence, "
        "evidence_quote, source_session_id, source_message_ref, source_agent, evidence_scope "
        "FROM knowledge_units WHERE unit_id LIKE 'v1|%' AND status='staging'"
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def plan_repairs(units: list[dict], index: dict, *, verbose: bool = True) -> list[dict]:
    """对每条 unit 出修复计划。action ∈ already_ok / repaired_session /
    repaired_global / unrepairable。"""
    plans: list[dict] = []
    global_cache: dict[str, dict | None] = {}  # quote → 全局搜索结果（多 unit 共享）
    t0 = time.time()
    for i, u in enumerate(units):
        if verbose and i and i % 2000 == 0:
            print(f"  [phase1] {i}/{len(units)} elapsed={time.time() - t0:.0f}s", flush=True)
        quote = u["evidence_quote"] or ""
        plan = {"unit_id": u["unit_id"], "run_id": u["run_id"], "action": "unrepairable"}
        if quote.strip():
            orig = index["by_id"].get(u["source_message_ref"] or "")
            if orig and _evidence_supported(quote, orig["content"]):
                plan["action"] = "already_ok"
            else:
                hit = _best_in_messages(
                    quote, index["by_session"].get(u["source_session_id"] or "", [])
                )
                if hit:
                    plan["action"] = "repaired_session"
                else:
                    if quote in global_cache:
                        hit = global_cache[quote]
                    else:
                        hit = global_search(quote, index["all"])
                        global_cache[quote] = hit
                    if hit:
                        plan["action"] = "repaired_global"
                if plan["action"] in ("repaired_session", "repaired_global"):
                    plan["new_ref"] = hit["mid"]
                    plan["new_sid"] = hit["sid"]
                    plan["new_agent"] = hit["agent"]
                    plan["new_scope"] = _scope_for_role(hit["role"])
        plans.append(plan)
    if verbose:
        print(f"  [phase1] done {len(units)}/{len(units)} elapsed={time.time() - t0:.0f}s", flush=True)
    return plans


def apply_repairs(con: sqlite3.Connection, plans: list[dict]) -> dict:
    """在调用方事务里执行 Phase 1 的 ref 修复 UPDATE，并同步 evidence 链接。

    返回 {"refs_repaired": int, "evidence_links_added": int}。
    """
    changed = 0
    evidence_added = 0
    for p in plans:
        if p["action"] not in ("repaired_session", "repaired_global"):
            continue
        changed += con.execute(
            "UPDATE knowledge_units SET source_message_ref=?, source_session_id=?, "
            "source_agent=?, evidence_scope=? WHERE unit_id=?",
            (p["new_ref"], p["new_sid"], p["new_agent"], p["new_scope"], p["unit_id"]),
        ).rowcount
        evidence_added += con.execute(
            "INSERT OR IGNORE INTO knowledge_unit_evidence (unit_id, evidence_ref) VALUES (?,?)",
            (p["unit_id"], p["new_ref"]),
        ).rowcount
    return {"refs_repaired": changed, "evidence_links_added": evidence_added}


# ---------------------------------------------------------------- Phase 2

def load_membership(db: Path) -> tuple[dict[str, list[tuple[str, str]]], dict[str, list[str]]]:
    """member_unit_id → [(canonical_unit_id, canonical_status)]，及反向映射。"""
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT m.member_unit_id, m.canonical_unit_id, c.status "
        "FROM canonical_unit_members m "
        "JOIN canonical_knowledge_units c ON c.canonical_unit_id = m.canonical_unit_id"
    ).fetchall()
    con.close()
    member_canons: dict[str, list[tuple[str, str]]] = defaultdict(list)
    canon_members: dict[str, list[str]] = defaultdict(list)
    for uid, cid, cstatus in rows:
        member_canons[uid].append((cid, cstatus))
        canon_members[cid].append(uid)
    return dict(member_canons), dict(canon_members)


def classify_phase2(
    units: list[dict],
    plans: list[dict],
    member_canons: dict[str, list[tuple[str, str]]],
) -> dict[str, list[dict]]:
    """按修复结果 + 现有链接把 unit 分到 phase2 桶。"""
    plan_by_id = {p["unit_id"]: p for p in plans}
    buckets: dict[str, list[dict]] = {
        "heal": [],           # repairable 且已是 current canonical 成员
        "linked_other": [],   # repairable 但只挂在非 current canonical（不动，报告）
        "unlinked": [],       # repairable 且无任何 canonical 链接 → attach-or-create
        "unrepairable": [],   # → rejected
        "skipped_empty": [],  # unlinked 但 subject/answer 空，无法建 canonical（同 merge_l2）
    }
    for u in units:
        p = plan_by_id[u["unit_id"]]
        if p["action"] == "unrepairable":
            buckets["unrepairable"].append(u)
            continue
        canons = member_canons.get(u["unit_id"], [])
        if any(st == "current" for _cid, st in canons):
            buckets["heal"].append(u)
        elif canons:
            buckets["linked_other"].append(u)
        elif not (u.get("answer") or "").strip() or not (u.get("subject") or "").strip():
            buckets["skipped_empty"].append(u)
        else:
            buckets["unlinked"].append(u)
    return buckets


def apply_phase2(
    con: sqlite3.Connection,
    buckets: dict[str, list[dict]],
    canon_by_type: dict[str, list[dict]],
) -> dict:
    """在调用方事务里执行 heal / attach-or-create / reject，返回计数。"""
    now = _utc_now()
    stats = Counter()

    # unrepairable → rejected
    for u in buckets["unrepairable"]:
        stats["units_rejected"] += con.execute(
            "UPDATE knowledge_units SET status='rejected' WHERE unit_id=?",
            (u["unit_id"],),
        ).rowcount

    # heal：已是 current canonical 成员 → 直接置 current
    for u in buckets["heal"]:
        stats["units_healed"] += con.execute(
            "UPDATE knowledge_units SET status='current' WHERE unit_id=?",
            (u["unit_id"],),
        ).rowcount

    # attach-or-create
    for u in buckets["unlinked"]:
        match = find_match(u, canon_by_type)
        if match:
            con.execute(
                "INSERT OR IGNORE INTO canonical_unit_members "
                "(canonical_unit_id, member_unit_id) VALUES (?,?)",
                (match["canonical_unit_id"], u["unit_id"]),
            )
            con.execute(
                "UPDATE knowledge_units SET status='current' WHERE unit_id=?",
                (u["unit_id"],),
            )
            stats["units_attached"] += 1
            continue

        cid = _canonical_id(u["subject"], u["unit_type"], u["answer"])
        existing = con.execute(
            "SELECT canonical_unit_id FROM canonical_knowledge_units WHERE canonical_unit_id=?",
            (cid,),
        ).fetchone()
        if existing:
            con.execute(
                "UPDATE canonical_knowledge_units SET status='current' WHERE canonical_unit_id=?",
                (cid,),
            )
            stats["canonical_reactivated"] += 1
        else:
            conf = float(u.get("confidence") or 0.7)
            con.execute(
                "INSERT INTO canonical_knowledge_units "
                "(canonical_unit_id, subject, unit_type, question, answer, confidence, "
                "lifecycle, status, version, run_id, merge_reason, supersedes_id, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    cid,
                    u["subject"][:200],
                    u["unit_type"],
                    (u.get("question") or "")[:500],
                    (u.get("answer") or "")[:2000],
                    conf,
                    "current",
                    "current",
                    1,
                    SALVAGE_RUN_ID,
                    MERGE_REASON,
                    None,
                    now,
                ),
            )
            # 同 run 后续 unit 可挂到这个新 canonical（同 merge_l2）
            canon_by_type.setdefault(u["unit_type"] or "", []).append(
                {
                    "canonical_unit_id": cid,
                    "subject": u["subject"],
                    "unit_type": u["unit_type"],
                    "answer": u["answer"],
                    "confidence": conf,
                }
            )
            stats["canonical_created"] += 1
        con.execute(
            "INSERT OR IGNORE INTO canonical_unit_members "
            "(canonical_unit_id, member_unit_id) VALUES (?,?)",
            (cid, u["unit_id"]),
        )
        con.execute(
            "UPDATE knowledge_units SET status='current' WHERE unit_id=?",
            (u["unit_id"],),
        )
        stats["units_merged_new"] += 1

    return dict(stats)


# ---------------------------------------------------------------- Phase 3

def plan_phase3(db: Path) -> list[str]:
    """current 且无 current 成员、且成员含本批 v1 unit 的 canonical（影子行）。"""
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT c.canonical_unit_id FROM canonical_knowledge_units c "
        "WHERE c.status='current' "
        "AND EXISTS (SELECT 1 FROM canonical_unit_members m "
        "            JOIN knowledge_units k ON k.unit_id=m.member_unit_id "
        "            WHERE m.canonical_unit_id=c.canonical_unit_id "
        "            AND k.unit_id LIKE 'v1|%') "
        "AND NOT EXISTS (SELECT 1 FROM canonical_unit_members m "
        "                JOIN knowledge_units k ON k.unit_id=m.member_unit_id "
        "                WHERE m.canonical_unit_id=c.canonical_unit_id "
        "                AND k.status='current')"
    ).fetchall()
    con.close()
    return [r[0] for r in rows]


def apply_phase3(con: sqlite3.Connection) -> int:
    """Phase 2 落库后在同事务里清理剩余影子行，返回 rejected 行数。"""
    cur = con.execute(
        "UPDATE canonical_knowledge_units SET status='rejected' "
        "WHERE status='current' "
        "AND EXISTS (SELECT 1 FROM canonical_unit_members m "
        "            JOIN knowledge_units k ON k.unit_id=m.member_unit_id "
        "            WHERE m.canonical_unit_id=canonical_knowledge_units.canonical_unit_id "
        "            AND k.unit_id LIKE 'v1|%') "
        "AND NOT EXISTS (SELECT 1 FROM canonical_unit_members m "
        "                JOIN knowledge_units k ON k.unit_id=m.member_unit_id "
        "                WHERE m.canonical_unit_id=canonical_knowledge_units.canonical_unit_id "
        "                AND k.status='current')"
    )
    return cur.rowcount


# ---------------------------------------------------------------- 备份 / 编排

def backup_unified_db(unified_db: Path) -> tuple[Path | None, str]:
    """--write 前备份；当天（UTC）已有备份则不重复拷贝。"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    existing = sorted(BACKUP_DIR.glob(f"personal_system_{today}T*.sqlite"))
    if existing:
        return existing[-1], "exists"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = BACKUP_DIR / f"personal_system_{stamp}.sqlite"
    shutil.copy2(unified_db, dest)
    return dest, "created"


def _ensure_salvage_run(con: sqlite3.Connection) -> None:
    """canonical_knowledge_units.run_id 有 FK，先落一行 build run。"""
    con.execute(
        "INSERT OR IGNORE INTO knowledge_build_runs "
        "(run_id, run_type, generated_at, source_build_id, input_hash, status, stats_json) "
        "VALUES (?,?,?,?,?,?,?)",
        (SALVAGE_RUN_ID, "merge", _utc_now(), "salvage_v1_backlog",
         "salvage_v1_backlog", "current", "{}"),
    )


def estimate_new_canonical(
    unlinked: list[dict],
    canon_by_type: dict[str, list[dict]],
    sample_size: int,
) -> dict:
    """抽样跑 find_match 估算 attach / 新建 canonical 比例。"""
    if not unlinked:
        return {"sample": 0, "attach": 0, "new": 0, "est_attach": 0, "est_new_canonical": 0}
    sample = random.Random(42).sample(unlinked, min(sample_size, len(unlinked)))
    attach = sum(1 for u in sample if find_match(u, canon_by_type))
    rate = attach / len(sample)
    return {
        "sample": len(sample),
        "attach": attach,
        "new": len(sample) - attach,
        "est_attach": round(rate * len(unlinked)),
        "est_new_canonical": round((1 - rate) * len(unlinked)),
    }


def run(
    db: Path,
    canonical_db: Path,
    *,
    write: bool = False,
    sample_size: int = DRY_SAMPLE_SIZE,
    verbose: bool = True,
) -> dict:
    timings: dict[str, float] = {}
    t_all = time.time()

    t = time.time()
    index = load_message_index(canonical_db)
    timings["load_message_index"] = time.time() - t
    if verbose:
        print(f"[load] canonical 消息 {len(index['all'])} 条，{timings['load_message_index']:.1f}s")

    t = time.time()
    units = load_v1_units(db)
    timings["load_units"] = time.time() - t
    if verbose:
        print(f"[load] v1| staging units {len(units)} 条")

    t = time.time()
    plans = plan_repairs(units, index, verbose=verbose)
    timings["phase1_repair_scan"] = time.time() - t

    t = time.time()
    member_canons, canon_members = load_membership(db)
    buckets = classify_phase2(units, plans, member_canons)
    timings["phase2_classify"] = time.time() - t

    t = time.time()
    current_canonical = load_current_canonical(db)
    canon_by_type: dict[str, list[dict]] = defaultdict(list)
    for c in current_canonical:
        canon_by_type[c["unit_type"] or ""].append(c)
    timings["load_canonical"] = time.time() - t
    if verbose:
        print(f"[load] current canonical {len(current_canonical)} 条")

    action_counts = Counter(p["action"] for p in plans)
    by_run: dict[str, Counter] = defaultdict(Counter)
    for p in plans:
        by_run[p["run_id"]]["repairable" if p["action"] != "unrepairable" else "unrepairable"] += 1

    report: dict = {
        "generated_at": _utc_now(),
        "mode": "write" if write else "dry-run",
        "units_total": len(units),
        "distinct_quotes": len({u["evidence_quote"] for u in units}),
        "phase1": {
            "already_ok": action_counts["already_ok"],
            "repaired_session": action_counts["repaired_session"],
            "repaired_global": action_counts["repaired_global"],
            "unrepairable": action_counts["unrepairable"],
            "by_run": {k: dict(v) for k, v in sorted(by_run.items())},
        },
        "phase2": {
            "heal_linked_current": len(buckets["heal"]),
            "linked_non_current_untouched": len(buckets["linked_other"]),
            "unlinked_attach_or_create": len(buckets["unlinked"]),
            "skipped_empty_untouched": len(buckets["skipped_empty"]),
            "units_rejected": len(buckets["unrepairable"]),
        },
    }

    if write:
        backup, how = backup_unified_db(db)
        report["backup"] = {"path": str(backup), "status": how}
        if verbose:
            print(f"[backup] {how}: {backup}")
        t = time.time()
        con = sqlite3.connect(str(db), timeout=60)
        try:
            con.execute("BEGIN")
            _ensure_salvage_run(con)
            applied: dict = apply_repairs(con, plans)
            applied.update(apply_phase2(con, buckets, canon_by_type))
            applied["canonical_rejected_phase3"] = apply_phase3(con)
            con.commit()
        except Exception:
            con.rollback()
            con.close()
            raise
        con.close()
        timings["write_transaction"] = time.time() - t
        report["applied"] = applied
    else:
        t = time.time()
        con_ro = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        existing_evidence = {
            (r[0], r[1])
            for r in con_ro.execute(
                "SELECT unit_id, evidence_ref FROM knowledge_unit_evidence "
                "WHERE unit_id LIKE 'v1|%'"
            )
        }
        con_ro.close()
        report["phase1"]["est_evidence_links_new"] = sum(
            1
            for p in plans
            if p["action"] in ("repaired_session", "repaired_global")
            and (p["unit_id"], p["new_ref"]) not in existing_evidence
        )
        timings["evidence_estimate"] = time.time() - t

        t = time.time()
        est = estimate_new_canonical(buckets["unlinked"], canon_by_type, sample_size)
        timings["phase2_sample_estimate"] = time.time() - t
        report["phase2"]["sample_estimate"] = est

        t = time.time()
        shadow = plan_phase3(db)
        repairable_ids = {
            u["unit_id"]
            for key in ("heal", "unlinked")
            for u in buckets[key]
        }
        will_heal = sum(
            1 for cid in shadow if any(m in repairable_ids for m in canon_members.get(cid, []))
        )
        timings["phase3_estimate"] = time.time() - t
        report["phase3"] = {
            "shadow_canonical_current_no_current_members": len(shadow),
            "est_healed": will_heal,
            "est_rejected": len(shadow) - will_heal,
        }

    timings["total"] = time.time() - t_all
    report["timings_sec"] = {k: round(v, 1) for k, v in timings.items()}
    return report


def print_report(report: dict) -> None:
    p1, p2 = report["phase1"], report["phase2"]
    print(f"\n== salvage_v1_backlog {report['mode']} 报告 ==")
    print(f"  units 总数: {report['units_total']}（distinct quotes {report['distinct_quotes']}）")
    print("[phase1] 证据链修复")
    print(f"  already_ok（原 ref 本就支持 quote）: {p1['already_ok']}")
    print(f"  repaired_session（同 session 他消息命中）: {p1['repaired_session']}")
    print(f"  repaired_global（全局兜底命中）: {p1['repaired_global']}")
    print(f"  unrepairable: {p1['unrepairable']}")
    if "est_evidence_links_new" in p1:
        print(f"  预计新增 knowledge_unit_evidence 链接: {p1['est_evidence_links_new']}")
    print("  按 run_id 分布:")
    for run_id, c in p1["by_run"].items():
        print(f"    {run_id}: repairable={c.get('repairable', 0)} unrepairable={c.get('unrepairable', 0)}")
    print("[phase2] 并账")
    print(f"  heal（已链接 current canonical，置 current）: {p2['heal_linked_current']}")
    print(f"  unlinked（待 attach-or-create）: {p2['unlinked_attach_or_create']}")
    print(f"  仅挂非 current canonical（不动，仅报告）: {p2['linked_non_current_untouched']}")
    print(f"  subject/answer 为空（不动，仅报告）: {p2['skipped_empty_untouched']}")
    print(f"  rejected units（unrepairable）: {p2['units_rejected']}")
    if "sample_estimate" in p2:
        est = p2["sample_estimate"]
        print(
            f"  抽样 {est['sample']} 估算: attach={est['attach']} new={est['new']} → "
            f"预计 attach {est['est_attach']}，新建 canonical {est['est_new_canonical']}"
        )
    if "phase3" in report:
        p3 = report["phase3"]
        print("[phase3] 清理预估")
        print(f"  影子 canonical（current 且无 current 成员）: {p3['shadow_canonical_current_no_current_members']}")
        print(f"  预计愈合: {p3['est_healed']}  预计 rejected: {p3['est_rejected']}")
    if "applied" in report:
        print(f"[applied] {report['applied']}")
        print(f"[backup] {report['backup']['status']}: {report['backup']['path']}")
    print(f"[timings] {report['timings_sec']}")
    if report["mode"] == "dry-run":
        print("\n(dry-run：未做任何修改；加 --write 执行)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="只出报告，不写（默认）")
    mode.add_argument("--write", action="store_true", help="实际写入（先备份 UNIFIED_DB）")
    parser.add_argument("--db", type=Path, default=UNIFIED_DB)
    parser.add_argument("--canonical-db", type=Path, default=AGENT_CONVERSATIONS_DB)
    parser.add_argument("--sample-size", type=int, default=DRY_SAMPLE_SIZE,
                        help="dry-run 估算新 canonical 数的抽样大小")
    args = parser.parse_args(argv)

    report = run(args.db, args.canonical_db, write=bool(args.write), sample_size=args.sample_size)
    print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
