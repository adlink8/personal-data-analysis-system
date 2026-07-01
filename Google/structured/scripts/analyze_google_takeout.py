from __future__ import annotations

import csv
import html
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager
import seaborn as sns


ROOT = Path(r"C:\Users\li\Desktop\数据分析\Google\takeout-20260608T162603Z-17-001\Takeout")
OUT = Path(r"C:\Users\li\Desktop\数据分析\analysis_output\google_takeout_report")
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
}


def safe_rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def read_text(path: Path) -> str:
    for enc in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            return path.read_text(encoding=enc, errors="replace")
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="replace")


def parse_google_time(raw: str) -> datetime | None:
    raw = html.unescape(raw).strip()
    raw = re.sub(r"\s+", " ", raw)
    patterns = [
        "%Y年%m月%d日 %H:%M:%S %Z",
        "%Y年%m月%d日 %H:%M:%S",
        "%Y-%m-%d %H:%M:%S %Z",
        "%Y-%m-%d %H:%M:%S",
    ]
    cleaned = raw.replace(" UTC", "").replace(" GMT", "")
    for fmt in patterns:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            pass
    for fmt in ("%Y年%m月%d日 %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            pass
    return None


def extract_activity_events(path: Path) -> list[dict]:
    text = read_text(path)
    # Google Takeout activity HTML normally has timestamps as "YYYY年M月D日 HH:MM:SS UTC".
    time_matches = re.findall(r"(\d{4}年\d{1,2}月\d{1,2}日\s+\d{1,2}:\d{2}:\d{2}(?:\s+(?:UTC|GMT))?)", text)
    service = path.parent.name
    events = []
    for value in time_matches:
        dt = parse_google_time(value)
        if dt:
            events.append({"service": service, "datetime": dt.isoformat(timespec="seconds")})
    return events


def load_json_shape(path: Path) -> tuple[str, int]:
    try:
        data = json.loads(read_text(path))
    except Exception:
        return "unreadable", 0
    if isinstance(data, list):
        return "list", len(data)
    if isinstance(data, dict):
        return "object", len(data)
    return type(data).__name__, 1


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def chart_theme() -> None:
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
            "font.sans-serif": [font_name, "Microsoft YaHei", "Segoe UI", "DejaVu Sans", "Arial"],
            "axes.unicode_minus": False,
        },
    )


def add_header(fig, ax, title: str, subtitle: str) -> None:
    ax.set_title("")
    fig.subplots_adjust(top=0.78, left=0.22)
    left = ax.get_position().x0
    fig.text(left, 0.97, title, ha="left", va="top", fontsize=13, fontweight="semibold", color=TOKENS["ink"])
    fig.text(left, 0.91, subtitle, ha="left", va="top", fontsize=9, color=TOKENS["muted"])
    sns.despine(ax=ax)


def plot_top_services(rows: list[dict]) -> None:
    data = sorted(rows, key=lambda r: r["events"], reverse=True)[:10]
    data = list(reversed(data))
    fig, ax = plt.subplots(figsize=(9, 5.4), dpi=160)
    ax.barh([r["service"] for r in data], [r["events"] for r in data], color=TOKENS["blue"], edgecolor=TOKENS["blue_dark"])
    ax.set_xlabel("活动条数")
    ax.set_ylabel("")
    add_header(fig, ax, "可解析活动主要集中在哪些服务", "按 Google Takeout 的“我的活动”HTML 时间戳统计，不展示活动正文")
    fig.savefig(ASSETS / "top_services.png", bbox_inches="tight")
    plt.close(fig)


def plot_monthly(month_rows: list[dict]) -> None:
    fig, ax = plt.subplots(figsize=(10, 5.2), dpi=160)
    ax.plot([r["month"] for r in month_rows], [r["events"] for r in month_rows], color=TOKENS["orange"], marker="o", linewidth=1.2)
    ax.set_xlabel("")
    ax.set_ylabel("活动条数")
    ax.tick_params(axis="x", rotation=45)
    add_header(fig, ax, "活动记录的月份分布", "只统计可解析时间戳；时间密度受 Google 导出范围和各产品记录策略影响")
    fig.savefig(ASSETS / "activity_by_month.png", bbox_inches="tight")
    plt.close(fig)


def plot_file_mix(rows: list[dict]) -> None:
    data = sorted(rows, key=lambda r: r["files"], reverse=True)[:10]
    data = list(reversed(data))
    fig, ax = plt.subplots(figsize=(9, 5.2), dpi=160)
    ax.barh([r["module"] for r in data], [r["files"] for r in data], color=TOKENS["olive"], edgecolor=TOKENS["olive_dark"])
    ax.set_xlabel("文件数")
    ax.set_ylabel("")
    add_header(fig, ax, "导出文件最多的模块", "按 Takeout 一级目录统计，反映数据体量而非重要性")
    fig.savefig(ASSETS / "top_modules_by_files.png", bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ASSETS.mkdir(parents=True, exist_ok=True)
    chart_theme()

    files = [p for p in ROOT.rglob("*") if p.is_file()]
    top_counter = Counter(p.relative_to(ROOT).parts[0] if p.relative_to(ROOT).parts else "(root)" for p in files)
    size_by_top = defaultdict(int)
    ext_counter = Counter()
    for p in files:
        top = p.relative_to(ROOT).parts[0] if p.relative_to(ROOT).parts else "(root)"
        size_by_top[top] += p.stat().st_size
        ext_counter[p.suffix.lower() or "(none)"] += 1

    module_rows = [
        {"module": k, "files": top_counter[k], "size_mb": round(size_by_top[k] / 1024 / 1024, 2)}
        for k in sorted(top_counter)
    ]
    ext_rows = [{"extension": k, "files": v} for k, v in ext_counter.most_common()]

    json_rows = []
    for p in sorted(ROOT.rglob("*.json")):
        shape, count = load_json_shape(p)
        json_rows.append({"path": safe_rel(p), "shape": shape, "top_level_count": count, "size_kb": round(p.stat().st_size / 1024, 1)})

    activity_events = []
    for p in sorted((ROOT / "我的活动").rglob("*.html")) if (ROOT / "我的活动").exists() else []:
        activity_events.extend(extract_activity_events(p))

    service_counts = Counter(e["service"] for e in activity_events)
    service_rows = [{"service": k, "events": v} for k, v in service_counts.most_common()]
    month_counts = Counter(e["datetime"][:7] for e in activity_events)
    month_rows = [{"month": k, "events": month_counts[k]} for k in sorted(month_counts)]

    write_csv(OUT / "module_inventory.csv", module_rows, ["module", "files", "size_mb"])
    write_csv(OUT / "file_extension_summary.csv", ext_rows, ["extension", "files"])
    write_csv(OUT / "json_shape_inventory.csv", json_rows, ["path", "shape", "top_level_count", "size_kb"])
    write_csv(OUT / "activity_service_counts.csv", service_rows, ["service", "events"])
    write_csv(OUT / "activity_month_counts.csv", month_rows, ["month", "events"])

    plot_file_mix(module_rows)
    if service_rows:
        plot_top_services(service_rows)
    if month_rows:
        plot_monthly(month_rows)

    total_size_mb = round(sum(p.stat().st_size for p in files) / 1024 / 1024, 2)
    first_month = month_rows[0]["month"] if month_rows else "未解析到"
    last_month = month_rows[-1]["month"] if month_rows else "未解析到"
    top_module = max(module_rows, key=lambda r: r["files"]) if module_rows else {"module": "无", "files": 0}
    top_service = service_rows[0] if service_rows else {"service": "未解析到", "events": 0}

    top_modules_html = "\n".join(
        f"<tr><td>{html.escape(r['module'])}</td><td>{r['files']}</td><td>{r['size_mb']}</td></tr>"
        for r in sorted(module_rows, key=lambda x: x["files"], reverse=True)[:12]
    )
    top_services_html = "\n".join(
        f"<tr><td>{html.escape(r['service'])}</td><td>{r['events']}</td></tr>"
        for r in service_rows[:12]
    )
    ext_html = "\n".join(
        f"<tr><td>{html.escape(r['extension'])}</td><td>{r['files']}</td></tr>"
        for r in ext_rows[:12]
    )

    report = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Google Takeout 账号数据概览</title>
  <style>
    body {{ margin: 0; background: #FCFCFD; color: #1F2430; font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif; line-height: 1.65; }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 40px 24px 72px; }}
    h1 {{ font-size: 30px; margin: 0 0 18px; letter-spacing: 0; }}
    h2 {{ font-size: 21px; margin: 34px 0 12px; }}
    h3 {{ font-size: 16px; margin: 24px 0 10px; }}
    .summary {{ background: #fff; border: 1px solid #E6E8F0; border-radius: 8px; padding: 18px 20px; }}
    .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin: 20px 0; }}
    .kpi {{ background: #fff; border: 1px solid #E6E8F0; border-radius: 8px; padding: 14px 16px; }}
    .kpi strong {{ display: block; font-size: 24px; }}
    .kpi span {{ color: #6F768A; font-size: 13px; }}
    img {{ width: 100%; max-width: 960px; display: block; margin: 14px 0 6px; border: 1px solid #E6E8F0; border-radius: 8px; background: #fff; }}
    table {{ border-collapse: collapse; width: 100%; background: #fff; border: 1px solid #E6E8F0; border-radius: 8px; overflow: hidden; }}
    th, td {{ padding: 9px 11px; border-bottom: 1px solid #E6E8F0; text-align: left; }}
    th {{ background: #F4F5F7; }}
    .note {{ color: #6F768A; font-size: 14px; }}
    code {{ background: #F4F5F7; padding: 2px 5px; border-radius: 4px; }}
  </style>
</head>
<body>
<main>
  <h1>Google Takeout 账号数据概览</h1>
  <section class="summary">
    <h2>Executive Summary</h2>
    <p><strong>这份导出更像“Google 账号活动与产品足迹体检”，不是完整行为画像。</strong> 本次分析发现 {len(files)} 个文件、{len(module_rows)} 个一级模块、约 {total_size_mb} MB 数据；文件最多的模块是 <strong>{html.escape(top_module['module'])}</strong>。</p>
    <p><strong>可结构化分析的主轴是“我的活动”。</strong> 从活动 HTML 中解析到 {len(activity_events)} 条带时间戳记录，覆盖 {first_month} 到 {last_month}；活动最多的服务是 <strong>{html.escape(top_service['service'])}</strong>。</p>
    <p><strong>隐私上，下一步应按问题逐层深入。</strong> 当前报告只做聚合统计，不展示搜索、聊天、联系人、付款或具体页面内容；如果要研究学习、AI 使用、消费或地图轨迹，应单独开专题并先定义脱敏规则。</p>
  </section>

  <div class="kpis">
    <div class="kpi"><strong>{len(files)}</strong><span>总文件数</span></div>
    <div class="kpi"><strong>{len(module_rows)}</strong><span>Takeout 一级模块</span></div>
    <div class="kpi"><strong>{total_size_mb} MB</strong><span>本次导出体量</span></div>
    <div class="kpi"><strong>{len(activity_events)}</strong><span>可解析活动时间戳</span></div>
  </div>

  <section>
    <h2>数据资产集中在少数模块</h2>
    <p><strong>文件数量最高的模块不等于最敏感，但它告诉我们从哪里开始审计最划算。</strong> 大量图片和附件集中在活动相关目录，像神经系统里突触最多的区域，后续专题分析应先处理这些高密度区域的隐私边界。</p>
    <img src="assets/top_modules_by_files.png" alt="导出文件最多的模块">
    <table><thead><tr><th>模块</th><th>文件数</th><th>大小 MB</th></tr></thead><tbody>{top_modules_html}</tbody></table>
  </section>

  <section>
    <h2>活动时间线可用于识别使用节律</h2>
    <p><strong>时间戳足以做节律分析，但还不足以解释原因。</strong> 月份趋势能看出活跃期和沉默期；要解释“为什么某月升高”，需要进一步读取对应服务的活动类别或文件附件来源。</p>
    <img src="assets/activity_by_month.png" alt="活动记录的月份分布">
  </section>

  <section>
    <h2>服务分布显示主要行为入口</h2>
    <p><strong>服务排名能帮助决定专题分析顺序。</strong> 如果排名靠前的是 Gemini、Search、YouTube 或 Maps，下一轮可以分别分析 AI 学习材料、搜索兴趣、内容消费或位置相关足迹，但每个方向都需要不同脱敏策略。</p>
    <img src="assets/top_services.png" alt="可解析活动主要集中在哪些服务">
    <table><thead><tr><th>服务</th><th>活动条数</th></tr></thead><tbody>{top_services_html}</tbody></table>
  </section>

  <section>
    <h2>文件格式决定后续分析能力</h2>
    <p><strong>JSON 和 CSV 是最适合自动分析的结构化来源，HTML 适合做时间和服务聚合，图片/PDF 更适合附件清点。</strong> 本次没有把图片/PDF 内容 OCR 或全文抽取，避免扩大隐私暴露面。</p>
    <table><thead><tr><th>扩展名</th><th>文件数</th></tr></thead><tbody>{ext_html}</tbody></table>
  </section>

  <section>
    <h2>Recommended Next Steps</h2>
    <ol>
      <li><strong>先定专题：</strong>AI/Gemini 使用、搜索兴趣、YouTube 内容、地图足迹、Chrome 历史、消费记录中选一个深入。</li>
      <li><strong>先定脱敏：</strong>默认只保留日期、服务、类别、数量；正文、URL、联系人、交易对象不进报告。</li>
      <li><strong>再做细分：</strong>按月份、星期、小时、产品类别做趋势和异常点解释。</li>
    </ol>
  </section>

  <section>
    <h2>Caveats and Assumptions</h2>
    <p class="note">本报告基于本地 Google Takeout 文件夹：<code>{html.escape(str(ROOT))}</code>。活动统计来自 HTML 时间戳抽取，不保证覆盖所有 Google 产品行为；Google 各产品的导出粒度不同，因此本报告用于数据盘点和分析路线选择，不应被视为完整账号审计。</p>
  </section>
</main>
</body>
</html>"""
    (OUT / "report.html").write_text(report, encoding="utf-8")

    summary = {
        "root": str(ROOT),
        "output": str(OUT),
        "files": len(files),
        "modules": len(module_rows),
        "total_size_mb": total_size_mb,
        "activity_events": len(activity_events),
        "activity_first_month": first_month,
        "activity_last_month": last_month,
        "top_module_by_files": top_module,
        "top_activity_service": top_service,
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
