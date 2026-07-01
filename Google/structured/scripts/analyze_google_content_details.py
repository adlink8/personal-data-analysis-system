from __future__ import annotations

import csv
import html
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import matplotlib.pyplot as plt
from bs4 import BeautifulSoup
from matplotlib import font_manager
import seaborn as sns


GOOGLE_DIR = Path(r"C:\Users\li\Desktop\数据分析\Google")
TAKEOUT = GOOGLE_DIR / "takeout-20260608T162603Z-17-001" / "Takeout"
OUT = GOOGLE_DIR / "google_content_analysis"
ASSETS = OUT / "assets"

TOKENS = {
    "surface": "#FCFCFD",
    "panel": "#FFFFFF",
    "ink": "#1F2430",
    "muted": "#6F768A",
    "grid": "#E6E8F0",
    "axis": "#D7DBE7",
    "blue": "#A3BEFA",
    "blue_dark": "#2E4780",
    "orange": "#F0986E",
    "orange_dark": "#804126",
    "olive": "#A3D576",
    "olive_dark": "#386411",
    "pink": "#F390CA",
    "pink_dark": "#8A3A6F",
}

CATEGORIES = {
    "AI / 编程 / 工具": [
        "gemini", "ai", "claude", "chatgpt", "openai", "antigravity", "mcp",
        "docker", "linux", "devops", "python", "github", "编程", "代码", "模型", "智能体", "额度",
    ],
    "课程 / 学习 / 资料": [
        "课程", "实验", "计算机组成", "教师用书", "roadmap", "学习", "study", "学生", "考试",
    ],
    "账号 / 安全 / 浏览器": [
        "谷歌账户", "账号", "账户", "指纹浏览器", "错误", "报错", "安全", "登录", "quota", "terminated",
    ],
    "支付 / 金融 / 卡": [
        "卡", "信用卡", "虚拟卡", "wells fargo", "one key", "bpay", "pay", "钱包", "finance",
    ],
    "政治 / 时政 / 社会": [
        "习近平", "中共", "中国", "北京", "朝鲜", "政治", "时政", "两会", "护照", "国安", "信访",
    ],
    "娱乐 / 体育 / 生活内容": [
        "攀岩", "春晚", "机器人", "防身", "足球", "娱乐", "体育", "电影", "youtube",
    ],
    "地图 / 地点 / 本地生活": [
        "maps", "地图", "地点", "local", "place", "restaurant", "餐", "商店", "realty",
    ],
}


def read_text(path: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return path.read_text(encoding=enc, errors="replace")
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def parse_time(raw: str) -> str:
    raw = html.unescape(raw).strip()
    raw = re.sub(r"\s+", " ", raw).replace(" CST", "").replace(" UTC", "").replace(" GMT", "")
    for fmt in ("%Y年%m月%d日 %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).isoformat(timespec="seconds")
        except ValueError:
            pass
    return ""


def clean(value: str, limit: int = 500) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def normalize_url(url: str) -> tuple[str, str]:
    if not url:
        return "", ""
    url = html.unescape(url)
    parsed = urlparse(url)
    if parsed.netloc == "www.google.com" and parsed.path == "/url":
        target = parse_qs(parsed.query).get("q", [""])[0]
        if target:
            url = unquote(target)
            parsed = urlparse(url)
    return parsed.netloc.lower().replace("www.", ""), url


def classify(text: str) -> str:
    lower = text.lower()
    hits = []
    for category, keywords in CATEGORIES.items():
        score = sum(1 for kw in keywords if kw.lower() in lower)
        if score:
            hits.append((score, category))
    return sorted(hits, reverse=True)[0][1] if hits else "其他 / 未分类"


def activity_cards(path: Path, service: str) -> list[dict]:
    if not path.exists():
        return []
    soup = BeautifulSoup(read_text(path), "html.parser")
    cards = soup.select("div.outer-cell")
    rows = []
    for card in cards:
        body = card.select_one("div.content-cell.mdl-cell--6-col")
        if not body:
            continue
        text = clean(body.get_text(" ", strip=True), 2000)
        time_match = re.search(r"(\d{4}年\d{1,2}月\d{1,2}日\s+\d{1,2}:\d{2}:\d{2}(?:\s+(?:CST|UTC|GMT))?)", text)
        dt = parse_time(time_match.group(1)) if time_match else ""
        links = body.find_all("a")
        first_link = links[0] if links else None
        title = clean(first_link.get_text(" ", strip=True), 500) if first_link else ""
        href = first_link.get("href", "") if first_link else ""
        domain, url = normalize_url(href)
        action = "other"
        for prefix, label in [
            ("Searched for", "search"),
            ("Visited", "visit"),
            ("Watched", "watch"),
            ("Viewed", "view"),
            ("Prompted", "prompt"),
            ("Attached", "attachment"),
        ]:
            if text.startswith(prefix):
                action = label
                break
        if service == "Gemini Apps":
            m = re.match(r"Prompted\s+(.+?)(?:\s+Attached|\s+\d{4}年|$)", text)
            if m:
                title = clean(m.group(1), 500)
                action = "prompt"
        elif service == "Search" and action == "search":
            title = clean(title or re.sub(r"^Searched for\s+", "", text).split(" 20")[0], 500)
        elif service == "YouTube" and len(links) >= 2:
            channel = clean(links[1].get_text(" ", strip=True), 200)
        else:
            channel = ""
        channel = locals().get("channel", "")
        content = " ".join([service, action, title, channel, domain, text[:500]])
        rows.append(
            {
                "service": service,
                "datetime": dt,
                "month": dt[:7] if dt else "",
                "action": action,
                "title_or_query": title,
                "channel_or_source": channel,
                "domain": domain,
                "url": url,
                "category": classify(content),
                "raw_excerpt": text[:1000],
            }
        )
        if "channel" in locals():
            del channel
    return rows


def gemini_attachments() -> list[dict]:
    root = TAKEOUT / "我的活动" / "Gemini Apps"
    rows = []
    if not root.exists():
        return rows
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.name == "我的活动记录.html":
            continue
        name = path.name
        rows.append(
            {
                "file_name": name,
                "extension": path.suffix.lower() or "(none)",
                "size_kb": round(path.stat().st_size / 1024, 1),
                "category": classify(name),
            }
        )
    return rows


def maps_details() -> list[dict]:
    rows = []
    root = TAKEOUT / "Google 地图"
    if not root.exists():
        return rows
    for path in sorted(root.rglob("*.json")):
        try:
            data = json.loads(read_text(path))
        except Exception:
            rows.append({"source_file": str(path.relative_to(root)), "record_type": "unreadable", "name_or_value": "", "category": "地图 / 地点 / 本地生活"})
            continue
        stack = [data]
        extracted = []
        while stack and len(extracted) < 200:
            item = stack.pop()
            if isinstance(item, dict):
                for key in ("name", "title", "placeName", "address", "query", "displayName"):
                    if key in item and isinstance(item[key], str) and item[key].strip():
                        extracted.append((key, clean(item[key], 300)))
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)
        if not extracted:
            rows.append({"source_file": str(path.relative_to(root)), "record_type": "structure_only", "name_or_value": "", "category": "地图 / 地点 / 本地生活"})
        for key, value in extracted:
            rows.append({"source_file": str(path.relative_to(root)), "record_type": key, "name_or_value": value, "category": classify(value + " 地图")})
    return rows


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def setup_chart_theme() -> None:
    font_path = Path(r"C:\Windows\Fonts\simhei.ttf")
    font_name = "SimHei"
    if font_path.exists():
        font_manager.fontManager.addfont(str(font_path))
        font_name = font_manager.FontProperties(fname=str(font_path)).get_name()
    sns.set_theme(
        style="whitegrid",
        rc={
            "figure.facecolor": TOKENS["surface"],
            "axes.facecolor": TOKENS["panel"],
            "axes.edgecolor": TOKENS["axis"],
            "grid.color": TOKENS["grid"],
            "font.family": "sans-serif",
            "font.sans-serif": [font_name, "Microsoft YaHei", "Segoe UI", "Arial"],
            "axes.unicode_minus": False,
        },
    )


def add_header(fig, ax, title: str, subtitle: str) -> None:
    ax.set_title("")
    fig.subplots_adjust(top=0.78, left=0.28)
    left = ax.get_position().x0
    fig.text(left, 0.97, title, ha="left", va="top", fontsize=13, fontweight="semibold", color=TOKENS["ink"])
    fig.text(left, 0.91, subtitle, ha="left", va="top", fontsize=9, color=TOKENS["muted"])
    sns.despine(ax=ax)


def plot_counter(counter: Counter, filename: str, title: str, subtitle: str, color: str, edge: str) -> None:
    data = counter.most_common(12)
    labels = [k for k, _ in reversed(data)]
    values = [v for _, v in reversed(data)]
    fig, ax = plt.subplots(figsize=(9, 5.4), dpi=160)
    ax.barh(labels, values, color=color, edgecolor=edge)
    ax.set_xlabel("条数")
    add_header(fig, ax, title, subtitle)
    fig.savefig(ASSETS / filename, bbox_inches="tight")
    plt.close(fig)


def html_table(rows: list[dict], fields: list[str], limit: int = 20) -> str:
    out = []
    for row in rows[:limit]:
        out.append("<tr>" + "".join(f"<td>{html.escape(str(row.get(field, '')))}</td>" for field in fields) + "</tr>")
    return "\n".join(out)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    OUT.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    setup_chart_theme()

    rows = []
    for service in ("Gemini Apps", "AI Mode", "Search", "YouTube", "Maps"):
        rows.extend(activity_cards(TAKEOUT / "我的活动" / service / "我的活动记录.html", service))

    attachments = gemini_attachments()
    map_rows = maps_details()

    category_counter = Counter(row["category"] for row in rows)
    service_counter = Counter(row["service"] for row in rows)
    search_queries = [r for r in rows if r["service"] == "Search" and r["action"] == "search"]
    youtube_rows = [r for r in rows if r["service"] == "YouTube"]
    gemini_rows = [r for r in rows if r["service"] == "Gemini Apps"]
    domains = Counter(row["domain"] for row in rows if row["domain"])
    channels = Counter(row["channel_or_source"] for row in youtube_rows if row["channel_or_source"])
    attachment_categories = Counter(row["category"] for row in attachments)

    plot_counter(category_counter, "content_categories.png", "具体内容主题分布", "按标题、查询、频道、文件名和域名做关键词归类", TOKENS["blue"], TOKENS["blue_dark"])
    plot_counter(channels, "youtube_channels.png", "YouTube 高频频道", "按观看/查看记录中的频道名统计", TOKENS["orange"], TOKENS["orange_dark"])
    plot_counter(attachment_categories, "gemini_attachment_categories.png", "Gemini 附件主题", "按附件文件名做关键词归类，不读取附件正文", TOKENS["olive"], TOKENS["olive_dark"])
    plot_counter(domains, "visited_domains.png", "访问内容的主要域名", "Search 访问记录、YouTube 链接和地图链接中的域名", TOKENS["pink"], TOKENS["pink_dark"])

    full_fields = ["service", "datetime", "month", "action", "category", "title_or_query", "channel_or_source", "domain", "url", "raw_excerpt"]
    write_csv(OUT / "full_activity_details.csv", rows, full_fields)
    write_csv(OUT / "search_queries.csv", search_queries, full_fields)
    write_csv(OUT / "youtube_items.csv", youtube_rows, full_fields)
    write_csv(OUT / "gemini_prompts.csv", gemini_rows, full_fields)
    write_csv(OUT / "gemini_attachments.csv", attachments, ["file_name", "extension", "size_kb", "category"])
    write_csv(OUT / "maps_extracted_details.csv", map_rows, ["source_file", "record_type", "name_or_value", "category"])

    category_rows = [{"category": k, "count": v} for k, v in category_counter.most_common()]
    service_rows = [{"service": k, "count": v} for k, v in service_counter.most_common()]
    domain_rows = [{"domain": k, "count": v} for k, v in domains.most_common(20)]
    channel_rows = [{"channel": k, "count": v} for k, v in channels.most_common(20)]
    write_csv(OUT / "category_summary.csv", category_rows, ["category", "count"])
    write_csv(OUT / "service_summary.csv", service_rows, ["service", "count"])
    write_csv(OUT / "domain_summary.csv", domain_rows, ["domain", "count"])
    write_csv(OUT / "youtube_channel_summary.csv", channel_rows, ["channel", "count"])

    report = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Google 账号具体内容分析</title>
  <style>
    body {{ margin:0; background:#FCFCFD; color:#1F2430; font-family:"Segoe UI","Microsoft YaHei",Arial,sans-serif; line-height:1.65; }}
    main {{ max-width:1150px; margin:0 auto; padding:40px 24px 76px; }}
    h1 {{ font-size:30px; margin:0 0 18px; }}
    h2 {{ font-size:21px; margin:34px 0 12px; }}
    .summary {{ background:#fff; border:1px solid #E6E8F0; border-radius:8px; padding:18px 20px; }}
    .kpis {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin:20px 0; }}
    .kpi {{ background:#fff; border:1px solid #E6E8F0; border-radius:8px; padding:14px 16px; }}
    .kpi strong {{ display:block; font-size:24px; }}
    .kpi span {{ color:#6F768A; font-size:13px; }}
    img {{ width:100%; max-width:980px; display:block; margin:14px 0 6px; border:1px solid #E6E8F0; border-radius:8px; background:#fff; }}
    table {{ border-collapse:collapse; width:100%; background:#fff; border:1px solid #E6E8F0; margin:12px 0; table-layout:fixed; }}
    th,td {{ padding:8px 10px; border-bottom:1px solid #E6E8F0; text-align:left; vertical-align:top; word-break:break-word; }}
    th {{ background:#F4F5F7; }}
    .note {{ color:#6F768A; font-size:14px; }}
    code {{ background:#F4F5F7; padding:2px 5px; border-radius:4px; }}
  </style>
</head>
<body>
<main>
  <h1>Google 账号具体内容分析</h1>
  <section class="summary">
    <h2>Executive Summary</h2>
    <p><strong>这次已经进入具体内容层。</strong> 共抽取 {len(rows)} 条可读活动明细、{len(attachments)} 个 Gemini 附件、{len(map_rows)} 条地图结构化明细；明细表保留标题、查询、频道、域名和原始摘要。</p>
    <p><strong>主要内容主题不是单一兴趣，而是“AI/工具 + 时政社会 + 学习资料 + 账号金融操作”的组合。</strong> 这像注意力系统里的几条高频神经回路：一条服务学习/生产，一条服务信息观察，一条服务账号和支付操作。</p>
    <p><strong>完整可审计明细在 CSV，报告只展示样例和聚合。</strong> 具体原文可在 <code>full_activity_details.csv</code>、<code>search_queries.csv</code>、<code>youtube_items.csv</code>、<code>gemini_prompts.csv</code> 中查看。</p>
  </section>

  <div class="kpis">
    <div class="kpi"><strong>{len(rows)}</strong><span>活动明细</span></div>
    <div class="kpi"><strong>{len(search_queries)}</strong><span>Search 查询</span></div>
    <div class="kpi"><strong>{len(youtube_rows)}</strong><span>YouTube 条目</span></div>
    <div class="kpi"><strong>{len(gemini_rows)}</strong><span>Gemini prompt</span></div>
    <div class="kpi"><strong>{len(attachments)}</strong><span>Gemini 附件</span></div>
  </div>

  <section>
    <h2>内容主题分布</h2>
    <p><strong>分类结果显示，内容核心围绕 AI/编程工具、政治时政、学习资料、账号安全和支付金融。</strong> 分类由关键词完成，因此它适合快速导航，不等同于严格语义模型。</p>
    <img src="assets/content_categories.png" alt="具体内容主题分布">
    <table><thead><tr><th>主题</th><th>数量</th></tr></thead><tbody>{html_table(category_rows, ["category", "count"], 20)}</tbody></table>
  </section>

  <section>
    <h2>Search 具体内容样例</h2>
    <p><strong>Search 明细里能看到 AI 产品、账号、支付卡、浏览器安全、具体网站访问等意图。</strong> 这部分是“显性问题意识”：用户主动输入或点击的内容。</p>
    <table><thead><tr><th>时间</th><th>分类</th><th>查询/标题</th><th>域名</th></tr></thead><tbody>{html_table(search_queries, ["datetime", "category", "title_or_query", "domain"], 25)}</tbody></table>
  </section>

  <section>
    <h2>YouTube 具体内容样例</h2>
    <p><strong>YouTube 高频内容偏向时政社会、AI/科技、体育娱乐等。</strong> 频道统计能看出信息源结构，标题样例能看出实际观看主题。</p>
    <img src="assets/youtube_channels.png" alt="YouTube 高频频道">
    <table><thead><tr><th>时间</th><th>分类</th><th>标题</th><th>频道</th></tr></thead><tbody>{html_table(youtube_rows, ["datetime", "category", "title_or_query", "channel_or_source"], 25)}</tbody></table>
  </section>

  <section>
    <h2>Gemini / AI 具体内容样例</h2>
    <p><strong>Gemini 内容以问题排错、AI 工具额度、课程/技术资料解读为主。</strong> 它更像工作台和学习助手，而不是单纯聊天应用。</p>
    <table><thead><tr><th>时间</th><th>分类</th><th>Prompt / 标题</th><th>摘要</th></tr></thead><tbody>{html_table(gemini_rows, ["datetime", "category", "title_or_query", "raw_excerpt"], 18)}</tbody></table>
    <img src="assets/gemini_attachment_categories.png" alt="Gemini 附件主题">
  </section>

  <section>
    <h2>域名与地图结构化内容</h2>
    <p><strong>域名能揭示访问对象，地图 JSON 能揭示地点类数据是否存在。</strong> Chrome 历史本次导出较弱，主要可用的是 Search 访问记录和 Maps 结构化文件。</p>
    <img src="assets/visited_domains.png" alt="访问内容的主要域名">
    <table><thead><tr><th>域名</th><th>数量</th></tr></thead><tbody>{html_table(domain_rows, ["domain", "count"], 20)}</tbody></table>
    <table><thead><tr><th>地图文件</th><th>字段</th><th>内容</th><th>分类</th></tr></thead><tbody>{html_table(map_rows, ["source_file", "record_type", "name_or_value", "category"], 25)}</tbody></table>
  </section>

  <section>
    <h2>生成文件</h2>
    <p class="note">输出目录：<code>{html.escape(str(OUT))}</code></p>
    <ul>
      <li><code>full_activity_details.csv</code>：全部活动明细</li>
      <li><code>search_queries.csv</code>：Search 查询与访问</li>
      <li><code>youtube_items.csv</code>：YouTube 标题与频道</li>
      <li><code>gemini_prompts.csv</code>：Gemini prompt 和摘要</li>
      <li><code>gemini_attachments.csv</code>：Gemini 附件清单</li>
      <li><code>maps_extracted_details.csv</code>：地图结构化内容</li>
    </ul>
  </section>
</main>
</body>
</html>"""
    (OUT / "content_analysis_report.html").write_text(report, encoding="utf-8")

    summary = {
        "output": str(OUT),
        "activity_rows": len(rows),
        "search_rows": len(search_queries),
        "youtube_rows": len(youtube_rows),
        "gemini_rows": len(gemini_rows),
        "gemini_attachments": len(attachments),
        "map_rows": len(map_rows),
        "top_categories": category_rows[:10],
        "top_youtube_channels": channel_rows[:10],
        "top_domains": domain_rows[:10],
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
