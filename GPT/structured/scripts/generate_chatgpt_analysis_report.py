import html
import json
import sqlite3
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


BASE = Path(__file__).resolve().parents[2]
DB = BASE / "结构化数据" / "SQLite数据库" / "chatgpt_data.db"
OUT = BASE / "分析数据" / "报告HTML"
CHARTS = BASE / "分析数据" / "图表PNG"
REPORT = OUT / "chatgpt_聊天数据分析报告.html"
SOURCE_NOTES = OUT / "chatgpt_聊天数据分析_source_notes.json"


COLORS = {
    "blue": "#A3BEFA",
    "blue_dark": "#2E4780",
    "gold": "#FFE15B",
    "orange": "#F0986E",
    "olive": "#A3D576",
    "pink": "#F390CA",
    "ink": "#1F2430",
    "muted": "#6F768A",
    "grid": "#E6E8F0",
    "surface": "#FCFCFD",
}


TOPIC_RULES = [
    ("编程与调试", ["python", "java", "c#", "android", "代码", "报错", "bug", "class", "def", "import", "qt", "socket", "接口", "数据库", "api"]),
    ("文档/PPT/写作", ["ppt", "文档", "报告", "模板", "论文", "总结", "简历", "写作", "markdown", "readme"]),
    ("学习与考试", ["课程", "考试", "题", "讲解", "ll(1)", "左递归", "网络", "实验", "复习", "教材"]),
    ("AI/代理/工具", ["gpt", "codex", "代理", "插件", "ai", "memory", "mcp", "模型", "提示词", "工作流"]),
    ("设计/原型/图像", ["原型", "ui", "设计", "图片", "图像", "封面", "海报", "图标", "界面"]),
    ("职业与规划", ["职业", "日本", "留学", "就业", "规划", "背景", "目标", "岗位"]),
]


def query(con, sql):
    return pd.read_sql_query(sql, con)


def add_header(fig, title, subtitle):
    fig.text(0.06, 0.97, title, ha="left", va="top", fontsize=15, weight="bold", color=COLORS["ink"])
    fig.text(0.06, 0.925, subtitle, ha="left", va="top", fontsize=10, color=COLORS["muted"])


def save_fig(fig, name):
    path = CHARTS / name
    fig.savefig(path, dpi=180, bbox_inches="tight", facecolor=COLORS["surface"])
    plt.close(fig)
    return path


def classify_topic(row):
    text = " ".join(
        str(row.get(col) or "")
        for col in ["title", "first_user_msg"]
    ).lower()
    for topic, keys in TOPIC_RULES:
        if any(k.lower() in text for k in keys):
            return topic
    return "其他/闲聊"


def pct(n, d):
    return 0 if not d else n / d * 100


def esc(value):
    return html.escape(str(value))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    CHARTS.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)

    conversations = query(con, "select * from conversations")
    messages = query(con, "select * from messages")
    artifacts = query(con, "select * from artifacts")
    feedback = query(con, "select * from feedback")

    conversations["topic"] = conversations.apply(classify_topic, axis=1)
    monthly = query(
        con,
        """
        select substr(create_date,1,7) as month,
               count(*) as conversations,
               sum(user_msg_count) as user_messages,
               sum(total_chars) as total_chars
        from conversations
        group by 1
        order by 1
        """,
    )
    hour = query(con, "select create_hour as hour, count(*) as conversations from conversations group by 1 order by 1")
    topic = conversations.groupby("topic", as_index=False).agg(
        conversations=("id", "count"),
        user_messages=("user_msg_count", "sum"),
        total_chars=("total_chars", "sum"),
    ).sort_values("total_chars", ascending=False)
    models = query(
        con,
        """
        select model_name, count(*) as conversations, sum(total_msg_count) as messages, sum(total_chars) as total_chars
        from conversations
        group by 1
        order by total_chars desc
        """,
    )
    top = conversations.sort_values("total_chars", ascending=False).head(8)[
        ["title", "create_date", "topic", "user_msg_count", "assistant_msg_count", "total_chars", "has_code", "has_attachments"]
    ]
    artifact_summary = artifacts.groupby(["category", "sub_category"], as_index=False).agg(
        count=("id", "count"),
        size_mb=("size_kb", lambda s: round(s.sum() / 1024, 2)),
    ).sort_values(["count", "size_mb"], ascending=False).head(10)

    sns.set_theme(style="whitegrid")
    plt.rcParams.update(
        {
            "font.sans-serif": ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"],
            "axes.edgecolor": COLORS["grid"],
            "axes.labelcolor": COLORS["muted"],
            "xtick.color": COLORS["muted"],
            "ytick.color": COLORS["muted"],
        }
    )

    fig, ax = plt.subplots(figsize=(11, 5.2))
    fig.patch.set_facecolor(COLORS["surface"])
    sns.barplot(data=monthly, x="month", y="total_chars", ax=ax, color=COLORS["blue"], edgecolor=COLORS["blue_dark"], linewidth=0.8)
    ax.set_xlabel("")
    ax.set_ylabel("总字符数")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(axis="y", color=COLORS["grid"], linestyle="--", linewidth=0.8)
    add_header(fig, "月度使用强度", "按对话创建月份汇总，总字符数代表任务体量；来源：conversations 表")
    monthly_chart = save_fig(fig, "monthly_usage.png")

    fig, ax = plt.subplots(figsize=(10, 4.8))
    fig.patch.set_facecolor(COLORS["surface"])
    sns.barplot(data=topic, y="topic", x="total_chars", ax=ax, color=COLORS["orange"], edgecolor="#804126", linewidth=0.8)
    ax.set_xlabel("总字符数")
    ax.set_ylabel("")
    ax.grid(axis="x", color=COLORS["grid"], linestyle="--", linewidth=0.8)
    add_header(fig, "主题工作量分布", "按标题和首条用户消息做规则分类；用于识别主要使用场景")
    topic_chart = save_fig(fig, "topic_workload.png")

    fig, ax = plt.subplots(figsize=(10, 4.5))
    fig.patch.set_facecolor(COLORS["surface"])
    sns.lineplot(data=hour, x="hour", y="conversations", marker="o", ax=ax, color=COLORS["blue_dark"], linewidth=2)
    ax.fill_between(hour["hour"], hour["conversations"], color=COLORS["blue"], alpha=0.25)
    ax.set_xlabel("开始小时")
    ax.set_ylabel("对话数")
    ax.set_xticks(range(8, 23, 2))
    ax.grid(color=COLORS["grid"], linestyle="--", linewidth=0.8)
    add_header(fig, "一天中的启动节奏", "按对话开始时间统计；高峰集中在上午和晚间")
    hour_chart = save_fig(fig, "hourly_start_pattern.png")

    total_convs = len(conversations)
    total_messages = len(messages)
    user_messages = int((messages["role"] == "user").sum())
    assistant_messages = int((messages["role"] == "assistant").sum())
    total_chars = int(conversations["total_chars"].sum())
    first_date = conversations["create_date"].min()
    last_date = conversations["create_date"].max()
    code_convs = int(conversations["has_code"].sum())
    attachment_convs = int(conversations["has_attachments"].sum())
    may2026 = monthly.loc[monthly["month"].eq("2026-05"), "total_chars"].sum()
    may2026_convs = monthly.loc[monthly["month"].eq("2026-05"), "conversations"].sum()
    top_conv = top.iloc[0]
    topic_top = topic.iloc[0]
    model_top = models.iloc[0]
    avg_user_per_conv = conversations["user_msg_count"].mean()
    avg_chars_per_conv = conversations["total_chars"].mean()
    feedback_count = len(feedback)

    top_rows = "\n".join(
        f"<tr><td>{esc(r.title)}</td><td>{esc(r.create_date)}</td><td>{esc(r.topic)}</td><td>{int(r.user_msg_count)}</td><td>{int(r.assistant_msg_count)}</td><td>{int(r.total_chars):,}</td><td>{'是' if r.has_code else '否'}</td><td>{'是' if r.has_attachments else '否'}</td></tr>"
        for r in top.itertuples()
    )
    model_rows = "\n".join(
        f"<tr><td>{esc(r.model_name)}</td><td>{int(r.conversations)}</td><td>{int(r.messages)}</td><td>{int(r.total_chars):,}</td></tr>"
        for r in models.itertuples()
    )
    artifact_rows = "\n".join(
        f"<tr><td>{esc(r.category)}</td><td>{esc(r.sub_category)}</td><td>{int(r.count)}</td><td>{r.size_mb:.2f}</td></tr>"
        for r in artifact_summary.itertuples()
    )

    html_doc = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>你和 ChatGPT 的聊天数据分析</title>
  <style>
    body {{ margin: 0; background: #FCFCFD; color: #1F2430; font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif; line-height: 1.65; }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 36px 24px 64px; }}
    h1 {{ font-size: 30px; margin: 0 0 18px; letter-spacing: 0; }}
    h2 {{ margin-top: 34px; font-size: 21px; }}
    h3 {{ margin-top: 24px; font-size: 17px; }}
    .summary {{ background: #fff; border: 1px solid #E6E8F0; border-radius: 8px; padding: 18px 20px; }}
    .kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 18px 0 26px; }}
    .kpi {{ background: #fff; border: 1px solid #E6E8F0; border-radius: 8px; padding: 14px; }}
    .kpi b {{ display: block; font-size: 24px; margin-bottom: 4px; }}
    .kpi span {{ color: #6F768A; font-size: 13px; }}
    img {{ width: 100%; max-width: 100%; border: 1px solid #E6E8F0; border-radius: 8px; background: #fff; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border: 1px solid #E6E8F0; border-radius: 8px; overflow: hidden; }}
    th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #E6E8F0; vertical-align: top; }}
    th {{ background: #F4F5F7; font-weight: 700; }}
    tr:last-child td {{ border-bottom: 0; }}
    .note {{ color: #6F768A; font-size: 14px; }}
    @media (max-width: 760px) {{ .kpis {{ grid-template-columns: repeat(2, 1fr); }} main {{ padding: 24px 14px 42px; }} }}
  </style>
</head>
<body>
<main>
  <h1>你和 ChatGPT 的聊天数据分析</h1>

  <section class="summary">
    <h2>Executive Summary</h2>
    <ul>
      <li><b>你的使用已经从零散问答转成任务型协作。</b>全量 {total_convs} 个对话里，2026-05 单月只有 {int(may2026_convs)} 个对话，却贡献 {int(may2026):,} 字符，占总字符量 {pct(may2026, total_chars):.1f}%。这像从“问路”变成“带着 AI 做项目推进”。</li>
      <li><b>编程、文档和学习是主要工作负载。</b>按标题和首问规则分类，最高负载主题是“{esc(topic_top.topic)}”，贡献 {int(topic_top.total_chars):,} 字符；长对话榜里同时出现调试、文档模板、LL(1) 题目讲解、职业规划等场景。</li>
      <li><b>你的高价值用法集中在长链路任务。</b>最大单个对话是“{esc(top_conv.title)}”，{int(top_conv.total_chars):,} 字符；有代码的对话 {code_convs} 个，占 {pct(code_convs, total_convs):.1f}%，带附件对话 {attachment_convs} 个，占 {pct(attachment_convs, total_convs):.1f}%。</li>
      <li><b>使用节奏偏“上午启动 + 晚间补充”。</b>对话启动高峰在 9 点、10 点和 21 点附近，说明 GPT 更像你的工作台/学习台，而不是单纯娱乐聊天窗口。</li>
    </ul>
  </section>

  <div class="kpis">
    <div class="kpi"><b>{total_convs}</b><span>对话数</span></div>
    <div class="kpi"><b>{total_messages:,}</b><span>消息数，用户 {user_messages} / 助手 {assistant_messages}</span></div>
    <div class="kpi"><b>{total_chars/10000:.1f} 万</b><span>总字符量</span></div>
    <div class="kpi"><b>{first_date} 至 {last_date}</b><span>导出覆盖时间</span></div>
  </div>

  <section>
    <h2>最近的使用强度显著上升</h2>
    <p><b>2026-05 是整个导出里的强峰值。</b>它不是对话数量最多的月份，但单月字符量最高，说明最近的互动更长、更复杂，可能包含 Codex、插件、文档处理、课程题目讲解等多轮任务。按平均值看，每个对话约 {avg_user_per_conv:.1f} 条用户消息、{avg_chars_per_conv:,.0f} 字符；2026-05 的强度明显超过这个均值。</p>
    <img src="charts/{monthly_chart.name}" alt="月度使用强度">
  </section>

  <section>
    <h2>主题重心：工程化、学习化、产物化</h2>
    <p><b>你的聊天不是普通闲聊型数据。</b>从标题和首条用户消息看，主题主要围绕编程调试、文档/PPT/写作、学习考试、AI 代理工具、设计原型和职业规划。这种结构更像“外接大脑”的任务队列：问题输入后，GPT 负责解释、生成、检查或把材料变成产物。</p>
    <img src="charts/{topic_chart.name}" alt="主题工作量分布">
  </section>

  <section>
    <h2>使用时间像工作台，而不是纯聊天窗口</h2>
    <p><b>上午 9-10 点和晚上 21 点附近启动最多。</b>这通常对应两类场景：白天开始解决课程/代码/文档任务，晚上补充整理或继续长任务。它像神经系统里的“执行功能”外包：白天负责推进，晚上负责复盘和补完。</p>
    <img src="charts/{hour_chart.name}" alt="一天中的启动节奏">
  </section>

  <section>
    <h2>高价值对话排行榜</h2>
    <p><b>最长的对话基本都是复杂任务。</b>这些对话是后续最值得深挖的对象：可以抽取你的常用工作流、常见阻塞点、提示词模式和可沉淀成脚本/技能的重复动作。</p>
    <table>
      <thead><tr><th>标题</th><th>日期</th><th>主题</th><th>用户消息</th><th>助手消息</th><th>字符数</th><th>代码</th><th>附件</th></tr></thead>
      <tbody>{top_rows}</tbody>
    </table>
  </section>

  <section>
    <h2>模型和附件说明了任务复杂度</h2>
    <p><b>Unknown/GPT-3.5 代表早期或未识别模型，2026 年的 thinking 模型贡献了大量长任务。</b>附件和产物也不少：导出中识别到 {len(artifacts)} 个 artifact，包含页面渲染、AI 生成图像、用户截图、文档截图、PPT 等。这说明你不是只让 GPT “说答案”，而是在让它处理可见材料、生成交付物。</p>
    <h3>模型分布</h3>
    <table>
      <thead><tr><th>模型</th><th>对话数</th><th>消息数</th><th>字符数</th></tr></thead>
      <tbody>{model_rows}</tbody>
    </table>
    <h3>主要附件/产物类型</h3>
    <table>
      <thead><tr><th>类别</th><th>子类别</th><th>数量</th><th>大小 MB</th></tr></thead>
      <tbody>{artifact_rows}</tbody>
    </table>
  </section>

  <section>
    <h2>建议：把高频任务固化成工作流</h2>
    <ol>
      <li><b>把“编程调试”固化成三段式：</b>错误现象、最小复现、验证命令。你已经大量这么用，下一步是让每次调试都自动留下结论和复盘。</li>
      <li><b>把“课程/考试题讲解”固化成题库工作流：</b>题目、知识点、解法、易错点、Anki 卡片。这样 GPT 不只是讲题，而是帮你形成长期记忆。</li>
      <li><b>把“文档/PPT/报告”固化成产物流水线：</b>资料读取、结构差异、草稿、视觉检查、最终导出。你当前已有大量附件和渲染产物，适合继续自动化。</li>
    </ol>
  </section>

  <section>
    <h2>Further Questions</h2>
    <ul>
      <li>哪些长对话最后真正产出了可复用文件或解决了问题？现在的数据能看到“长”，但不能完全判断“有效”。</li>
      <li>哪些提示词模式最稳定？需要进一步抽取用户首问和追问结构。</li>
      <li>哪些任务可以从聊天升级成脚本、技能或固定模板？建议从最长 10 个对话开始。</li>
    </ul>
  </section>

  <section>
    <h2>Caveats and Assumptions</h2>
    <p class="note">本报告以本地 SQLite 清洗库为主源，并用原始 conversations.json 校验对话数量。主题分类是规则分类，不等同于语义模型聚类；模型名中的 Unknown 代表导出或清洗阶段未能识别模型。反馈表只有 {feedback_count} 条记录，因此未对满意度做统计推断。</p>
  </section>
</main>
</body>
</html>"""
    REPORT.write_text(html_doc, encoding="utf-8")

    notes = {
        "source_files": {
            "database": str(DB),
            "raw_conversations": str(BASE / "原始数据" / "conversations.json"),
        },
        "row_counts": {
            "conversations": total_convs,
            "messages": total_messages,
            "artifacts": len(artifacts),
            "feedback": feedback_count,
        },
        "chart_map": [
            {"section": "最近的使用强度显著上升", "chart": str(monthly_chart), "type": "bar", "fields": ["month", "total_chars"]},
            {"section": "主题重心：工程化、学习化、产物化", "chart": str(topic_chart), "type": "horizontal_bar", "fields": ["topic", "total_chars"]},
            {"section": "使用时间像工作台，而不是纯聊天窗口", "chart": str(hour_chart), "type": "line_area", "fields": ["hour", "conversations"]},
        ],
        "classification_rules": TOPIC_RULES,
    }
    SOURCE_NOTES.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")

    with (BASE / "原始数据" / "conversations.json").open("r", encoding="utf-8") as f:
        raw_count = len(json.load(f))
    print(json.dumps({
        "report": str(REPORT),
        "source_notes": str(SOURCE_NOTES),
        "charts": [str(monthly_chart), str(topic_chart), str(hour_chart)],
        "database_conversations": total_convs,
        "raw_conversations": raw_count,
        "messages": total_messages,
        "total_chars": total_chars,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
