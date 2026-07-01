from __future__ import annotations

import csv
import html
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import matplotlib.pyplot as plt
from matplotlib import font_manager
import seaborn as sns


ROOT = Path(r"C:\Users\li\Desktop\数据分析\Google\takeout-20260608T162603Z-17-001\Takeout")
OUT = Path(r"C:\Users\li\Desktop\数据分析\analysis_output\google_topics_report")
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
    "gold": "#FFE15B",
    "gold_dark": "#736422",
}

TOPIC_SERVICES = {
    "Gemini / AI": ["Gemini Apps", "AI Mode"],
    "Search / YouTube": ["Search", "YouTube"],
    "Chrome / Maps": ["Chrome History", "Maps"],
}


def read_text(path: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return path.read_text(encoding=enc, errors="replace")
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def parse_time(raw: str) -> datetime | None:
    raw = html.unescape(raw).strip()
    raw = re.sub(r"\s+", " ", raw).replace(" UTC", "").replace(" GMT", "")
    for fmt in ("%Y年%m月%d日 %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    return None


def strip_tags(value: str) -> str:
    value = re.sub(r"<script.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def extract_activity(path: Path, service: str) -> list[dict]:
    text = read_text(path)
    times = re.findall(r"(\d{4}年\d{1,2}月\d{1,2}日\s+\d{1,2}:\d{2}:\d{2}(?:\s+(?:UTC|GMT))?)", text)
    plain = strip_tags(text)
    verbs = Counter()
    for verb in ["搜索了", "访问了", "观看了", "使用了", "打开了", "查看了", "询问了", "已上传", "Created", "Viewed", "Searched", "Watched"]:
        count = plain.count(verb)
        if count:
            verbs[verb] = count
    events = []
    for raw in times:
        dt = parse_time(raw)
        if dt:
            events.append({"service": service, "datetime": dt.isoformat(timespec="seconds")})
    return events, verbs


def parse_chrome_history(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(read_text(path))
    except Exception:
        return []
    records = []
    stack = [data]
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            url = item.get("url") or item.get("URL")
            title = item.get("title") or item.get("Title") or ""
            time_value = item.get("time_usec") or item.get("last_visit_time") or item.get("time")
            if url:
                domain = urlparse(str(url)).netloc.lower().replace("www.", "")
                records.append({"domain": domain or "(unknown)", "title_len": len(str(title)), "has_time": bool(time_value)})
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return records


def json_shape(path: Path) -> tuple[str, int]:
    try:
        data = json.loads(read_text(path))
    except Exception:
        return "unreadable", 0
    if isinstance(data, list):
        return "list", len(data)
    if isinstance(data, dict):
        return "object", len(data)
    return type(data).__name__, 1


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def theme() -> None:
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
            "axes.labelcolor": TOKENS["ink"],
            "grid.color": TOKENS["grid"],
            "font.family": "sans-serif",
            "font.sans-serif": [font_name, "Microsoft YaHei", "Segoe UI", "Arial"],
            "axes.unicode_minus": False,
        },
    )


def add_header(fig, ax, title: str, subtitle: str) -> None:
    ax.set_title("")
    fig.subplots_adjust(top=0.78, left=0.2)
    left = ax.get_position().x0
    fig.text(left, 0.97, title, ha="left", va="top", fontsize=13, fontweight="semibold", color=TOKENS["ink"])
    fig.text(left, 0.91, subtitle, ha="left", va="top", fontsize=9, color=TOKENS["muted"])
    sns.despine(ax=ax)


def plot_topic_totals(rows: list[dict]) -> None:
    colors = [TOKENS["blue"], TOKENS["orange"], TOKENS["olive"]]
    edges = [TOKENS["blue_dark"], TOKENS["orange_dark"], TOKENS["olive_dark"]]
    fig, ax = plt.subplots(figsize=(8.5, 5), dpi=160)
    labels = [r["topic"] for r in rows]
    values = [r["events"] for r in rows]
    bars = ax.bar(labels, values, color=colors[: len(rows)], edgecolor=edges[: len(rows)])
    for bar, value in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{value:,}", ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("活动条数")
    add_header(fig, ax, "三个专题的活动量对比", "按 Gemini/AI、Search/YouTube、Chrome/Maps 聚合可解析时间戳")
    fig.savefig(ASSETS / "topic_totals.png", bbox_inches="tight")
    plt.close(fig)


def plot_monthly(rows: list[dict]) -> None:
    if not rows:
        return
    fig, ax = plt.subplots(figsize=(10.5, 5.5), dpi=160)
    palette = {"Gemini / AI": TOKENS["blue"], "Search / YouTube": TOKENS["orange"], "Chrome / Maps": TOKENS["olive"]}
    for topic in sorted(set(r["topic"] for r in rows)):
        part = [r for r in rows if r["topic"] == topic]
        ax.plot([r["month"] for r in part], [r["events"] for r in part], marker="o", linewidth=1.2, label=topic, color=palette.get(topic))
    ax.set_ylabel("活动条数")
    ax.set_xlabel("")
    ax.tick_params(axis="x", rotation=45)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.01), frameon=False, ncol=3)
    add_header(fig, ax, "三个专题的月度节律", "只统计可解析时间戳，趋势受各产品导出粒度影响")
    fig.savefig(ASSETS / "topic_monthly.png", bbox_inches="tight")
    plt.close(fig)


def plot_attachment_mix(rows: list[dict]) -> None:
    fig, ax = plt.subplots(figsize=(8.5, 5), dpi=160)
    data = sorted(rows, key=lambda r: r["files"], reverse=True)
    ax.barh([r["extension"] for r in reversed(data)], [r["files"] for r in reversed(data)], color=TOKENS["pink"], edgecolor=TOKENS["pink_dark"])
    ax.set_xlabel("文件数")
    add_header(fig, ax, "Gemini 附件格式构成", "按 Gemini Apps 文件夹统计，不读取图片/PDF/文档正文")
    fig.savefig(ASSETS / "gemini_attachment_mix.png", bbox_inches="tight")
    plt.close(fig)


def table_rows(rows: list[dict], fields: list[str]) -> str:
    out = []
    for r in rows:
        out.append("<tr>" + "".join(f"<td>{html.escape(str(r.get(f, '')))}</td>" for f in fields) + "</tr>")
    return "\n".join(out)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    theme()

    all_events = []
    verb_rows = []
    for service in ["Gemini Apps", "AI Mode", "Search", "YouTube", "Maps"]:
        path = ROOT / "我的活动" / service / "我的活动记录.html"
        if path.exists():
            events, verbs = extract_activity(path, service)
            all_events.extend(events)
            for verb, count in verbs.most_common():
                verb_rows.append({"service": service, "signal": verb, "count": count})

    chrome_records = parse_chrome_history(ROOT / "Chrome" / "历史记录.json")
    chrome_event_count = len(chrome_records)
    if chrome_event_count:
        for i in range(chrome_event_count):
            all_events.append({"service": "Chrome History", "datetime": ""})

    topic_rows = []
    for topic, services in TOPIC_SERVICES.items():
        count = sum(1 for e in all_events if e["service"] in services)
        topic_rows.append({"topic": topic, "events": count})

    month_counts = Counter()
    for e in all_events:
        if not e["datetime"]:
            continue
        topic = next((t for t, services in TOPIC_SERVICES.items() if e["service"] in services), None)
        if topic:
            month_counts[(topic, e["datetime"][:7])] += 1
    months = sorted({m for _, m in month_counts})
    monthly_rows = []
    for topic in TOPIC_SERVICES:
        for month in months:
            monthly_rows.append({"topic": topic, "month": month, "events": month_counts[(topic, month)]})

    gemini_dir = ROOT / "我的活动" / "Gemini Apps"
    gemini_files = [p for p in gemini_dir.rglob("*") if p.is_file()] if gemini_dir.exists() else []
    attach_counter = Counter(p.suffix.lower() or "(none)" for p in gemini_files if p.name != "我的活动记录.html")
    attach_rows = [{"extension": k, "files": v} for k, v in attach_counter.most_common()]

    maps_dir = ROOT / "Google 地图"
    maps_json_rows = []
    for path in maps_dir.rglob("*.json") if maps_dir.exists() else []:
        shape, count = json_shape(path)
        maps_json_rows.append({"file": str(path.relative_to(maps_dir)), "shape": shape, "top_level_count": count})

    chrome_domains = [{"domain": k, "visits": v} for k, v in Counter(r["domain"] for r in chrome_records).most_common(10)]

    plot_topic_totals(topic_rows)
    plot_monthly(monthly_rows)
    if attach_rows:
        plot_attachment_mix(attach_rows)

    write_csv(OUT / "topic_totals.csv", topic_rows, ["topic", "events"])
    write_csv(OUT / "topic_monthly.csv", monthly_rows, ["topic", "month", "events"])
    write_csv(OUT / "topic_activity_signals.csv", verb_rows, ["service", "signal", "count"])
    write_csv(OUT / "gemini_attachment_mix.csv", attach_rows, ["extension", "files"])
    write_csv(OUT / "chrome_top_domains.csv", chrome_domains, ["domain", "visits"])
    write_csv(OUT / "maps_json_inventory.csv", maps_json_rows, ["file", "shape", "top_level_count"])

    total_topic_events = sum(r["events"] for r in topic_rows)
    lead_topic = max(topic_rows, key=lambda r: r["events"]) if topic_rows else {"topic": "无", "events": 0}
    gemini_events = next((r["events"] for r in topic_rows if r["topic"] == "Gemini / AI"), 0)
    search_events = next((r["events"] for r in topic_rows if r["topic"] == "Search / YouTube"), 0)
    chrome_maps_events = next((r["events"] for r in topic_rows if r["topic"] == "Chrome / Maps"), 0)
    attachment_total = sum(r["files"] for r in attach_rows)

    report = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Google 账号三专题兴趣与使用分析</title>
  <style>
    body {{ margin: 0; background: #FCFCFD; color: #1F2430; font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif; line-height: 1.65; }}
    main {{ max-width: 1100px; margin: 0 auto; padding: 40px 24px 72px; }}
    h1 {{ font-size: 30px; margin: 0 0 18px; }}
    h2 {{ font-size: 21px; margin: 34px 0 12px; }}
    .summary {{ background: #fff; border: 1px solid #E6E8F0; border-radius: 8px; padding: 18px 20px; }}
    .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 20px 0; }}
    .kpi {{ background: #fff; border: 1px solid #E6E8F0; border-radius: 8px; padding: 14px 16px; }}
    .kpi strong {{ display: block; font-size: 24px; }}
    .kpi span {{ color: #6F768A; font-size: 13px; }}
    img {{ width: 100%; max-width: 980px; display: block; margin: 14px 0 6px; border: 1px solid #E6E8F0; border-radius: 8px; background: #fff; }}
    table {{ border-collapse: collapse; width: 100%; background: #fff; border: 1px solid #E6E8F0; margin: 12px 0; }}
    th, td {{ padding: 9px 11px; border-bottom: 1px solid #E6E8F0; text-align: left; }}
    th {{ background: #F4F5F7; }}
    .note {{ color: #6F768A; font-size: 14px; }}
    code {{ background: #F4F5F7; padding: 2px 5px; border-radius: 4px; }}
  </style>
</head>
<body>
<main>
  <h1>Google 账号三专题兴趣与使用分析</h1>
  <section class="summary">
    <h2>Executive Summary</h2>
    <p><strong>三专题里，{html.escape(lead_topic['topic'])} 是最强信号。</strong> 在可解析和可聚合的范围内，三个专题共计 {total_topic_events} 条信号，其中领先专题为 {lead_topic['events']} 条。</p>
    <p><strong>Gemini / AI 更像“学习与生产资料仓库”。</strong> Gemini 相关活动 {gemini_events} 条，附件 {attachment_total} 个；附件包含图片、PDF、文档等，适合继续做学习资料/任务主题归类，但当前未读取附件正文。</p>
    <p><strong>Search / YouTube 是兴趣入口，Chrome / Maps 是行为足迹入口。</strong> Search/YouTube 有 {search_events} 条可解析活动；Chrome/Maps 有 {chrome_maps_events} 条聚合信号。它们像大脑里的“注意力系统”和“行动地图”，要深入时必须先定脱敏边界。</p>
  </section>

  <div class="kpis">
    <div class="kpi"><strong>{gemini_events}</strong><span>Gemini / AI 信号</span></div>
    <div class="kpi"><strong>{search_events}</strong><span>Search / YouTube 信号</span></div>
    <div class="kpi"><strong>{chrome_maps_events}</strong><span>Chrome / Maps 信号</span></div>
    <div class="kpi"><strong>{attachment_total}</strong><span>Gemini 附件数</span></div>
  </div>

  <section>
    <h2>三个专题的强弱对比</h2>
    <p><strong>活动量先告诉我们应该把分析显微镜放在哪里。</strong> 当前报告只比较数量和节律，不暴露原始查询词、标题、URL 或位置名称。</p>
    <img src="assets/topic_totals.png" alt="三个专题的活动量对比">
    <table><thead><tr><th>专题</th><th>信号数</th></tr></thead><tbody>{table_rows(topic_rows, ["topic", "events"])}</tbody></table>
  </section>

  <section>
    <h2>月度节律显示兴趣和使用阶段</h2>
    <p><strong>趋势的作用是找“哪段时间值得回看”。</strong> 如果某个月 Gemini 或 YouTube 突然升高，下一步可以只在那个时间窗内做主题归类，降低隐私暴露面。</p>
    <img src="assets/topic_monthly.png" alt="三个专题的月度节律">
  </section>

  <section>
    <h2>Gemini / AI：先看附件，不读正文</h2>
    <p><strong>Gemini 目录里附件量高，说明这里不只是聊天记录，也包含学习材料和上传资料。</strong> 目前只统计扩展名；下一轮可以对文件名做脱敏关键词分类，或对 PDF/图片做受控 OCR。</p>
    <img src="assets/gemini_attachment_mix.png" alt="Gemini 附件格式构成">
    <table><thead><tr><th>格式</th><th>文件数</th></tr></thead><tbody>{table_rows(attach_rows, ["extension", "files"])}</tbody></table>
  </section>

  <section>
    <h2>Search / YouTube：适合做兴趣主题聚类</h2>
    <p><strong>Search 和 YouTube 是最适合做“兴趣谱系”的来源。</strong> 当前报告只用时间戳和服务名；如果继续深入，建议把查询词和视频标题先转成主题标签，例如课程、编程、AI、生活服务、娱乐，再删除原文。</p>
    <table><thead><tr><th>服务</th><th>动作信号</th><th>次数</th></tr></thead><tbody>{table_rows([r for r in verb_rows if r["service"] in ["Search", "YouTube"]], ["service", "signal", "count"])}</tbody></table>
  </section>

  <section>
    <h2>Chrome / Maps：当前更适合做盘点，不适合直接画像</h2>
    <p><strong>Chrome 历史导出很小，地图数据以结构化设置/贡献类文件为主。</strong> 这类数据包含高敏感足迹，应先做域名级、月份级、城市级聚合，避免展示具体 URL 和具体地点。</p>
    <table><thead><tr><th>Chrome 域名</th><th>记录数</th></tr></thead><tbody>{table_rows(chrome_domains, ["domain", "visits"])}</tbody></table>
    <table><thead><tr><th>地图文件</th><th>结构</th><th>顶层数量</th></tr></thead><tbody>{table_rows(maps_json_rows, ["file", "shape", "top_level_count"])}</tbody></table>
  </section>

  <section>
    <h2>Recommended Next Steps</h2>
    <ol>
      <li><strong>Gemini 深挖：</strong>按附件文件名和活动月份做学习/工作主题分类，不读取正文。</li>
      <li><strong>Search/YouTube 深挖：</strong>把查询词和标题映射为主题标签后删除原文，输出兴趣雷达图。</li>
      <li><strong>Chrome/Maps 深挖：</strong>只做域名/城市/月份聚合，禁止输出具体 URL、地址和坐标。</li>
    </ol>
  </section>

  <section>
    <h2>Caveats and Assumptions</h2>
    <p class="note">报告基于本地 Takeout：<code>{html.escape(str(ROOT))}</code>。本次未做正文抽取、OCR、URL 明细展示或位置明细展示；Chrome 历史导出仅 {chrome_event_count} 条可识别 URL 记录，因此 Chrome 结论只能视为数据盘点。</p>
  </section>
</main>
</body>
</html>"""
    (OUT / "report.html").write_text(report, encoding="utf-8")

    summary = {
        "output": str(OUT),
        "topic_totals": topic_rows,
        "gemini_attachment_total": attachment_total,
        "chrome_url_records": chrome_event_count,
        "maps_json_files": len(maps_json_rows),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
