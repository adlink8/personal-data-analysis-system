"""Semantic near-duplicate consolidation for the canonical KU layer.

Owns canonical_knowledge_units + canonical_unit_members: wipes rows written
by promote runs and rebuilds them from the current knowledge_units with
two-stage grouping:
  1. exact-normalized groups (same as promote: whitespace-stripped lowercase)
  2. semantic merge: group representatives (longest answer per exact group)
     with cosine >= --threshold (default 0.95) and identical unit_type are
     unified; the longest answer becomes the canonical answer

Embedding is local (bge-small-zh via personal_knowledge.core.local_embed);
no network, no cost. Pairs between 0.90 and the threshold are counted and
reported but NOT merged (review material).

Run from repo root:
  python tools/semantic/dedup_canonical_ku.py [--threshold 0.95] [--dry-run]
"""
import hashlib, json, sqlite3, sys, time

import numpy as np

import os
# runtime_config 默认指向 C 盘残缺缓存（同 build_semantic_vector_store 的兜底）
os.environ.setdefault("PERSONAL_DATA_EMBED_MODEL_PATH", r"D:\models\bge-small-zh-v1.5")

UNIFIED = "var/db/personal_system.sqlite"


def h(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def norm_answer(a):
    return re.sub(r"\s+", "", (a or "").lower())


import re  # noqa: E402  (kept late to mirror promote's import style)


def main():
    threshold = 0.95
    if "--threshold" in sys.argv:
        threshold = float(sys.argv[sys.argv.index("--threshold") + 1])
    dry = "--dry-run" in sys.argv

    from personal_knowledge.core import local_embed

    uni = sqlite3.connect(f"file:{UNIFIED}?mode=ro", uri=True)
    rows = uni.execute(
        "select unit_id, unit_type, answer from knowledge_units "
        "where lifecycle='current' order by unit_id").fetchall()
    print(f"current units: {len(rows)}")

    # stage 1: exact-normalized groups
    exact = {}
    for uid, utype, ans in rows:
        exact.setdefault((utype, norm_answer(ans)), []).append((uid, ans))

    # representative per exact group = longest answer
    reps = []
    for (utype, _na), members in exact.items():
        best = max(members, key=lambda m: len(m[1]))
        reps.append((utype, best[1], len(members)))
    print(f"exact-normalized groups: {len(reps)}")

    # stage 2: semantic merge of representatives
    ok, msg, dim = local_embed.verify_model()
    if not ok:
        print(f"[error] embedding model unavailable: {msg}", file=sys.stderr)
        return 1
    texts = [r[1] for r in reps]
    print(f"embedding {len(texts)} representatives ({dim}d, local) ...", flush=True)
    emb = np.array(local_embed.embed_batch(texts), dtype=np.float32)
    emb /= np.clip(np.linalg.norm(emb, axis=1, keepdims=True), 1e-9, None)

    parent = list(range(len(reps)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    # identifier-token guard (build_merge_layer 防误并思想): a semantic match
    # with any identifier token that the representative lacks is a DIFFERENT
    # entity (e.g. repo deep-read vs deep-reads) — never merge those
    TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_\-.\\/]{3,}")
    STOP = {"this", "that", "with", "from", "have", "been", "were", "into", "your",
            "their", "about", "which", "would", "could", "should", "there", "these",
            "those", "then", "when", "what", "where", "will", "also", "just", "like",
            "more", "some", "than", "them", "they", "file", "line", "text", "error",
            "content", "tool", "path"}

    def toks(i):
        return {t.lower() for t in TOKEN_RE.findall(reps[i][1])
                if not t.lower().isdigit() and t.lower() not in STOP}

    rep_toks = [toks(i) for i in range(len(reps))]

    merged_pairs = flagged = ident_conflict = 0
    chunk = 512
    for i in range(0, len(reps), chunk):
        sims = emb[i:i + chunk] @ emb.T
        for r in range(sims.shape[0]):
            gi = i + r
            for j in range(gi + 1, len(reps)):
                s = float(sims[r, j])
                if s < 0.90:
                    continue
                same_type = reps[gi][0] == reps[j][0]
                if s >= threshold and same_type:
                    if rep_toks[j] - rep_toks[gi] or rep_toks[gi] - rep_toks[j]:
                        ident_conflict += 1
                        continue
                    union(gi, j)
                    merged_pairs += 1
                elif same_type:
                    flagged += 1
    print(f"semantic pairs >= {threshold} (same type, merged): {merged_pairs}; "
          f"0.90~{threshold} flagged (not merged): {flagged}; "
          f"identifier conflicts blocked: {ident_conflict}")

    groups = {}
    for idx in range(len(reps)):
        groups.setdefault(find(idx), []).append(idx)
    final_groups = list(groups.values())
    n_can = sum(1 for g in final_groups)
    n_absorbed = sum(len(g) - 1 for g in final_groups)
    print(f"final canonical groups: {n_can} (absorbed {n_absorbed} duplicate representatives)")
    examples = [g for g in final_groups if len(g) > 1][:5]
    for g in examples:
        print(f"  merge group ({reps[g[0]][0]}, {len(g)} reps):")
        for idx in g[:3]:
            print(f"    - {reps[idx][1][:70]}")
    if dry:
        print("[dry-run] canonical layer untouched")
        return 0

    # rewrite canonical layer (promote-run rows only — nothing else writes here)
    uni_w = sqlite3.connect(UNIFIED)
    cur = uni_w.cursor()
    cur.execute("PRAGMA foreign_keys=ON")
    promote_runs = [r[0] for r in cur.execute(
        "select run_id from knowledge_build_runs where run_type='promote'").fetchall()]
    for pr in promote_runs:
        cur.execute("delete from canonical_unit_members where member_unit_id in "
                    "(select unit_id from knowledge_units where run_id=?)", (pr,))
        cur.execute("delete from canonical_knowledge_units where run_id=?", (pr,))
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    n_written = 0
    for g in final_groups:
        utype = reps[g[0]][0]
        rep_ans = max((reps[i][1] for i in g), key=len)
        members = [u for i in g for u in exact[(utype, norm_answer(reps[i][1]))]]
        reason = ("semantic_%.2f_x%d" % (threshold, len(g))) if len(g) > 1 else \
                 ("exact_norm_dup" if len(members) > 1 else "single")
        cu = "cu|" + h(f"{utype}|{norm_answer(rep_ans)}")[:32]
        cur.execute(
            "insert or replace into canonical_knowledge_units "
            "(canonical_unit_id, subject, unit_type, question, answer, confidence, "
            " lifecycle, status, version, run_id, merge_reason, created_at) "
            "values (?,?,?,?,?,?,?,?,?,?,?,?)",
            (cu, rep_ans[:60], utype, "", rep_ans,
             max((uni.execute("select confidence from knowledge_units where unit_id=?",
                              (m[0],)).fetchone() or (0.5,))[0] for m in members),
             "current", "current", 1, promote_runs[0] if promote_runs else "pm_orphan",
             reason, now))
        for m in members:
            cur.execute(
                "insert or replace into canonical_unit_members "
                "(canonical_unit_id, member_unit_id) values (?,?)", (cu, m[0]))
        n_written += 1
    uni_w.commit()
    print(f"canonical written: {n_written} rows (from {len(rows)} current units)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
