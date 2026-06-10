from __future__ import annotations

import csv
import json
import shutil
from collections import Counter
from pathlib import Path


MODULE = Path(__file__).resolve().parents[2]
RAW = MODULE / "原始数据"
RESULTS = MODULE / "分析数据" / "旧处理结果" / "处理结果"
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


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def safe_name(value: str) -> str:
    value = value.strip() or "未分类"
    for char in '<>:"/\\|?*':
        value = value.replace(char, "_")
    return value.replace(" ", "")[:80]


def raw_index() -> dict:
    rows = []
    ext_counter = Counter()
    total_files = 0
    total_size = 0
    for path in RAW.rglob("*") if RAW.exists() else []:
        if not path.is_file():
            continue
        total_files += 1
        total_size += path.stat().st_size
        ext = path.suffix.lower() or "(none)"
        ext_counter[ext] += 1
        rows.append(
            {
                "relative_path": str(path.relative_to(RAW)),
                "extension": ext,
                "size_kb": round(path.stat().st_size / 1024, 1),
                "source_path": str(path),
            }
        )
    write_csv(STRUCTURED / "原始数据索引" / "raw_files_index.csv", rows, ["relative_path", "extension", "size_kb", "source_path"])
    return {"raw_file_count": total_files, "raw_size_mb": round(total_size / 1024 / 1024, 2), "raw_extensions": dict(ext_counter.most_common())}


def copy_reports_charts_database() -> dict:
    report_dir = ANALYSIS / "报告HTML"
    chart_dir = ANALYSIS / "图表PNG"
    db_dir = STRUCTURED / "SQLite数据库"
    script_dir = STRUCTURED / "脚本"

    for path in (RESULTS / "分析报告").glob("*.html") if (RESULTS / "分析报告").exists() else []:
        copy_if_exists(path, report_dir / path.name)
    for path in (RESULTS / "数据库").glob("*.html") if (RESULTS / "数据库").exists() else []:
        copy_if_exists(path, report_dir / path.name)
    for path in (RESULTS / "分析报告" / "charts").glob("*.png") if (RESULTS / "分析报告" / "charts").exists() else []:
        copy_if_exists(path, chart_dir / path.name)
    for path in (RESULTS / "数据库").glob("*.db") if (RESULTS / "数据库").exists() else []:
        copy_if_exists(path, db_dir / path.name)
    for path in (RESULTS / "分析报告").glob("*.py") if (RESULTS / "分析报告").exists() else []:
        copy_if_exists(path, script_dir / path.name)
    copy_if_exists(Path(__file__), script_dir / Path(__file__).name)

    return {
        "reports": len(list(report_dir.glob("*.html"))) if report_dir.exists() else 0,
        "charts": len(list(chart_dir.glob("*.png"))) if chart_dir.exists() else 0,
        "databases": len(list(db_dir.glob("*.db"))) if db_dir.exists() else 0,
    }


def copy_detail_data() -> dict:
    detail_dir = STRUCTURED / "明细数据"
    clean_dir = RESULTS / "清洗结果"
    mapping = {
        "chatgpt_qa_pairs.csv": "chatgpt_qa_pairs.csv",
        "chatgpt_qa_pairs.jsonl": "chatgpt_qa_pairs.jsonl",
        "chatgpt_清洗结果.xlsx": "chatgpt_清洗结果.xlsx",
    }
    for src_name, dst_name in mapping.items():
        copy_if_exists(clean_dir / src_name, detail_dir / dst_name)
    copy_if_exists(RESULTS / "分析报告" / "重要对话排行榜.json", detail_dir / "重要对话排行榜.json")
    copy_if_exists(RESULTS / "分析报告" / "chatgpt_聊天数据分析_source_notes.json", detail_dir / "source_notes.json")

    counts = {}
    csv_path = clean_dir / "chatgpt_qa_pairs.csv"
    if not csv_path.exists():
        csv_path = detail_dir / "chatgpt_qa_pairs.csv"
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
            counts["qa_pairs_rows"] = max(sum(1 for _ in f) - 1, 0)
    return counts


def split_outputs_by_file_type() -> dict:
    type_dir = STRUCTURED / "按文件类型分类"
    files = [p for p in RESULTS.rglob("*") if p.is_file()] if RESULTS.exists() else []
    counter = Counter()
    for path in files:
        ext = path.suffix.lower() or "no_extension"
        counter[ext] += 1
        copy_if_exists(path, type_dir / safe_name(ext.lstrip(".") or "no_extension") / path.name)
    return {"result_extensions": dict(counter.most_common())}


def split_raw_attachments_by_type() -> dict:
    attach_dir = STRUCTURED / "原始附件按类型"
    files = [p for p in RAW.rglob("*") if p.is_file()] if RAW.exists() else []
    counter = Counter()
    for path in files:
        ext = path.suffix.lower() or "no_extension"
        if path.name in {"conversations.json", "chat.html", "export_manifest.json", "user.json", "user_settings.json", "library_files.json", "message_feedback.json"}:
            group = "导出核心文件"
        elif ext in {".png", ".jpg", ".jpeg", ".webp"}:
            group = "图片附件"
        elif ext in {".pptx", ".pdf", ".docx", ".xlsx", ".csv"}:
            group = "文档表格附件"
        elif ext in {".json", ".jsonl", ".html"}:
            group = "结构化和网页文件"
        else:
            group = "其他附件"
        counter[group] += 1
        # Only index large/raw attachments by path; copying all raw files would duplicate export size.
    rows = [{"group": group, "file_count": count} for group, count in counter.most_common()]
    write_csv(attach_dir / "raw_attachment_type_summary.csv", rows, ["group", "file_count"])
    return {"raw_attachment_groups": dict(counter.most_common())}


def write_readme(summary: dict) -> None:
    readme = f"""# GPT 数据模块

本模块按原始数据、结构化数据、分析数据三层组织。原始导出数据保留在：

`{RAW}`

## 目录结构

- `结构化数据/原始数据索引`：GPT 原始导出文件索引。
- `结构化数据/明细数据`：清洗后的 CSV / JSONL / XLSX 和分析用 JSON。
- `结构化数据/SQLite数据库`：ChatGPT SQLite 数据库。
- `结构化数据/按文件类型分类`：处理结果按扩展名复制归类。
- `结构化数据/原始附件按类型`：原始导出附件类型汇总，不复制大体量原始附件。
- `结构化数据/脚本`：分析和整理脚本。
- `分析数据/报告HTML`：分析报告和数据库仪表盘。
- `分析数据/图表PNG`：报告图表。

## 当前统计

- 原始文件：{summary.get("raw_file_count", 0)}
- 原始体量 MB：{summary.get("raw_size_mb", 0)}
- QA 明细行：{summary.get("qa_pairs_rows", 0)}
- 报告 HTML：{summary.get("reports", 0)}
- 图表 PNG：{summary.get("charts", 0)}
- SQLite 数据库：{summary.get("databases", 0)}

## 原始附件分组

{chr(10).join(f"- {name}: {count}" for name, count in summary.get("raw_attachment_groups", {}).items())}
"""
    (MODULE / "README.md").write_text(readme, encoding="utf-8")
    (ANALYSIS / "classification_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    summary = {}
    summary.update(raw_index())
    summary.update(copy_detail_data())
    summary.update(copy_reports_charts_database())
    summary.update(split_outputs_by_file_type())
    summary.update(split_raw_attachments_by_type())
    write_readme(summary)
    print(json.dumps({"module": str(MODULE), **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
