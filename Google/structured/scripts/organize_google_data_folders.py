from __future__ import annotations

import csv
import json
import shutil
from collections import Counter
from pathlib import Path


MODULE = Path(__file__).resolve().parents[2]
SRC_ANALYSIS = MODULE / "分析数据" / "旧分析输出" / "google_content_analysis"
SRC_ANALYSIS_OUTPUT = MODULE / "分析数据" / "旧分析输出" / "analysis_output"
RAW_TAKEOUT = MODULE / "原始数据" / "Takeout"
STRUCTURED = MODULE / "结构化数据"
ANALYSIS = MODULE / "分析数据"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def copy_if_exists(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    if src.resolve() == dst.resolve():
        return
    ensure_dir(dst.parent)
    shutil.copy2(src, dst)


def safe_name(value: str) -> str:
    value = value.strip() or "未分类"
    for char in '<>:"/\\|?*':
        value = value.replace(char, "_")
    value = value.replace(" ", "")
    return value[:80]


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def copy_report_assets() -> None:
    reports = ensure_dir(ANALYSIS / "报告HTML")
    charts = ensure_dir(ANALYSIS / "图表PNG")

    copy_if_exists(SRC_ANALYSIS / "content_analysis_report.html", reports / "具体内容分析.html")
    copy_if_exists(SRC_ANALYSIS_OUTPUT / "google_takeout_report" / "report.html", reports / "账号数据概览.html")
    copy_if_exists(SRC_ANALYSIS_OUTPUT / "google_topics_report" / "report.html", reports / "三专题分析.html")

    for src_dir in [
        SRC_ANALYSIS / "assets",
        SRC_ANALYSIS_OUTPUT / "google_takeout_report" / "assets",
        SRC_ANALYSIS_OUTPUT / "google_topics_report" / "assets",
    ]:
        if not src_dir.exists():
            continue
        for path in src_dir.glob("*.png"):
            copy_if_exists(path, charts / path.name)


def copy_database_and_scripts() -> None:
    database_dir = ensure_dir(STRUCTURED / "SQLite数据库")
    scripts_dir = ensure_dir(STRUCTURED / "脚本")
    for name in ["google_data.sqlite", "google_data_schema.sql", "google_data_README.md"]:
        copy_if_exists(MODULE / name, database_dir / name)
    for path in (MODULE / "结构化数据" / "脚本").glob("*.py"):
        if path.name == Path(__file__).name:
            continue
        copy_if_exists(path, scripts_dir / path.name)
    copy_if_exists(Path(__file__), scripts_dir / Path(__file__).name)


def copy_detail_csvs() -> None:
    detail_dir = ensure_dir(STRUCTURED / "明细CSV")
    mapping = {
        "full_activity_details.csv": "00_全部活动明细.csv",
        "search_queries.csv": "01_Search查询与访问.csv",
        "youtube_items.csv": "02_YouTube标题与频道.csv",
        "gemini_prompts.csv": "03_Gemini提示词与摘要.csv",
        "gemini_attachments.csv": "04_Gemini附件清单.csv",
        "maps_extracted_details.csv": "05_地图结构化明细.csv",
        "category_summary.csv": "90_主题汇总.csv",
        "service_summary.csv": "91_服务汇总.csv",
        "domain_summary.csv": "92_域名汇总.csv",
        "youtube_channel_summary.csv": "93_YouTube频道汇总.csv",
    }
    for src_name, dst_name in mapping.items():
        dst = detail_dir / dst_name
        if dst.exists():
            continue
        copy_if_exists(SRC_ANALYSIS / src_name, dst)


def split_by_category_and_service() -> dict:
    current_details = STRUCTURED / "明细CSV" / "00_全部活动明细.csv"
    rows = read_csv(SRC_ANALYSIS / "full_activity_details.csv") or read_csv(current_details)
    fields = rows[0].keys() if rows else []
    category_counts = Counter()
    service_counts = Counter()

    by_category: dict[str, list[dict]] = {}
    by_service: dict[str, list[dict]] = {}
    for row in rows:
        category = row.get("category", "未分类") or "未分类"
        service = row.get("service", "未知服务") or "未知服务"
        by_category.setdefault(category, []).append(row)
        by_service.setdefault(service, []).append(row)
        category_counts[category] += 1
        service_counts[service] += 1

    for category, part in by_category.items():
        write_csv(STRUCTURED / "按主题分类" / f"{safe_name(category)}.csv", part, list(fields))

    for service, part in by_service.items():
        write_csv(STRUCTURED / "按服务分类" / f"{safe_name(service)}.csv", part, list(fields))

    return {
        "activity_rows": len(rows),
        "category_counts": dict(category_counts.most_common()),
        "service_counts": dict(service_counts.most_common()),
    }


def write_raw_index() -> None:
    raw_index_dir = ensure_dir(STRUCTURED / "原始数据索引")
    module_rows = []
    if RAW_TAKEOUT.exists():
        for child in sorted(RAW_TAKEOUT.iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir():
                files = [p for p in child.rglob("*") if p.is_file()]
                size = sum(p.stat().st_size for p in files)
                module_rows.append(
                    {
                        "module": child.name,
                        "file_count": len(files),
                        "size_mb": round(size / 1024 / 1024, 2),
                        "path": str(child),
                    }
                )
    write_csv(raw_index_dir / "takeout_modules_index.csv", module_rows, ["module", "file_count", "size_mb", "path"])
    (raw_index_dir / "README.md").write_text(
        "# 原始数据索引\n\n"
        f"原始 Takeout 数据保留在：`{RAW_TAKEOUT}`\n\n"
        "这里不复制整份原始数据，只生成模块索引，避免重复占用空间。\n",
        encoding="utf-8",
    )


def write_readme(summary: dict) -> None:
    readme = f"""# Google 数据模块

本模块按原始数据、结构化数据、分析数据三层组织。原始 Takeout 数据保留在：

`{RAW_TAKEOUT}`

## 目录结构

- `结构化数据/原始数据索引`：原始 Takeout 一级模块索引。
- `结构化数据/明细CSV`：从 Takeout 抽取出的可分析明细和汇总表。
- `结构化数据/SQLite数据库`：SQLite 数据库、schema、查询说明。
- `结构化数据/按主题分类`：按内容主题拆分的活动明细。
- `结构化数据/按服务分类`：按 Google 服务拆分的活动明细。
- `结构化数据/脚本`：分析、建库、整理脚本。
- `分析数据/报告HTML`：已生成的分析报告。
- `分析数据/图表PNG`：报告图表。

## 当前统计

- 活动明细：{summary.get("activity_rows", 0)}
- 主题分类：{len(summary.get("category_counts", {}))}
- 服务分类：{len(summary.get("service_counts", {}))}

## 主要主题

{chr(10).join(f"- {name}: {count}" for name, count in summary.get("category_counts", {}).items())}

## 主要服务

{chr(10).join(f"- {name}: {count}" for name, count in summary.get("service_counts", {}).items())}
"""
    (MODULE / "README.md").write_text(readme, encoding="utf-8")
    (ANALYSIS / "classification_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    write_raw_index()
    copy_detail_csvs()
    copy_report_assets()
    copy_database_and_scripts()
    summary = split_by_category_and_service()
    write_readme(summary)
    print(json.dumps({"module": str(MODULE), **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
