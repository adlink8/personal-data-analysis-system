"""数据管道统一入口。

把所有 build_* 步骤按依赖顺序串联，避免手动依次运行出错。
每步幂等，失败时打印错误并停止（不跳过，防止下游跑污染数据）。

管道步骤（固定顺序）:
  1  build_integrated_system    重建统合 SQLite（9张原始表）
  2  enrich_unified_events      语义增强（补文本/修分类/建跨模块链接）⚠ 必须紧跟步骤1
  3  build_merge_layer          去重折叠（叠加表，不破坏原数据）
  4  build_deep_profiles        模块画像 + 统合画像
  5  build_memory_store         记忆层基础表（tooling 工具偏好）
  6  build_capability_memory    能力记忆抽取
  7  build_context_memory       上下文记忆抽取（fact/project/habit）
  8  build_preference_memory    偏好记忆抽取（Google 关注偏好）
  9  build_memory_graph         记忆关系图谱构建
  10 build_vector_store         向量化 → ChromaDB（约 53s，支持 --resume）
  11 build_context_doc          生成 AI 长期上下文文档

用法:
  python 统合模块\\脚本\\run_pipeline.py               # 全量重跑（步骤 1-11）
  python 统合模块\\脚本\\run_pipeline.py --from 2      # 从步骤2开始（跳过重建库）
  python 统合模块\\脚本\\run_pipeline.py --only 3,4    # 只跑步骤3和4
  python 统合模块\\脚本\\run_pipeline.py --skip 10     # 跳过向量化（节省时间）
  python 统合模块\\脚本\\run_pipeline.py --dry-run     # 只打印顺序，不执行
  python 统合模块\\脚本\\run_pipeline.py --from 5 --skip 9,10  # 组合用法
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

# ===== 管道步骤定义 =====

SCRIPTS_DIR = Path(__file__).resolve().parent

STEPS: list[dict] = [
    {
        "num": 1,
        "name": "build_integrated_system",
        "desc": "重建统合 SQLite（⚠ 会删除并重建整个库文件）",
        "extra_args": [],
    },
    {
        "num": 2,
        "name": "enrich_unified_events",
        "desc": "语义增强：补真实文本 / 修复分类污染 / 建跨模块链接",
        "extra_args": [],
    },
    {
        "num": 3,
        "name": "build_merge_layer",
        "desc": "去重折叠：L1 真重复 / L2 同主题 / L3 保留（叠加表）",
        "extra_args": [],
    },
    {
        "num": 4,
        "name": "build_deep_profiles",
        "desc": "生成模块画像 + 统合画像（含 --use-merged 去重视图）",
        "extra_args": ["--use-merged"],
    },
    {
        "num": 5,
        "name": "build_memory_store",
        "desc": "记忆层：tooling 工具偏好记忆（Phase 04 Wave 3）",
        "extra_args": [],
    },
    {
        "num": 6,
        "name": "build_capability_memory",
        "desc": "记忆层：capability 能力使用记忆",
        "extra_args": [],
    },
    {
        "num": 7,
        "name": "build_context_memory",
        "desc": "记忆层：fact / project / habit 上下文记忆",
        "extra_args": [],
    },
    {
        "num": 8,
        "name": "build_preference_memory",
        "desc": "记忆层：preference 关注偏好记忆（Google 信号）",
        "extra_args": [],
    },
    {
        "num": 9,
        "name": "build_memory_graph",
        "desc": "记忆图谱：节点 + 5种跨类关系边",
        "extra_args": [],
    },
    {
        "num": 10,
        "name": "build_vector_store",
        "desc": "向量化 → ChromaDB personal_events（约 53s，支持断点续传）",
        "extra_args": ["--resume"],
    },
    {
        "num": 11,
        "name": "build_context_doc",
        "desc": "生成 AI 长期上下文文档 person_profile.md",
        "extra_args": [],
    },
]


# ===== CLI 参数解析 =====

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="个人数据分析项目管道统一入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--from", dest="from_step", type=int, default=1, metavar="N",
        help="从第 N 步开始运行（默认 1）",
    )
    p.add_argument(
        "--only", dest="only_steps", type=str, default="", metavar="N,N",
        help="只运行指定步骤，逗号分隔，如 --only 3,4",
    )
    p.add_argument(
        "--skip", dest="skip_steps", type=str, default="", metavar="N,N",
        help="跳过指定步骤，逗号分隔，如 --skip 10",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="只打印将要执行的步骤，不实际运行",
    )
    return p.parse_args()


def parse_step_list(s: str) -> set[int]:
    if not s.strip():
        return set()
    return {int(x.strip()) for x in s.split(",")}


# ===== 执行逻辑 =====

def select_steps(args: argparse.Namespace) -> list[dict]:
    only = parse_step_list(args.only_steps)
    skip = parse_step_list(args.skip_steps)

    result = []
    for step in STEPS:
        n = step["num"]
        if only and n not in only:
            continue
        if n < args.from_step:
            continue
        if n in skip:
            continue
        result.append(step)
    return result


def fmt_step(step: dict) -> str:
    return f"步骤 {step['num']:>2}  {step['name']:<35}  {step['desc']}"


def run_step(step: dict) -> tuple[bool, float]:
    script = SCRIPTS_DIR / f"{step['name']}.py"
    cmd = [sys.executable, str(script)] + step["extra_args"]

    print(f"\n{'='*70}")
    print(f"▶  {fmt_step(step)}")
    print(f"{'='*70}")

    t0 = time.time()
    ret = subprocess.run(cmd, cwd=str(SCRIPTS_DIR.parent.parent))
    elapsed = time.time() - t0

    if ret.returncode != 0:
        print(f"\n✗  步骤 {step['num']} 失败（exit {ret.returncode}），管道已中止。")
        print(f"   修复后可用 --from {step['num']} 从此步重跑。")
        return False, elapsed

    print(f"\n✓  步骤 {step['num']} 完成（{elapsed:.1f}s）")
    return True, elapsed


# ===== 主入口 =====

def main() -> None:
    args = parse_args()
    selected = select_steps(args)

    if not selected:
        print("没有匹配的步骤，请检查 --from / --only / --skip 参数。")
        sys.exit(1)

    print(f"\n{'='*70}")
    print("个人数据分析管道")
    print(f"{'='*70}")
    print(f"共 {len(selected)} 步将执行{'（dry-run 模式，不实际运行）' if args.dry_run else ''}：\n")
    for step in selected:
        marker = "  " if not args.dry_run else "──"
        print(f"  {marker} {fmt_step(step)}")
    print()

    if args.dry_run:
        return

    total_t0 = time.time()
    for step in selected:
        ok, _ = run_step(step)
        if not ok:
            sys.exit(1)

    total = time.time() - total_t0
    print(f"\n{'='*70}")
    print(f"✅  全部 {len(selected)} 步完成，总耗时 {total:.0f}s（{total/60:.1f} 分钟）")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
