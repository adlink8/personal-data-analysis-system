# 正式住所: tools/semantic/mvp_semantic_compress.py（自 tmp/mvp_semantic_compress.py 迁入, 2026-08-29; 与 export_ku_staging.py 同居）。
# 运行: python tools/semantic/mvp_semantic_compress.py pilot|scale|report（pilot/scale 仍需 pi 内核在跑 + PI_KERNEL_INTERNAL_CAPABILITY 环境变量; report 纯只读; 报告/会话清单等运行数据仍在 tmp/）。
"""MVP semantic compression pilot v3: strip injections, map-reduce large
sessions, per-chunk fact collection, size-adaptive visible budget.

Operator-run offline pilot (user-authorized). Reads the canonical DB
read-only, calls the pi kernel (purpose=conversation_summary) once per
session (small) or once per chunk + one merge call (large), stores cards +
chunk summaries + fact ops into var/db/semantic_mvp_v3.sqlite, then (mode
``report``) computes the v1-vs-v3 recall report. Never writes to the
canonical DB.

Fixes vs v2 (independent verifier findings):
 M1. consolidate() similarity supersede branch now actually works: the
     normalized 40-char prefix is computed once (norm_prefix()) and stored
     in ku_facts.norm_prefix at insert time, so the SQL compare is exact
     instead of a divergent substr() (40 lowercased de-punctuated chars vs 36 raw);
 M2. every fact's evidence_ids are validated against the message ids
     actually sent to the model; bare hex ids missing the ``v2|cm|``
     prefix are repaired when the prefixed form matches, anything else is
     dropped (no fabricated provenance can enter the DB);
 L4. a failed session rolls back its partial chunk_summaries instead of
     leaking them into the next session's commit.

Modes: ``pilot`` re-runs the 12-session pilot into v3; ``retry <sid...>``
re-attempts failed sessions; ``scale [limit]`` compresses every visible
session (>=200 stripped chars, not yet carded) with 3 concurrent workers
and a hard cost cap (env PK_MVP_COST_CAP, default ¥8); ``report`` recomputes
the recall report from the v1 and v3 MVP DBs.
"""
import json, re, sqlite3, sys, time

sys.path.insert(0, "src")
from personal_knowledge.core.canonical_visibility import canonical_projection_predicate

CANON = "file:data/canonical/agent/structured/db/agent_conversations.sqlite?mode=ro"
V1_DB = "var/db/semantic_mvp.sqlite"     # round 1 evidence, never rewritten
V2_DB = "var/db/semantic_mvp_v2.sqlite"  # round 2 evidence, never rewritten
V3_DB = "var/db/semantic_mvp_v3.sqlite"  # round 3: M1/M2 fixes + scale run
REPORT_PATH = "tmp/mvp_recall_report_v3.json"
MIN_SESSION_CHARS = 200  # scale mode: skip trivial sessions below this stripped size
REF_PREFIX = "v2|cm|"    # canonical_message_id prefix the model sometimes drops

SYSTEM_RE = re.compile(r"<system-reminder[^>]*>.*?</system-reminder>", re.S)

# v1 window rules, kept only to reproduce v1's window for the recall report
V1_MAX_MSGS, V1_MSG_CAP, V1_WINDOW_CAP = 60, 500, 22000
# v2 rules
MSG_CAP = 800        # per-message cap inside any window/chunk
WINDOW_CAP = 22000   # single-window budget (small sessions, one call)
CHUNK_CAP = 12000    # per-chunk budget (large sessions, map phase)
MAX_CHUNKS = 24      # hard cap on chunks per session
LARGE_MSGS = 20      # > this many messages => map-reduce path

STOPWORDS = {
    "this", "that", "with", "from", "have", "been", "were", "into", "your",
    "their", "about", "which", "would", "could", "should", "there", "these",
    "those", "then", "when", "what", "where", "will", "also", "just", "like",
    "more", "some", "than", "them", "they", "file", "line", "text", "error",
    "content", "tool", "path",
}
TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_\-.\\/]{3,}")

PROMPT_SMALL = """你是个人知识库的会话压缩器。下面是一个完整会话（可能被截断）。输出严格的 JSON 对象，不要 markdown 代码块、不要任何解释文字。schema:
{{
 "purpose": "不超过80字，这个会话在做什么",
 "conclusions": ["结论1", "..."],
 "entities": ["涉及的项目/工具/系统/人"],
 "artifacts": ["产生的文件/代码/文档/配置"],
 "open_questions": ["未决问题"],
 "facts": [{{"op":"ADD","fact":"一句可独立成立的事实，不超过100字","evidence_ids":["消息id"],"confidence":"high|medium|low"}}],
 "summary_md": "不超过300字的会话纪要"
}}
规则:
- facts 只收可长期成立的事实（偏好/配置变更/结论/决策），不收过程性对话；没有就给空数组
- evidence_ids 必须从下面给出的消息 id 里选，每条 fact 2-5 个
- 信息不足就少写，绝不编造
会话 id: {sid}
消息列表（每行格式 [消息id] [角色] [时间] 内容）:
{window}"""

PROMPT_CHUNK = """你是个人知识库的会话压缩器。下面是一个大会话按顺序切成的 {n_chunks} 块中的第 {i} 块（同一会话的其它内容在其它块里）。输出严格的 JSON 对象，不要 markdown 代码块、不要任何解释文字。schema:
{{
 "chunk_summary": "不超过200字，这一块发生了什么",
 "facts": [{{"op":"ADD","fact":"一句可独立成立的事实，不超过100字","evidence_ids":["消息id"],"confidence":"high|medium|low"}}]
}}
规则:
- facts 只收可长期成立的事实（偏好/配置变更/结论/决策），不收过程性对话；没有就给空数组
- evidence_ids 必须从本块给出的消息 id 里选，每条 fact 2-5 个
- 信息不足就少写，绝不编造
会话 id: {sid}（块 {i}/{n_chunks}）
本块消息列表（每行格式 [消息id] [角色] [时间] 内容）:
{chunk}"""

PROMPT_MERGE = """你是个人知识库的会话压缩器。下面是同一个大会话按顺序排列的各块摘要。请把它们合并成一张最终会话卡。输出严格的 JSON 对象，不要 markdown 代码块、不要任何解释文字。schema:
{{
 "purpose": "不超过80字，这个会话在做什么",
 "conclusions": ["结论1", "..."],
 "entities": ["涉及的项目/工具/系统/人"],
 "artifacts": ["产生的文件/代码/文档/配置"],
 "open_questions": ["未决问题"],
 "facts": [{{"op":"ADD","fact":"一句可独立成立的事实，不超过100字","evidence_ids":["消息id"],"confidence":"high|medium|low"}}],
 "summary_md": "不超过300字的会话纪要"
}}
规则:
- 合并去重、跨块归纳，不要逐块复述
- facts 只收可长期成立的事实；evidence_ids 只能从下面各块摘要 facts 里出现过的消息 id 中选，每条 fact 2-5 个；没有就给空数组
- 信息不足就少写，绝不编造
会话 id: {sid}
各块摘要（按会话顺序）:
{summaries}"""


def strip_injections(text):
    """Fix 1: remove injected system-reminder blocks from raw message content."""
    return SYSTEM_RE.sub("", text or "")


def load_rows(con, f, fp, sid):
    sql = (
        "select m.canonical_message_id, m.role, m.timestamp, m.content "
        "from canonical_messages m join canonical_sessions s "
        "  on s.canonical_session_id = m.canonical_session_id "
        f"where {f} and m.canonical_session_id=? and m.content is not null "
        "order by m.ordinal"
    )
    return con.execute(sql, (*fp, sid)).fetchall()


def build_lines(rows, strip=True):
    """Message -> window line + kept message id. Fix 1 applies here, before the
    MSG_CAP cut. The id list is the validity set for M2 evidence-ref checks."""
    lines, ids = [], []
    for mid, role, ts, content in rows:
        text = strip_injections(content) if strip else (content or "")
        if strip and not text.strip():
            continue  # message was pure injection, carries no information
        lines.append(f"[{mid}] [{role}] [{ts}] {text[:MSG_CAP]}")
        ids.append(mid)
    return lines, ids


def v1_window(con, sid):
    """Exact reproduction of the v1 load_window rules (500/60/22000, no strip)."""
    rows = con.execute(
        "select canonical_message_id, role, timestamp, content from canonical_messages "
        "where canonical_session_id=? and content is not null order by ordinal",
        (sid,),
    ).fetchall()
    lines, n_chars, truncated = [], 0, False
    for mid, role, ts, content in rows[:V1_MAX_MSGS]:
        line = f"[{mid}] [{role}] [{ts}] {(content or '')[:V1_MSG_CAP]}"
        if n_chars + len(line) > V1_WINDOW_CAP:
            truncated = True
            break
        lines.append(line)
        n_chars += len(line)
    if len(rows) > V1_MAX_MSGS:
        truncated = True
    return "\n".join(lines), truncated


def assemble_window(lines, cap):
    parts, n, truncated = [], 0, False
    for line in lines:
        if n + len(line) > cap:
            truncated = True
            break
        parts.append(line)
        n += len(line)
    return "\n".join(parts), truncated


def make_chunks(lines, cap=CHUNK_CAP):
    """Fix 2: greedy ~cap-char chunks in message order."""
    chunks, cur, n = [], [], 0
    for line in lines:
        if cur and n + len(line) > cap:
            chunks.append("\n".join(cur))
            cur, n = [], 0
        cur.append(line)
        n += len(line)
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def sample_chunk_indices(n, max_n=MAX_CHUNKS):
    """Uniform sample of at most max_n chunk indices, first and last kept."""
    if n <= max_n:
        return list(range(n))
    return sorted({round(i * (n - 1) / (max_n - 1)) for i in range(max_n)})


def parse_json(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object found")
    return json.loads(text[start : end + 1])


def init_db(path):
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS session_cards(
          session_id TEXT PRIMARY KEY, purpose TEXT, summary_md TEXT,
          card_json TEXT, n_messages INTEGER, truncated INTEGER,
          model TEXT, input_tokens INTEGER, output_tokens INTEGER, created_at TEXT,
          chunk_count INTEGER);
        CREATE TABLE IF NOT EXISTS chunk_summaries(
          run TEXT, session_id TEXT, chunk_index INTEGER, chunk_chars INTEGER,
          summary_json TEXT, PRIMARY KEY(run, session_id, chunk_index));
        CREATE TABLE IF NOT EXISTS ku_facts(
          fact_key TEXT PRIMARY KEY, session_id TEXT, fact TEXT,
          evidence_refs TEXT, confidence TEXT, valid_from TEXT,
          supersedes TEXT, status TEXT DEFAULT 'active', norm_prefix TEXT);
        CREATE INDEX IF NOT EXISTS idx_facts_fact ON ku_facts(fact);
        CREATE INDEX IF NOT EXISTS idx_facts_norm ON ku_facts(norm_prefix);
        """
    )
    return db


def norm_prefix(fact):
    """M1: single normalization shared by insert and lookup (40 chars of the
    lowercased, punctuation/space-stripped fact)."""
    return re.sub(r"\W+", "", fact.lower())[:40]


def normalize_refs(evidence_ids, valid_ids):
    """M2: keep only refs pointing at a message actually sent to the model.
    A bare hex id (model dropped the ``v2|cm|`` prefix) is repaired when the
    prefixed form is valid; anything else is dropped. Returns (refs, fixed, dropped)."""
    out, fixed, dropped = [], 0, 0
    for ref in evidence_ids or []:
        if not isinstance(ref, str):
            dropped += 1
            continue
        ref = ref.strip()
        if ref in valid_ids:
            out.append(ref)
        elif ref and (REF_PREFIX + ref) in valid_ids:
            out.append(REF_PREFIX + ref)
            fixed += 1
        else:
            dropped += 1
    return out, fixed, dropped


def consolidate(db, sid, facts, now):
    """ADD/UPDATE/DELETE/NOOP 对账：同义事实覆盖，矛盾的不自动删（标 review）。
    M1 fix: similarity matching compares against the stored norm_prefix column
    (same normalization both sides) instead of a divergent substr() on raw text."""
    added = updated = noop = 0
    for f in facts or []:
        fact = (f.get("fact") or "").strip()
        if not fact:
            continue
        key = "kc|" + re.sub(r"\W+", "", fact.lower())[:80]
        old = db.execute("select fact_key from ku_facts where fact=?", (fact,)).fetchone()
        if old:
            noop += 1
            continue
        prefix = norm_prefix(fact)
        rows = db.execute(
            "select fact_key, fact from ku_facts where norm_prefix=? and status='active'",
            (prefix,),
        ).fetchall()
        if rows and all(r[1] != fact for r in rows):
            for r in rows:
                db.execute(
                    "update ku_facts set status='superseded', supersedes=? where fact_key=?",
                    (key, r[0]))
            updated += 1
        else:
            added += 1
        db.execute(
            "insert or replace into ku_facts "
            "(fact_key, session_id, fact, evidence_refs, confidence, valid_from, "
            " supersedes, status, norm_prefix) values (?,?,?,?,?,?,?,'active',?)",
            (key, sid, fact, json.dumps(f.get("evidence_ids") or [], ensure_ascii=False),
             f.get("confidence") or "medium", now, None, prefix),
        )
    return added, updated, noop


def call_llm(client, prompt, max_tokens):
    """One completion; initial attempt + 2 retries with short backoff."""
    last = None
    for attempt in range(3):
        try:
            return client.chat.completions.create(
                model="ignored", messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens)
        except Exception as exc:
            last = exc
            time.sleep(2 * (attempt + 1))
    raise last


def _account(r, stats):
    stats["in"] += r.usage.prompt_tokens
    stats["out"] += r.usage.completion_tokens
    stats["calls"] += 1


def _tag(prompt, run_tag):
    """Append the run tag to the prompt. The kernel task ledger persists
    idempotency keys (var/db/pi_kernel_tasks.sqlite) but response caching is
    in-memory only, so a byte-identical re-run after a kernel restart fails
    with provider_response_unavailable. A per-run tag makes every run's keys
    fresh and keeps re-runs restart-safe."""
    return f"{prompt}\n\n管线运行: {run_tag}" if run_tag else prompt


def compress_session(sid, client, run_tag=""):
    """LLM-only part: build window/chunks, call the model, normalize fact refs.
    Opens its own read-only canonical connection (safe across worker threads);
    performs no MVP-DB writes, so the main thread stays the single writer."""
    con = sqlite3.connect(CANON, uri=True)
    try:
        f, fp = canonical_projection_predicate(con, "s.canonical_session_id")
        rows = load_rows(con, f, fp, sid)
        n_msgs = len(rows)
        lines, ids = build_lines(rows)
        if not lines:
            return {"status": "SKIP", "reason": "no content after strip"}
        valid_ids = set(ids)
        stats = {"status": "OK", "n_msgs": n_msgs, "in": 0, "out": 0, "calls": 0}
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        if n_msgs <= LARGE_MSGS:
            # single window, one call (reduce not needed)
            window, truncated = assemble_window(lines, WINDOW_CAP)
            r = call_llm(client, _tag(PROMPT_SMALL.format(sid=sid, window=window), run_tag), 1600)
            _account(r, stats)
            card = parse_json(r.choices[0].message.content)
            chunk_count, visible = 1, len(window)
            facts = card.get("facts")
            chunk_rows = []
        else:
            # map: one chunk-summary call per chunk
            chunks = make_chunks(lines)
            keep = sample_chunk_indices(len(chunks))
            sampled = len(chunks) > MAX_CHUNKS
            truncated = sampled
            kept_text, payloads, facts, chunk_rows = [], [], [], []
            for ci in keep:
                chunk_text = chunks[ci]
                r = call_llm(client, _tag(PROMPT_CHUNK.format(
                    n_chunks=len(chunks), i=ci + 1, sid=sid, chunk=chunk_text), run_tag), 800)
                _account(r, stats)
                cs = parse_json(r.choices[0].message.content)
                chunk_rows.append((ci, len(chunk_text), json.dumps(cs, ensure_ascii=False)))
                kept_text.append(len(chunk_text))
                payloads.append((ci, cs))
                facts.extend(cs.get("facts") or [])
                time.sleep(0.5)
            # reduce: merge all chunk summaries into the final card
            summaries_txt = "\n\n".join(
                f"[块{ci + 1}] {json.dumps(cs, ensure_ascii=False)}" for ci, cs in payloads)
            r = call_llm(client, _tag(PROMPT_MERGE.format(sid=sid, summaries=summaries_txt), run_tag), 1600)
            _account(r, stats)
            card = parse_json(r.choices[0].message.content)
            if sampled:
                card["truncated_sampling"] = True
                card["summary_md"] = ((card.get("summary_md") or "") +
                                      "（truncated：会话超长，仅均匀抽样部分块）")
            facts.extend(card.get("facts") or [])
            chunk_count, visible = len(keep), sum(kept_text)

        # M2: validate/normalize every fact's evidence refs against ids actually sent
        fixed = dropped = no_ev = 0
        clean_facts = []
        for fo in facts or []:
            if not isinstance(fo, dict):
                continue
            refs, fx, dp = normalize_refs(fo.get("evidence_ids"), valid_ids)
            fixed += fx
            dropped += dp
            if not refs:
                no_ev += 1
            clean_facts.append(dict(fo, evidence_ids=refs))
        stats.update(chunk_count=chunk_count, visible=visible, truncated=bool(truncated),
                     refs_fixed=fixed, refs_dropped=dropped, facts_no_evidence=no_ev,
                     purpose=str(card.get("purpose") or ""))
        return {"status": "OK", "card": card, "facts": clean_facts, "chunk_rows": chunk_rows,
                "stats": stats, "created_at": now}
    finally:
        con.close()


def persist_session(db, sid, res, run_id):
    """DB part: chunk summaries + session card + fact consolidation, committed."""
    card, stats = res["card"], res["stats"]
    now = res["created_at"]
    for ci, chars, summary_json in res["chunk_rows"]:
        db.execute("insert or replace into chunk_summaries values (?,?,?,?,?)",
                   (run_id, sid, ci, chars, summary_json))
    db.execute(
        "insert or replace into session_cards "
        "(session_id, purpose, summary_md, card_json, n_messages, truncated, "
        " model, input_tokens, output_tokens, created_at, chunk_count) "
        "values (?,?,?,?,?,?,?,?,?,?,?)",
        (sid, card.get("purpose"), card.get("summary_md"),
         json.dumps(card, ensure_ascii=False), stats["n_msgs"], int(stats["truncated"]),
         "hy3", stats["in"], stats["out"], now, stats["chunk_count"]),
    )
    a, u, n = consolidate(db, sid, res["facts"], now)
    db.commit()
    stats.update(facts_add=a, facts_upd=u, facts_noop=n)
    return stats


def run_pilot():
    sids = json.load(open("tmp/mvp_sessions.json", encoding="utf-8"))
    db = init_db(V3_DB)
    from personal_knowledge.core.llm import make_llm_client
    client = make_llm_client(purpose="conversation_summary")
    run_id = "v3-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    total_in = total_out = ok = fail = skip = 0
    t0 = time.time()
    for i, sid in enumerate(sids, 1):
        try:
            res = compress_session(sid, client, run_id)
            if res.get("status") == "SKIP":
                skip += 1
                print(f"[{i}/{len(sids)}] SKIP {sid[5:29]} ({res.get('reason')})", flush=True)
                continue
            st = persist_session(db, sid, res, run_id)
        except Exception as exc:
            db.rollback()  # L4: don't leak partial chunk_summaries into the next commit
            fail += 1
            print(f"[{i}/{len(sids)}] FAIL {sid[5:29]}: {type(exc).__name__}: {str(exc)[:140]}", flush=True)
            continue
        s = res["stats"]
        ok += 1
        total_in += s["in"]
        total_out += s["out"]
        print(f"[{i}/{len(sids)}] OK {sid[5:29]} msgs={s['n_msgs']} chunks={s['chunk_count']} "
              f"visible={s['visible']} in={s['in']} out={s['out']} calls={s['calls']} "
              f"refs fix{s['refs_fixed']}/drop{s['refs_dropped']} "
              f"facts +{st['facts_add']}/~{st['facts_upd']}/={st['facts_noop']} | {s['purpose'][:50]}", flush=True)
        time.sleep(1)
    print(f"\n=== v3 pilot done: run={run_id} ok={ok} fail={fail} skip={skip} "
          f"tokens in={total_in} out={total_out} elapsed={time.time() - t0:.0f}s", flush=True)


# ---------------------------------------------------------------- recall report

def token_set(text):
    toks = TOKEN_RE.findall(strip_injections(text or ""))
    return {t.lower() for t in toks if not t.isdigit() and t.lower() not in STOPWORDS}


def full_text(con, f, fp, sid):
    rows = load_rows(con, f, fp, sid)
    return "\n".join(strip_injections(r[3]) for r in rows)


def v3_visible_text(con, f, fp, sid):
    """Rebuild the text v3 actually sent (same deterministic rules as the pilot)."""
    rows = load_rows(con, f, fp, sid)
    lines, _ids = build_lines(rows)
    if not lines:
        return ""
    if len(rows) <= LARGE_MSGS:
        window, _ = assemble_window(lines, WINDOW_CAP)
        return window
    chunks = make_chunks(lines)
    keep = sample_chunk_indices(len(chunks))
    return "\n".join(chunks[ci] for ci in keep)


def card_text(db_path, sid):
    db = sqlite3.connect(db_path)
    try:
        parts = []
        row = db.execute("select card_json from session_cards where session_id=?", (sid,)).fetchone()
        if row and row[0]:
            parts.append(row[0])
        for (fact,) in db.execute("select fact from ku_facts where session_id=?", (sid,)):
            parts.append(fact)
        return "\n".join(parts)
    finally:
        db.close()


def db_tokens(db_path):
    db = sqlite3.connect(db_path)
    try:
        row = db.execute("select coalesce(sum(input_tokens),0), coalesce(sum(output_tokens),0) "
                         "from session_cards").fetchone()
        return {"input": row[0], "output": row[1]}
    finally:
        db.close()


def build_report():
    sids = json.load(open("tmp/mvp_sessions.json", encoding="utf-8"))
    con = sqlite3.connect(CANON, uri=True)
    f, fp = canonical_projection_predicate(con, "s.canonical_session_id")
    acc = {t: {"full_hit": 0, "full_den": 0, "win_hit": 0, "win_den": 0,
               "win_chars": 0, "full_chars": 0} for t in ("v1", "v3")}
    sessions = []
    for sid in sids:
        full = full_text(con, f, fp, sid)
        ftoks = token_set(full)
        rec = {"session_id": sid, "stripped_chars": len(full), "full_tokens": len(ftoks)}
        for tag in ("v1", "v3"):
            card = card_text(V1_DB if tag == "v1" else V3_DB, sid)
            ctoks = token_set(card)
            if tag == "v1":
                window, _trunc = v1_window(con, sid)
            else:
                window = v3_visible_text(con, f, fp, sid)
            wtoks = token_set(window)
            full_hit = len(ftoks & ctoks)
            win_hit = len(wtoks & ctoks)
            rec[tag] = {
                "window_chars": len(window), "window_tokens": len(wtoks),
                "card_tokens": len(ctoks),
                "visible_rate": round(len(window) / len(full), 4) if full else None,
                "full_recall": round(full_hit / len(ftoks), 4) if ftoks else None,
                "window_recall": round(win_hit / len(wtoks), 4) if wtoks else None,
            }
            a = acc[tag]
            a["full_hit"] += full_hit
            a["full_den"] += len(ftoks)
            a["win_hit"] += win_hit
            a["win_den"] += len(wtoks)
            a["win_chars"] += len(window)
            a["full_chars"] += len(full)
        sessions.append(rec)

    cost = {"input_cny_per_mtok": 1.0, "output_cny_per_mtok": 2.0}
    totals = {}
    for tag in ("v1", "v3"):
        a = acc[tag]
        toks = db_tokens(V1_DB if tag == "v1" else V3_DB)
        cost_cny = round(toks["input"] / 1e6 * cost["input_cny_per_mtok"]
                         + toks["output"] / 1e6 * cost["output_cny_per_mtok"], 4)
        totals[tag] = {
            "visible_rate": round(a["win_chars"] / a["full_chars"], 4) if a["full_chars"] else None,
            "full_recall": round(a["full_hit"] / a["full_den"], 4) if a["full_den"] else None,
            "window_recall": round(a["win_hit"] / a["win_den"], 4) if a["win_den"] else None,
            "window_chars": a["win_chars"], "stripped_chars": a["full_chars"],
            "tokens": toks, "cost_cny": cost_cny,
        }
    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "metric": {
            "unit": "unique identifier token types (set semantics)",
            "regex": TOKEN_RE.pattern,
            "lowercase": True,
            "stopwords": sorted(STOPWORDS),
            "full_text": "all message contents joined, system-reminder blocks stripped",
            "full_recall": "|full_tokens ∩ card_tokens| / |full_tokens|, card = card_json + ku_facts.fact",
            "window_recall": "|window_tokens ∩ card_tokens| / |window_tokens|",
            "v1_window": "v1 rules reproduced: first 60 content messages, 500 chars/msg, 22000 chars total, no strip",
            "v3_window": "v3 rules rebuilt: strip -> 800 chars/msg -> small(<=20 msgs): one 22000-char window; large: 12000-char chunks, max 24 sampled",
            "note": "window text is rebuilt deterministically from canonical rows with the same code paths as the runs",
        },
        "cost_cny_per_mtok": cost,
        "totals": totals,
        "sessions": sessions,
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)

    print(f"{'session':<26} {'ftok':>5} | {'v1 vis%':>7} {'v1 full%':>8} {'v1 win%':>7} "
          f"| {'v3 vis%':>7} {'v3 full%':>8} {'v3 win%':>7}")
    for rec in sessions:
        v1, v3 = rec["v1"], rec["v3"]
        def pct(x):
            return f"{100 * x:>6.1f}" if x is not None else "   n/a"
        print(f"{rec['session_id'][5:29]:<26} {rec['full_tokens']:>5} "
              f"| {pct(v1['visible_rate'])} {pct(v1['full_recall'])} "
              f"{pct(v1['window_recall'])} "
              f"| {pct(v3['visible_rate'])} {pct(v3['full_recall'])} "
              f"{pct(v3['window_recall'])}")
    for tag in ("v1", "v3"):
        t = totals[tag]
        print(f"{tag} totals: visible_rate={t['visible_rate']} full_recall={t['full_recall']} "
              f"window_recall={t['window_recall']} tokens in={t['tokens']['input']} "
              f"out={t['tokens']['output']} cost=¥{t['cost_cny']}")
    print(f"report written: {REPORT_PATH}")


def run_retry(sids):
    """Re-attempt specific failed sessions into the same v3 DB (idempotent)."""
    db = init_db(V3_DB)
    from personal_knowledge.core.llm import make_llm_client
    client = make_llm_client(purpose="conversation_summary")
    run_id = "v3-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    for sid in sids:
        try:
            res = compress_session(sid, client, run_id)
            if res.get("status") == "SKIP":
                print(f"RETRY SKIP {sid[5:29]} ({res.get('reason')})", flush=True)
                continue
            st = persist_session(db, sid, res, run_id)
            print(f"RETRY OK {sid[5:29]} facts +{st['facts_add']}/~{st['facts_upd']}/={st['facts_noop']}", flush=True)
        except Exception as exc:
            db.rollback()
            print(f"RETRY FAIL {sid[5:29]}: {type(exc).__name__}: {str(exc)[:140]}", flush=True)
        time.sleep(1)


def run_scale(limit=None, workers=3):
    """Next round: compress every visible session with enough content. Skips
    sessions already carded in v3, runs compress calls on a small thread pool
    (DB writes stay on the main thread), and stops at a hard cost cap."""
    import os
    from concurrent.futures import ThreadPoolExecutor, as_completed
    cap = float(os.environ.get("PK_MVP_COST_CAP", "8"))
    con = sqlite3.connect(CANON, uri=True)
    f, fp = canonical_projection_predicate(con, "s.canonical_session_id")
    all_sids = [r[0] for r in con.execute(
        f"select s.canonical_session_id from canonical_sessions s where {f} "
        "order by s.canonical_session_id", fp).fetchall()]
    carded_sids = set(all_sids)
    db = init_db(V3_DB)
    done = {r[0] for r in db.execute("select session_id from session_cards")}
    todo = []
    for sid in all_sids:
        if sid in done:
            continue
        rows = load_rows(con, f, fp, sid)
        text = "\n".join(strip_injections(r[3]) for r in rows if r[3])
        if len(text) >= MIN_SESSION_CHARS:
            todo.append(sid)
    con.close()
    if limit:
        todo = todo[:int(limit)]
    print(f"scale: visible={len(all_sids)} already_carded={len(carded_sids & done)} "
          f"todo={len(todo)} workers={workers} cost_cap=¥{cap}", flush=True)
    from personal_knowledge.core.llm import make_llm_client
    client = make_llm_client(purpose="conversation_summary")
    run_id = "v3-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    ok = fail = skip = 0
    total_in = total_out = 0
    price_in, price_out = 1.0, 2.0  # hy3 ¥/MTok from var/config/pi-provider.json
    t0 = time.time()
    cap_stopped = False

    def work(sid):
        return sid, compress_session(sid, client, run_id)

    ex = ThreadPoolExecutor(max_workers=workers)
    futures = {ex.submit(work, s): s for s in todo}
    try:
        for fut in as_completed(futures):
            sid = futures[fut]
            try:
                sid, res = fut.result()
                if res.get("status") == "SKIP":
                    skip += 1
                    print(f"SKIP {sid[5:29]} ({res.get('reason')})", flush=True)
                    continue
                st = persist_session(db, sid, res, run_id)
            except Exception as exc:
                db.rollback()
                fail += 1
                print(f"FAIL {sid[5:29]}: {type(exc).__name__}: {str(exc)[:140]}", flush=True)
                continue
            s = res["stats"]
            ok += 1
            total_in += s["in"]
            total_out += s["out"]
            cost = total_in / 1e6 * price_in + total_out / 1e6 * price_out
            if ok % 10 == 0 or ok + fail + skip == len(todo):
                proj = cost / max(ok, 1) * len(todo)
                print(f"... {ok + fail + skip}/{len(todo)} ok={ok} fail={fail} skip={skip} "
                      f"in={total_in} out={total_out} cost=¥{cost:.3f} proj=¥{proj:.2f} "
                      f"elapsed={time.time() - t0:.0f}s", flush=True)
            if cost >= cap:
                cap_stopped = True
                print(f"!! cost cap ¥{cap} reached (¥{cost:.3f}) — cancelling pending sessions", flush=True)
                break
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    cost = total_in / 1e6 * price_in + total_out / 1e6 * price_out
    print(f"\n=== v3 scale done: run={run_id} ok={ok} fail={fail} skip={skip} "
          f"tokens in={total_in} out={total_out} cost=¥{cost:.3f} "
          f"cap_stopped={cap_stopped} elapsed={time.time() - t0:.0f}s", flush=True)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "pilot"
    if mode == "pilot":
        run_pilot()
    elif mode == "retry":
        run_retry(sys.argv[2:])
    elif mode == "scale":
        run_scale(sys.argv[2] if len(sys.argv) > 2 else None)
    elif mode == "report":
        build_report()
    else:
        sys.exit(f"unknown mode: {mode}")


if __name__ == "__main__":
    main()
