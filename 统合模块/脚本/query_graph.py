"""记忆图谱查询与可视化(里程碑5b)。

提供两类能力:
  1. 图遍历查询(命令行)
     - neighbors:  某节点的N跳邻居("从Codex出发2跳能到什么?")
     - path:        两节点最短路径("ASMR和GSD怎么关联?")
     - common:      共同邻居("哪些记忆同时连了Codex和Claude?")
     - hub:         枢纽节点(连接最多的)
     - component:   连通分量(图里有几个"岛")
  2. 交互式可视化(pyvis → HTML)
     浏览器打开,可拖拽/缩放/点击节点查看详情

运行:
  python 统合模块\\脚本\\query_graph.py visualize           # 生成可视化HTML
  python 统合模块\\脚本\\query_graph.py neighbors "Codex" 2 # 查2跳邻居
  python 统合模块\\脚本\\query_graph.py path "Codex" "ASMR/助眠放松"
  python 统合模块\\脚本\\query_graph.py common "Codex" "Claude"
  python 统合模块\\脚本\\query_graph.py hub                 # 枢纽节点
"""

from __future__ import annotations

import json
import sqlite3
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ensure_dirs

import networkx as nx


ROOT = Path(__file__).resolve().parents[2]
UNIFIED_DB = ROOT / "统合模块" / "SQLite数据库" / "personal_system.sqlite"
ANALYSIS_DIR = ROOT / "统合模块" / "分析数据"

# 节点配色(按 memory_type)
TYPE_COLORS = {
    "tooling": "#3b82f6",     # 蓝
    "preference": "#10b981",  # 绿
    "capability": "#f59e0b",  # 橙
    "fact": "#8b5cf6",        # 紫
    "project": "#ec4899",     # 粉
    "habit": "#06b6d4",       # 青
}

# 边配色(按 relation)
RELATION_COLORS = {
    "uses_tool": "#3b82f6",
    "relates_to_topic": "#10b981",
    "enables": "#8b5cf6",
    "embodies": "#06b6d4",
    "same_subject": "#ef4444",
}


def load_graph(con: sqlite3.Connection) -> tuple[nx.MultiDiGraph, dict]:
    """从数据库加载图。返回 (G, node_info)。"""
    memories = {}
    for r in con.execute(
        "SELECT memory_id, memory_type, memory_subtype, subject, description "
        "FROM memory_items WHERE NOT (memory_type='capability' AND memory_subtype='minor_capability')"
    ):
        memories[r[0]] = {
            "memory_id": r[0], "memory_type": r[1], "memory_subtype": r[2],
            "subject": r[3], "description": r[4],
        }

    G = nx.MultiDiGraph()
    for mid, m in memories.items():
        G.add_node(mid, **m)
    for r in con.execute(
        "SELECT from_memory_id, to_memory_id, relation, strength FROM memory_relations"
    ):
        if r[0] in memories and r[1] in memories:
            G.add_edge(r[0], r[1], relation=r[2], strength=r[3])
    return G, memories


def find_node_by_subject(G: nx.MultiDiGraph, subject: str) -> str | None:
    """按 subject 模糊找节点。"""
    subject_lower = subject.lower().strip()
    # 精确匹配
    for n, d in G.nodes(data=True):
        if d.get("subject", "").lower() == subject_lower:
            return n
    # 包含匹配
    for n, d in G.nodes(data=True):
        if subject_lower in d.get("subject", "").lower():
            return n
    return None


def cmd_neighbors(G, args):
    """N跳邻居查询。"""
    if len(args) < 2:
        print("用法: neighbors <subject> <跳数>")
        return
    subject, hops = args[0], int(args[1])
    node = find_node_by_subject(G, subject)
    if not node:
        print(f"❌ 找不到节点: {subject}")
        return

    # 用弱连通的N跳邻居(忽略方向)
    undirected = G.to_undirected()
    neighbors = set()
    current = {node}
    for h in range(hops):
        next_level = set()
        for n in current:
            next_level.update(undirected.neighbors(n))
        next_level -= neighbors | current | {node}
        neighbors |= next_level
        current = next_level
        if not current:
            break

    subj = G.nodes[node]["subject"]
    print(f"\n📡 从 [{subj}] 出发 {hops} 跳邻居({len(neighbors)} 个):\n")
    # 按层级展示
    current = {node}
    visited = {node}
    for h in range(1, hops + 1):
        next_level = set()
        for n in current:
            for nb in undirected.neighbors(n):
                if nb not in visited:
                    next_level.add(nb)
                    visited.add(nb)
        if next_level:
            print(f"  第{h}跳:")
            for nb in next_level:
                d = G.nodes[nb]
                print(f"    [{d['memory_type']:11s}] {d['subject']}")
            current = next_level
        else:
            break


def cmd_path(G, args):
    """最短路径查询。"""
    if len(args) < 2:
        print("用法: path <subject1> <subject2>")
        return
    n1 = find_node_by_subject(G, args[0])
    n2 = find_node_by_subject(G, args[1])
    if not n1:
        print(f"❌ 找不到节点: {args[0]}")
        return
    if not n2:
        print(f"❌ 找不到节点: {args[1]}")
        return

    undirected = G.to_undirected()
    try:
        path = nx.shortest_path(undirected, n1, n2)
    except nx.NetworkXNoPath:
        s1 = G.nodes[n1]["subject"]
        s2 = G.nodes[n2]["subject"]
        print(f"\n🚫 [{s1}] 和 [{s2}] 之间没有路径(在不同连通分量)")
        return

    print(f"\n🛣️  最短路径({len(path)-1} 跳):\n")
    for i, n in enumerate(path):
        d = G.nodes[n]
        prefix = "  起点" if i == 0 else ("  终点" if i == len(path) - 1 else f"  第{i}跳")
        print(f"{prefix}: [{d['memory_type']:11s}] {d['subject']}")
        if i < len(path) - 1:
            # 找边的relation
            edge_data = G.get_edge_data(n, path[i + 1]) or G.get_edge_data(path[i + 1], n)
            if edge_data:
                rels = list(edge_data.values())
                rel = rels[0].get("relation", "?")
                print(f"         └──{rel}──>")


def cmd_common(G, args):
    """共同邻居查询。"""
    if len(args) < 2:
        print("用法: common <subject1> <subject2>")
        return
    n1 = find_node_by_subject(G, args[0])
    n2 = find_node_by_subject(G, args[1])
    if not n1 or not n2:
        print("❌ 找不到节点")
        return

    undirected = G.to_undirected()
    nb1 = set(undirected.neighbors(n1))
    nb2 = set(undirected.neighbors(n2))
    common = nb1 & nb2

    s1, s2 = G.nodes[n1]["subject"], G.nodes[n2]["subject"]
    print(f"\n🔗 [{s1}] 和 [{s2}] 的共同邻居({len(common)} 个):\n")
    for c in common:
        d = G.nodes[c]
        print(f"  [{d['memory_type']:11s}] {d['subject']}")
    if not common:
        print("  (无共同邻居)")


def cmd_hub(G, args):
    """枢纽节点(度数最高)。"""
    undirected = G.to_undirected()
    degrees = sorted(undirected.degree(), key=lambda x: -x[1])
    print(f"\n🌟 枢纽节点(连接最多,Top 15):\n")
    print(f"  {'记忆':30s} {'类型':12s} {'连接数'}")
    print(f"  {'-'*30} {'-'*12} {'-'*6}")
    for n, deg in degrees[:15]:
        if deg == 0:
            break
        d = G.nodes[n]
        print(f"  {d['subject'][:30]:30s} {d['memory_type']:12s} {deg}")


def cmd_component(G, args):
    """连通分量。"""
    undirected = G.to_undirected()
    components = sorted(nx.connected_components(undirected), key=len, reverse=True)
    print(f"\n🏝️  连通分量({len(components)} 个):\n")
    for i, comp in enumerate(components[:5], 1):
        print(f"  分量{i}({len(comp)}节点):")
        for n in comp:
            d = G.nodes[n]
            print(f"    [{d['memory_type']:11s}] {d['subject']}")
        print()
    if len(components) > 5:
        print(f"  ... 还有 {len(components) - 5} 个小分量")


def cmd_visualize(G, args):
    """生成 pyvis 交互式可视化。"""
    from pyvis.network import Network

    out_path = ANALYSIS_DIR / "memory_graph.html"
    ensure_dirs([ANALYSIS_DIR])

    net = Network(
        height="900px", width="100%",
        bgcolor="#1a1a2e", font_color="white",
        directed=True,
        # 不用 select_menu/filter_menu——它们引用本地 lib/tom-select 会致空白
        select_menu=False, filter_menu=False,
        # cdn_resources="in_line" 把 vis-network JS 内嵌进 HTML,不依赖网络
        cdn_resources="in_line",
        neighborhood_highlight=True,
    )

    # 添加节点
    undirected = G.to_undirected()
    for n, d in G.nodes(data=True):
        mtype = d.get("memory_type", "?")
        color = TYPE_COLORS.get(mtype, "#999999")
        degree = undirected.degree(n)
        # 节点大小按度数(枢纽更大)
        size = 15 + degree * 4
        title = f"{d.get('description', '')}\n类型: {mtype}\n连接数: {degree}"
        net.add_node(
            n, label=d.get("subject", "?"), title=title,
            color=color, size=size, shape="dot",
        )

    # 添加边
    for u, v, k, ed in G.edges(keys=True, data=True):
        rel = ed.get("relation", "?")
        color = RELATION_COLORS.get(rel, "#666666")
        width = 1 + ed.get("strength", 0.5) * 2
        net.add_edge(u, v, label=rel, color=color, width=width, title=rel)

    # 物理布局(力导向)
    net.set_options(json.dumps({
        "physics": {
            "forceAtlas2Based": {
                "gravitationalConstant": -50,
                "centralGravity": 0.01,
                "springLength": 150,
                "springConstant": 0.05,
            },
            "minVelocity": 0.5,
            "solver": "forceAtlas2Based",
        },
        "interaction": {
            "hover": True,
            "tooltipDelay": 100,
            "navigationButtons": True,
            "keyboard": True,
        },
    }))

    net.write_html(str(out_path), notebook=False)
    print(f"\n🎨 可视化已生成: {out_path}")
    print(f"   节点 {G.number_of_nodes()} / 边 {G.number_of_edges()}")
    print(f"\n   图例(节点颜色):")
    for t, c in TYPE_COLORS.items():
        print(f"     ■ {t} ({c})")
    print(f"\n   打开 HTML 文件即可交互(拖拽/缩放/点击)。")

    # 自动打开浏览器
    try:
        webbrowser.open(out_path.as_uri())
        print(f"   ✓ 已在浏览器打开")
    except Exception:
        print(f"   (请手动打开)")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="记忆图谱查询与可视化")
    parser.add_argument("command", choices=["visualize", "neighbors", "path", "common", "hub", "component"],
                        help="命令")
    parser.add_argument("args", nargs="*", help="命令参数")
    a = parser.parse_args()

    if not UNIFIED_DB.exists():
        print(f"❌ 统合库不存在: {UNIFIED_DB}")
        sys.exit(1)

    con = sqlite3.connect(UNIFIED_DB)
    try:
        G, memories = load_graph(con)
        print(f"图: {G.number_of_nodes()} 节点 / {G.number_of_edges()} 边")
    finally:
        con.close()

    commands = {
        "visualize": cmd_visualize,
        "neighbors": cmd_neighbors,
        "path": cmd_path,
        "common": cmd_common,
        "hub": cmd_hub,
        "component": cmd_component,
    }
    commands[a.command](G, a.args)


if __name__ == "__main__":
    main()
