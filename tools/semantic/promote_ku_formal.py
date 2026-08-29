"""Promote KU staging rows into the formal knowledge layer (UNIFIED_DB).

Idempotent: run_id and every unit_id are derived deterministically from the
staging content, so re-runs after incremental staging refreshes upsert in
place instead of duplicating. Creates:
  - one knowledge_build_runs row (run_type='promote')
  - knowledge_units rows (status='current', formal v1| unit ids,
    supersedes_id translated from staging ids)
  - knowledge_unit_evidence rows
  - canonical_knowledge_units + members (safe exact-normalized grouping only;
    near-duplicates stay separate pending review)
  - knowledge_index_versions row (status='candidate' — serving switch is a
    separate decision; the MVP surface keeps its JSON registry)

Run from repo root:  python tools/semantic/promote_ku_formal.py [--dry-run]
"""
import hashlib, json, re, sqlite3, sys, time

STAGING = "var/db/semantic_ku_staging.sqlite"
UNIFIED = "var/db/personal_system.sqlite"
REGISTRY = "var/db/semantic_index_registry.json"


def h(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def norm_answer(a):
    return re.sub(r"\s+", "", (a or "").lower())


def main():
    dry = "--dry-run" in sys.argv
    st = sqlite3.connect(f"file:{STAGING}?mode=ro", uri=True)
    units = st.execute(
        "select unit_id, unit_type, question, answer, confidence, lifecycle, "
        "source_session_id, supersedes_id, status from knowledge_units_staging "
        "order by unit_id").fetchall()
    evidence = st.execute(
        "select s.unit_id, e.evidence_ref from knowledge_unit_evidence_staging e "
        "join knowledge_units_staging s on s.unit_id=e.unit_id").fetchall()
    if not units:
        print("staging empty — nothing to promote")
        return

    content_hash = h(json.dumps([[u[0], u[3], u[1], u[5]] for u in units]))
    run_id = "pm_" + content_hash[:16]
    # formal unit ids derive from staging ids only (run-independent), so
    # incremental staging refreshes keep the same identity across runs
    idmap = {u[0]: "v1|" + u[0][4:36] for u in units}

    if dry:
        print(f"[dry-run] run={run_id} units={len(units)} evidence={len(evidence)}")
        return

    uni = sqlite3.connect(UNIFIED)
    uni.execute("PRAGMA foreign_keys=ON")
    cur = uni.cursor()
    # full idempotent refresh: formal unit ids are derived from staging ids
    # (run-independent), so re-promotes upsert; wipe any previous promote-run
    # data first so removed/retyped rows cannot linger
    for (pr,) in cur.execute(
            "select run_id from knowledge_build_runs where run_type='promote'").fetchall():
        cur.execute("delete from knowledge_index_versions where build_id=?", (pr,))
        cur.execute("delete from canonical_unit_members where member_unit_id in "
                    "(select unit_id from knowledge_units where run_id=?)", (pr,))
        cur.execute("delete from canonical_knowledge_units where run_id=?", (pr,))
        cur.execute("delete from knowledge_unit_evidence where unit_id in "
                    "(select unit_id from knowledge_units where run_id=?)", (pr,))
        cur.execute("delete from knowledge_units where run_id=?", (pr,))
        cur.execute("delete from knowledge_build_runs where run_id=?", (pr,))
    cur.execute(
        "insert or replace into knowledge_build_runs "
        "(run_id, run_type, generated_at, source_build_id, input_hash, prompt_version, "
        " schema_version, model, embedding_model, config_hash, git_sha, dataset_hash, "
        " status, stats_json) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, "promote", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
         None, content_hash, "mvp-staging-v1", "v1", "hy3", "bge-small-zh-v1.5",
         None, None, None, "current",
         json.dumps({"units": len(units), "evidence": len(evidence), "source": "mvp_staging"})))

    n_sup = n_dangling = 0
    for u in units:
        (stg_id, utype, question, answer, conf, lifecycle, src_sid, supersedes, _status) = u
        formal_sup = None
        if supersedes:
            # ku_facts.supersedes stores the successor's fact_key (kc|...);
            # staging unit ids are stg|sha256(fact_key), so the target is
            # computable without touching the source DB
            target = supersedes if supersedes.startswith("stg|") else \
                "stg|" + hashlib.sha256(supersedes.encode("utf-8")).hexdigest()
            formal_sup = idmap.get(target)
            if formal_sup:
                n_sup += 1
            else:
                n_dangling += 1
        cur.execute(
            "insert or replace into knowledge_units "
            "(unit_id, run_id, unit_type, subject, question, answer, confidence, "
            " evidence_quote, lifecycle, source_session_id, source_message_ref, "
            " source_agent, status, version, supersedes_id, created_at) "
            "values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (idmap[stg_id], run_id, utype, answer[:60], question or "", answer, conf,
             answer[:200], lifecycle, src_sid, None, "mvp", "current", 1, formal_sup,
             time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
    for stg_id, ref in evidence:
        cur.execute(
            "insert or replace into knowledge_unit_evidence (unit_id, evidence_ref) values (?,?)",
            (idmap[stg_id], ref))

    # canonical layer: safe exact-normalized grouping over current units only
    current = [u for u in units if u[5] == "current"]
    groups = {}
    for u in current:
        groups.setdefault((u[1], norm_answer(u[3])), []).append(u)
    n_can = n_merged = 0
    for (utype, na), members in groups.items():
        cu = "cu|" + h(f"{utype}|{na}")[:32]
        rep = members[0]
        cur.execute(
            "insert or replace into canonical_knowledge_units "
            "(canonical_unit_id, subject, unit_type, question, answer, confidence, "
            " lifecycle, status, version, run_id, merge_reason, created_at) "
            "values (?,?,?,?,?,?,?,?,?,?,?,?)",
            (cu, rep[3][:60], utype, rep[2] or "", rep[3], rep[4],
             "current", "current", len(members), run_id,
             "exact_norm_dup" if len(members) > 1 else "single",
             time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
        for m in members:
            cur.execute(
                "insert or replace into canonical_unit_members (canonical_unit_id, member_unit_id) "
                "values (?,?)", (cu, idmap[m[0]]))
        n_can += 1
        n_merged += max(0, len(members) - 1)

    # index version (candidate; formal serving switch is a separate decision)
    try:
        reg = json.load(open(REGISTRY))
        build = [b for b in reg["builds"] if b["status"] == "active"]
        if build:
            b = build[0]
            cur.execute(
                "insert or replace into knowledge_index_versions "
                "(version_id, build_id, collection_name, unit_count, status, created_at, checksum) "
                "values (?,?,?,?,?,?,?)",
                ("kiv_" + b["build_id"], run_id, b["collection"], b["docs"], "candidate",
                 time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), h(json.dumps(b, sort_keys=True))))
    except FileNotFoundError:
        print("note: registry not found, index version skipped")

    uni.commit()
    n_units = cur.execute("select count(*) from knowledge_units where run_id=?", (run_id,)).fetchone()[0]
    n_ev = cur.execute("select count(*) from knowledge_unit_evidence").fetchone()[0]
    print(f"promoted: run={run_id} units={n_units} evidence={n_ev} "
          f"canonical={n_can} (merged {n_merged} dups) supersedes={n_sup} dangling={n_dangling}")


if __name__ == "__main__":
    main()
