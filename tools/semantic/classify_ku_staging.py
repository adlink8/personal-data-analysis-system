"""Classify KU staging rows into the formal nine-type enum via the pi kernel
LLM channel (hy3). Idempotent: only rows still marked 'unclassified' are sent.

Run from repo root (kernel must be up):
  PI_KERNEL_INTERNAL_CAPABILITY=<cap> python tools/semantic/classify_ku_staging.py [--batch 40]
"""
import json, re, sqlite3, sys, time

STAGING = "var/db/semantic_ku_staging.sqlite"
BATCH = 40
ENUM = ("preference", "habit", "personal_fact", "project_decision",
        "capability", "tool_usage", "solution", "decision_rationale",
        "technical_conclusion")

PROMPT = """你是个人知识库的知识单元分类器。把每条知识事实分入唯一类别，类别定义：
- preference: 用户偏好/设定（工具配置偏好、沟通风格、工作方式要求）
- habit: 重复出现的工作习惯
- personal_fact: 关于用户个人或其环境的客观事实（机器配置、目录位置、仓库账号）
- project_decision: 项目层面的决策（架构选择、方案取舍、范围裁定）
- capability: 系统/工具具备什么能力的描述
- tool_usage: 工具的具体用法/配置方法/命令
- solution: 对某个具体问题的解决办法
- decision_rationale: 决策背后的理由或权衡
- technical_conclusion: 技术结论、踩坑结论、行为机制说明
输出严格的 JSON 对象，不要 markdown、不要解释：{{"results":[{{"id":"1","type":"technical_conclusion"}},...]}}，id 用下面每条前面的编号。

事实列表：
{items}"""


def parse_json(text):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.S)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object found")
    return json.loads(text[start:end + 1])


def main():
    batch = BATCH
    if "--batch" in sys.argv:
        batch = int(sys.argv[sys.argv.index("--batch") + 1])
    db = sqlite3.connect(STAGING)
    rows = db.execute(
        "select rowid, answer from knowledge_units_staging where unit_type='unclassified' order by rowid").fetchall()
    print(f"to classify: {len(rows)} (batch={batch})")
    if not rows:
        return
    from personal_knowledge.core.llm import make_llm_client
    client = make_llm_client(purpose="conversation_summary")
    stats = {}
    bad = 0
    for i in range(0, len(rows), batch):
        chunk = rows[i:i + batch]
        items = "\n".join(f"{j + 1}. {a[:150]}" for j, (rid, a) in enumerate(chunk))
        r = client.chat.completions.create(
            model="ignored", messages=[{"role": "user", "content": PROMPT.format(items=items)}],
            max_tokens=1600)
        data = parse_json(r.choices[0].message.content)
        got = {str(x.get("id")): str(x.get("type", "")).strip() for x in data.get("results", [])}
        for j, (rid, _a) in enumerate(chunk):
            t = got.get(str(j + 1), "")
            if t in ENUM:
                db.execute("update knowledge_units_staging set unit_type=? where rowid=?", (t, rid))
                stats[t] = stats.get(t, 0) + 1
            else:
                bad += 1
        db.commit()
        print(f"[{min(i + batch, len(rows))}/{len(rows)}] ok batch {i // batch + 1}", flush=True)
    print("distribution:", json.dumps(stats, ensure_ascii=False))
    left = db.execute("select count(*) from knowledge_units_staging where unit_type='unclassified'").fetchone()[0]
    print(f"still unclassified: {left} (invalid/failed: {bad})")


if __name__ == "__main__":
    main()
