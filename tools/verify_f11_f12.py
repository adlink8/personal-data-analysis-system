"""Post-F11/F12 verification — run against the newest shadow generation."""
import sqlite3, os, sys, json
base = r"D:\ADLINK\数据分析"
shadow = os.path.join(base, "data", "staging", "v2", "agent_conversations_v2.sqlite")
con = sqlite3.connect(shadow); con.row_factory = sqlite3.Row; cur = con.cursor()
g = cur.execute("SELECT generation_id FROM ce_event_generations ORDER BY created_at DESC LIMIT 1").fetchone()[0]
print("newest generation:", g)

# F12: epoch-millis raw timestamps must be GONE
cur.execute("""SELECT COUNT(*) c FROM ce_events WHERE generation_id=? AND occurred_at GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]'""", (g,))
epoch_events = cur.fetchone()["c"]
print("F12 epoch-millis events remaining:", epoch_events)

cur.execute("""SELECT s.family, COUNT(*) c FROM ce_events e JOIN ce_sessions s ON e.generation_id=s.generation_id AND e.session_id=s.session_id
WHERE e.generation_id=? AND e.occurred_at GLOB '[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]' GROUP BY s.family ORDER BY 2 DESC""", (g,))
print("F12 epoch by family:", [dict(r) for r in cur.fetchall()])

# F11: codex/claude reasoning content coverage
cur.execute("""SELECT s.family, e.kind, COUNT(*) total, SUM(CASE WHEN e.content IS NULL THEN 1 ELSE 0 END) null_content,
SUM(CASE WHEN e.fidelity_json LIKE '%UNAVAILABLE%' THEN 1 ELSE 0 END) unavailable_declared
FROM ce_events e JOIN ce_sessions s ON e.generation_id=s.generation_id AND e.session_id=s.session_id
WHERE e.generation_id=? AND e.kind IN ('reasoning','tool_call','tool_result') GROUP BY s.family, e.kind ORDER BY 1,2""", (g,))
for r in cur.fetchall(): print("F11:", dict(r))

# sanity: no content NULL + COMPLETE contradiction for reasoning
cur.execute("""SELECT COUNT(*) c FROM ce_events e JOIN ce_sessions s ON e.generation_id=s.generation_id AND e.session_id=s.session_id
WHERE e.generation_id=? AND e.kind='reasoning' AND e.content IS NULL AND e.fidelity_json LIKE '%content_availability\\": \\"complete%'""", (g,))
print("F11 lying reasoning events:", cur.fetchone()["c"])
con.close()