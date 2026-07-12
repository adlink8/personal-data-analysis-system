"""Audit automated test coverage vs integration/scripts packages.

Detects top-level and deferred imports, importlib loads, and script path
string references. Emits markdown + JSON gap reports under ai_context/.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "integration" / "scripts"
TESTS = ROOT / "tests"
OUT_JSON = ROOT / "integration" / "analysis" / "ai_context" / "test_coverage_gaps.json"
OUT_MD = ROOT / "integration" / "analysis" / "ai_context" / "test_coverage_gaps.md"

PACKAGES = [
    "core",
    "knowledge",
    "memory",
    "conversation",
    "graph",
    "vector",
    "services",
    "pipeline",
    "source_adapters",
]

# Critical production-path modules (priority bump regardless of package)
CRITICAL_BASES = {
    "promote_knowledge_index",
    "reconcile_knowledge_index",
    "refresh_knowledge_units",
    "build_knowledge_unit_vector_store",
    "evaluate_knowledge_unit_rag",
    "build_knowledge_units_prod",
    "evaluate_knowledge_unit_extraction",
    "unified_search",
    "search_vectors",
    "api_server",
    "mcp_server",
    "run_pipeline",
    "run_import_pipeline",
    "knowledge_unit_pipeline",
    "build_canonical_knowledge_units",
    "rollback_knowledge_checkpoint",
}

# Heuristic functional areas expected in a healthy automated suite
FUNCTIONAL_EXPECTATIONS = [
    {
        "id": "ku_extract_gate",
        "title": "知识抽取 gate / pilot / retry",
        "modules": [
            "knowledge.build_knowledge_units",
            "knowledge.build_knowledge_units_prod",
            "knowledge.evaluate_knowledge_unit_extraction",
            "knowledge.knowledge_unit_pipeline",
        ],
        "test_patterns": ["knowledge_unit", "gate", "pilot", "retry", "extraction"],
    },
    {
        "id": "ku_canonical_index",
        "title": "canonical + vector index + promote",
        "modules": [
            "knowledge.build_canonical_knowledge_units",
            "knowledge.build_knowledge_unit_vector_store",
            "knowledge.promote_knowledge_index",
            "knowledge.reconcile_knowledge_index",
            "knowledge.rollback_knowledge_checkpoint",
        ],
        "test_patterns": ["canonical", "vector_store", "promotion", "index"],
    },
    {
        "id": "ku_incremental",
        "title": "增量 refresh / delta",
        "modules": ["knowledge.refresh_knowledge_units"],
        "test_patterns": ["incremental", "refresh"],
    },
    {
        "id": "ku_search_canary",
        "title": "知识检索 / canary / RAG eval",
        "modules": [
            "vector.unified_search",
            "knowledge.evaluate_knowledge_canary",
            "knowledge.evaluate_knowledge_unit_rag",
        ],
        "test_patterns": ["search", "canary", "rag"],
    },
    {
        "id": "access_layer",
        "title": "REST / MCP / Apps 数据访问",
        "modules": ["services.api_server", "services.mcp_server", "vector.unified_search"],
        "test_patterns": ["data_access", "apps_sdk", "api"],
    },
    {
        "id": "import_pipeline",
        "title": "导入管道",
        "modules": ["pipeline.run_import_pipeline"],
        "test_patterns": ["import_pipeline"],
    },
    {
        "id": "memory_promotion",
        "title": "记忆候选 / 晋升 / lifecycle",
        "modules": [
            "memory.build_memory_promotion_candidates",
            "memory.extract_memory_candidates_from_bundles",
            "memory.sync_memory_lifecycle",
        ],
        "test_patterns": ["memory_promotion", "memory_candidate", "lifecycle", "gate_repair"],
    },
    {
        "id": "graph_relations",
        "title": "图关系候选 / 判定",
        "modules": [
            "graph.build_graph_relation_candidates",
            "graph.build_graph_relation_candidates_v2",
            "graph.judge_graph_relations",
        ],
        "test_patterns": ["graph_relation"],
    },
    {
        "id": "conversation_canonical",
        "title": "会话规范化 / 回滚 / repository",
        "modules": [
            "conversation.build_agentsview_normalized",
            "conversation.rollback_agent_conversation_source",
            "core.conversation_repository",
        ],
        "test_patterns": ["agentsview", "conversation", "rollback"],
    },
    {
        "id": "full_pipeline",
        "title": "全量 run_pipeline 编排",
        "modules": ["pipeline.run_pipeline"],
        "test_patterns": ["run_pipeline", "pipeline"],
    },
]


def collect_impl() -> dict[str, Path]:
    impl: dict[str, Path] = {}
    for pkg in PACKAGES:
        d = SCRIPTS / pkg
        if not d.is_dir():
            continue
        for f in d.rglob("*.py"):
            if f.name.startswith("_") or f.name == "__init__.py":
                continue
            rel = f.relative_to(SCRIPTS).with_suffix("")
            impl[".".join(rel.parts)] = f
    return impl


def extract_module_refs(text: str) -> tuple[set[str], set[str]]:
    """Return (strong_refs, weak_refs).

    strong: actual import / import_module
    weak: path string mention only (e.g. protected file list)
    """
    strong: set[str] = set()
    weak: set[str] = set()

    def add(target: set[str], full: str) -> None:
        target.add(full)
        target.add(full.split(".")[0])
        target.add(full.split(".")[-1])

    for m in re.finditer(
        r"(?:from|import)\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)",
        text,
    ):
        add(strong, m.group(1))
    for m in re.finditer(
        r"import_module\(\s*['\"]([a-zA-Z_][a-zA-Z0-9_.]*)['\"]",
        text,
    ):
        add(strong, m.group(1))
    for m in re.finditer(
        r"['\"](?:(?:integration[/\\]scripts[/\\])?(?:[a-z_]+[/\\])?)([a-zA-Z_][a-zA-Z0-9_]*)\.py['\"]",
        text,
    ):
        weak.add(m.group(1))
    for m in re.finditer(
        r"/\s*['\"]([a-zA-Z_][a-zA-Z0-9_]*)\.py['\"]",
        text,
    ):
        weak.add(m.group(1))
    return strong, weak


def collect_test_imports() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    strong_map: dict[str, set[str]] = {}
    weak_map: dict[str, set[str]] = {}
    for tf in sorted(TESTS.glob("test_*.py")):
        text = tf.read_text(encoding="utf-8", errors="ignore")
        strong, weak = extract_module_refs(text)
        strong_map[tf.name] = strong
        weak_map[tf.name] = weak
    return strong_map, weak_map


def classify_priority(mod: str) -> str:
    pkg, base = mod.split(".", 1) if "." in mod else (mod, mod)
    if base in CRITICAL_BASES or pkg in ("knowledge", "vector", "services"):
        return "high"
    if pkg in ("memory", "conversation", "pipeline", "graph"):
        return "medium"
    return "low"


def main() -> int:
    impl = collect_impl()
    strong_map, weak_map = collect_test_imports()
    test_files = sorted(strong_map)
    test_imports = {
        tf: strong_map[tf] | weak_map.get(tf, set()) for tf in test_files
    }

    basename_to_mod = {m.split(".")[-1]: m for m in impl}
    covered_strong: dict[str, list[str]] = defaultdict(list)
    covered_weak_only: dict[str, list[str]] = defaultdict(list)

    for tf, mods in strong_map.items():
        for name in mods:
            if name in impl:
                covered_strong[name].append(tf)
            if name in basename_to_mod:
                covered_strong[basename_to_mod[name]].append(tf)

    for tf, mods in weak_map.items():
        for name in mods:
            resolved = name if name in impl else basename_to_mod.get(name)
            if not resolved:
                continue
            if resolved not in covered_strong:
                covered_weak_only[resolved].append(tf)

    covered_strong = {k: sorted(set(v)) for k, v in covered_strong.items()}
    covered_weak_only = {k: sorted(set(v)) for k, v in covered_weak_only.items()}
    # Primary "covered" = strong import coverage only
    covered = covered_strong
    uncovered = sorted(set(impl) - set(covered))
    covered_list = sorted(covered)

    # pytest collection
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests", "--collect-only", "-q"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    collect_out = (proc.stdout or "") + "\n" + (proc.stderr or "")
    broken: list[str] = []
    collect_count = None
    m_count = re.search(r"(\d+)\s+tests?\s+collected", collect_out)
    if m_count:
        collect_count = int(m_count.group(1))
    # also "307 tests collected" variants / trailing summary "xxx selected"
    if collect_count is None:
        m2 = re.search(r"^(\d+)\s+tests?\s+collected", collect_out, re.M)
        if m2:
            collect_count = int(m2.group(1))
    for line in collect_out.splitlines():
        if "ERROR collecting" in line or line.startswith("ERROR "):
            broken.append(line.strip())
        if "ModuleNotFoundError" in line or "ImportError" in line:
            broken.append(line.strip())

    high, medium, low = [], [], []
    for m in uncovered:
        bucket = classify_priority(m)
        if bucket == "high":
            high.append(m)
        elif bucket == "medium":
            medium.append(m)
        else:
            low.append(m)

    # functional coverage analysis (strong import only)
    functional = []
    for exp in FUNCTIONAL_EXPECTATIONS:
        mod_hits = [m for m in exp["modules"] if m in covered]
        mod_miss = [m for m in exp["modules"] if m not in covered]
        matching_tests = [
            t
            for t in test_files
            if any(p in t.lower() for p in exp["test_patterns"])
        ]
        if not mod_miss and matching_tests:
            status = "covered"
        elif mod_hits or matching_tests:
            status = "partial"
        else:
            status = "missing"
        functional.append(
            {
                "id": exp["id"],
                "title": exp["title"],
                "status": status,
                "modules_hit": mod_hits,
                "modules_miss": mod_miss,
                "matching_tests": matching_tests,
            }
        )

    by_pkg: dict[str, dict] = {}
    for m in impl:
        pkg = m.split(".")[0]
        by_pkg.setdefault(pkg, {"total": 0, "covered": 0, "uncovered": []})
        by_pkg[pkg]["total"] += 1
        if m in covered:
            by_pkg[pkg]["covered"] += 1
        else:
            by_pkg[pkg]["uncovered"].append(m.split(".", 1)[-1])
    for pkg, d in by_pkg.items():
        d["uncovered"] = sorted(d["uncovered"])
        d["ratio"] = round(d["covered"] / max(d["total"], 1), 4)

    missing_modules = sorted(
        {
            line.split("'")[1]
            for line in broken
            if "No module named" in line and "'" in line
        }
    )

    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "method": "strong=import/deferred/import_module; weak=path-string only (not line coverage)",
        "impl_modules": len(impl),
        "test_files": len(test_imports),
        "covered_modules": len(covered_list),
        "uncovered_modules": len(uncovered),
        "coverage_ratio": round(len(covered_list) / max(len(impl), 1), 4),
        "weak_only_modules": sorted(covered_weak_only),
        "weak_only_detail": covered_weak_only,
        "pytest_collect_returncode": proc.returncode,
        "pytest_collect_count": collect_count,
        "by_package": by_pkg,
        "uncovered": uncovered,
        "priority": {"high": high, "medium": medium, "low": low},
        "functional_areas": functional,
        "covered_detail": covered,
        "broken_collection_signals": broken[:40],
        "missing_modules_referenced_by_tests": missing_modules,
    }

    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md: list[str] = [
        "# 全自动测试缺漏审计",
        "",
        f"**生成时间:** {report['generated_at']}",
        "",
        "## 方法",
        "",
        "- **强覆盖**：`tests/test_*.py` 中的顶层 / 函数内 deferred `import`、`import_module(...)`。",
        "- **弱引用**：仅出现在路径字符串（如 protected 文件列表）——单独列出，**不计入**强覆盖率。",
        "- **不是** line/branch coverage。",
        "- 实现范围：`integration/scripts/{core,knowledge,memory,conversation,graph,vector,services,pipeline,source_adapters}/`（不含 shim 与 `_tools`）。",
        "",
        "## 总览",
        "",
        "| 指标 | 值 |",
        "|------|----|",
        f"| 实现模块（分包内） | **{report['impl_modules']}** |",
        f"| 测试文件 `test_*.py` | **{report['test_files']}** |",
        f"| 被测试引用的模块 | **{report['covered_modules']}** |",
        f"| 无直接测试引用的模块 | **{report['uncovered_modules']}** |",
        f"| 粗覆盖率（**强引用/import** 级） | **{report['coverage_ratio'] * 100:.1f}%** |",
        f"| 仅路径字符串弱引用 | **{len(covered_weak_only)}** |",
        f"| pytest collect | returncode={proc.returncode}"
        + (f", ~{collect_count} items" if collect_count else "")
        + " |",
        "",
        "## 功能域覆盖（业务视角）",
        "",
        "| 功能域 | 状态 | 触及测试 | 未引用关键模块 |",
        "|--------|------|----------|----------------|",
    ]
    status_icon = {"covered": "✅", "partial": "⚠️", "missing": "❌"}
    for f in functional:
        tests_s = ", ".join(f"`{t}`" for t in f["matching_tests"][:4]) or "—"
        if len(f["matching_tests"]) > 4:
            tests_s += f" …(+{len(f['matching_tests']) - 4})"
        miss_s = ", ".join(f"`{m}`" for m in f["modules_miss"][:4]) or "—"
        if len(f["modules_miss"]) > 4:
            miss_s += f" …(+{len(f['modules_miss']) - 4})"
        md.append(
            f"| {status_icon.get(f['status'], '?')} {f['title']} | {f['status']} | {tests_s} | {miss_s} |"
        )

    md += [
        "",
        "## 分包装覆盖",
        "",
        "| 包 | 覆盖/总数 | 比率 | 未覆盖模块 |",
        "|----|-----------|------|------------|",
    ]
    for pkg, d in sorted(by_pkg.items()):
        un = ", ".join(f"`{x}`" for x in d["uncovered"][:12])
        if len(d["uncovered"]) > 12:
            un += f" …(+{len(d['uncovered']) - 12})"
        md.append(
            f"| `{pkg}/` | {d['covered']}/{d['total']} | {d['ratio'] * 100:.0f}% | {un or '—'} |"
        )

    md += [
        "",
        "## 高优先级缺漏（建议优先补测）",
        "",
    ]
    if high:
        for m in high:
            md.append(f"- `{m}`")
    else:
        md.append("- （无）")

    md += ["", "## 中优先级缺漏", ""]
    if medium:
        for m in medium:
            md.append(f"- `{m}`")
    else:
        md.append("- （无）")

    md += ["", "## 低优先级 / 基础设施", ""]
    if low:
        for m in low:
            md.append(f"- `{m}`")
    else:
        md.append("- （无）")

    md += ["", "## 破损/过时测试（collect 失败）", ""]
    if missing_modules:
        md.append("测试仍 import 已不存在的模块：")
        for m in missing_modules:
            md.append(f"- `{m}`")
    if broken:
        md.append("")
        md.append("```")
        md.extend(broken[:30])
        md.append("```")
    else:
        md.append("- 未检测到 collect ERROR 信号")

    md += ["", "## 仅路径字符串弱引用（不算强覆盖）", ""]
    if covered_weak_only:
        for m, tfs in sorted(covered_weak_only.items()):
            md.append(f"- `{m}` ← {', '.join(tfs[:3])}")
    else:
        md.append("- （无）")

    md += [
        "",
        "## 建议补测清单（按性价比）",
        "",
        "### P0 — 生产知识链路（Phase 14 收口）",
        "",
        "1. **`knowledge.reconcile_knowledge_index`**：分页 ID、eligible 多 run 合并、checksum 匹配 / 不匹配、missing/orphan 报告（当前无直接 import 测试）。",
        "2. **`knowledge.evaluate_knowledge_unit_rag`**：pure / hybrid Recall 计算、secret hit=0、gate 字段契约（eval 脚本本身几乎无单测）。",
        "3. **`knowledge.rollback_knowledge_checkpoint`**：回滚 active pointer / journal 条目 dry-run。",
        "4. **`services.mcp_server`**：tool 列表 smoke + 至少一个 knowledge/memory tool 契约（仅 apps/api 有部分覆盖）。",
        "",
        "### P1 — 编排与检索入口",
        "",
        "5. **`pipeline.run_pipeline`**：`--dry-run` 步骤表解析、`--from` / `--only` / `--skip` 边界（当前多为路径字符串弱引用）。",
        "6. **`vector.search_vectors` / `vector.build_vector_store`**：import smoke + mock chroma 最小路径。",
        "7. **`services.dashboard`**：import / 路由表 smoke（低耦合即可）。",
        "",
        "### P2 — 管道 builder（仍在 run_pipeline 中）",
        "",
        "8. `pipeline.enrich_unified_events` / `build_integrated_system` / `build_merge_layer` 的 schema 或 dry 契约。",
        "9. 生产记忆 builder（`build_memory_store` 等）最小幂等/空库 smoke。",
        "10. conversation 质量评估脚本若仍用于发布门禁，补 golden 小样测试。",
        "",
        "### 已较强覆盖（勿重复建设）",
        "",
        "- promote / refresh / vector_store / extraction gate / canary / unified_search / api_server / import_pipeline / agentsview / graph relation 已有专项测试。",
        "",
        "## 已有较强覆盖（按引用测试数）",
        "",
    ]
    for m, tfs in sorted(covered.items(), key=lambda x: (-len(x[1]), x[0]))[:25]:
        md.append(f"- `{m}` ← {', '.join(tfs[:4])}" + (f" …(+{len(tfs) - 4})" if len(tfs) > 4 else ""))

    md += [
        "",
        f"机器可读：`{OUT_JSON.relative_to(ROOT).as_posix()}`",
        "",
        "重跑：",
        "",
        "```powershell",
        "python integration/scripts/_tools/_audit_test_gaps.py",
        "python -m pytest tests -q",
        "```",
        "",
    ]
    OUT_MD.write_text("\n".join(md), encoding="utf-8")

    summary = {
        "impl": report["impl_modules"],
        "covered_strong": report["covered_modules"],
        "uncovered": report["uncovered_modules"],
        "weak_only": len(covered_weak_only),
        "ratio": report["coverage_ratio"],
        "high_priority_gaps": len(high),
        "functional_missing": sum(1 for f in functional if f["status"] == "missing"),
        "functional_partial": sum(1 for f in functional if f["status"] == "partial"),
        "missing_modules": missing_modules,
        "out_md": str(OUT_MD),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
