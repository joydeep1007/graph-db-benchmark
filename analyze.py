import json
import os
import glob

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
RAW_DIR     = os.path.join(RESULTS_DIR, "raw")
CHARTS_DIR  = os.path.join(RESULTS_DIR, "charts")
REPORT_PATH = os.path.join(RESULTS_DIR, "report.md")

os.makedirs(CHARTS_DIR, exist_ok=True)

DB_COLORS = {
    "cognodb":  "#6366F1",
    "neo4j":    "#2DD4BF",
    "memgraph": "#F59E0B",
    "arangodb": "#34D399",
    "surrealdb":"#F87171",
}
DB_ORDER = ["cognodb", "neo4j", "memgraph", "arangodb", "surrealdb"]


def load_all() -> dict:
    data = {}
    for path in glob.glob(os.path.join(RAW_DIR, "*.json")):
        db = os.path.splitext(os.path.basename(path))[0]
        with open(path) as f:
            data[db] = json.load(f)
    return data


def safe_get(data, db, *keys, default: object = "N/A"):
    d = data.get(db, {})
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, {})
    return d if d != {} else default


# ─── Chart helpers ─────────────────────────────────────────────────────────────

def bar_chart(title, labels, db_values: dict, ylabel, filename, log_scale=False):
    """db_values = {db_name: [value_per_label]}"""
    dbs = [db for db in DB_ORDER if db in db_values]
    x   = np.arange(len(labels))
    w   = 0.8 / len(dbs)

    fig, ax = plt.subplots(figsize=(10, 5))
    fig.patch.set_facecolor("#0F172A")
    ax.set_facecolor("#1E293B")

    for i, db in enumerate(dbs):
        vals = [v if isinstance(v, (int, float)) else 0 for v in db_values[db]]
        ax.bar(x + i * w, vals, w * 0.9, label=db, color=DB_COLORS.get(db, "#888"),
               alpha=0.9, zorder=3)

    ax.set_xticks(x + w * (len(dbs) - 1) / 2)
    ax.set_xticklabels(labels, color="#CBD5E1", fontsize=10)
    ax.set_ylabel(ylabel, color="#CBD5E1", fontsize=10)
    ax.set_title(title, color="#F1F5F9", fontsize=13, pad=12)
    ax.tick_params(colors="#CBD5E1")
    ax.spines[:].set_color("#334155")
    ax.yaxis.grid(True, color="#334155", zorder=0, linestyle="--", alpha=0.6)
    if log_scale:
        ax.set_yscale("log")
    ax.legend(facecolor="#1E293B", edgecolor="#334155", labelcolor="#CBD5E1",
              loc="upper right", fontsize=9)

    path = os.path.join(CHARTS_DIR, filename)
    plt.tight_layout()
    plt.savefig(path, dpi=150, facecolor=fig.get_facecolor())
    plt.close()
    print(f"  saved {path}")


# ─── Generate charts ──────────────────────────────────────────────────────────

def make_charts(data: dict):
    print("\nGenerating charts ...")

    # 1. Ingest throughput
    bar_chart(
        "Ingest throughput (nodes/s)",
        ["Nodes/s", "Edges/s"],
        {db: [
            safe_get(data, db, "ingest", "nodes", "nodes_per_second", default=0),
            safe_get(data, db, "ingest", "edges", "edges_per_second", default=0),
        ] for db in DB_ORDER if db in data},
        "items/second",
        "ingest_throughput.png",
    )

    # 2. Traversal latency p50
    bar_chart(
        "Traversal p50 latency (ms) — lower is better",
        ["1-hop", "2-hop", "3-hop"],
        {db: [
            safe_get(data, db, "traversal", "1_hop", "p50_ms", default=0),
            safe_get(data, db, "traversal", "2_hop", "p50_ms", default=0),
            safe_get(data, db, "traversal", "3_hop", "p50_ms", default=0),
        ] for db in DB_ORDER if db in data},
        "latency (ms)",
        "traversal_p50.png",
    )

    # 3. Traversal latency p95
    bar_chart(
        "Traversal p95 latency (ms) — lower is better",
        ["1-hop", "2-hop", "3-hop"],
        {db: [
            safe_get(data, db, "traversal", "1_hop", "p95_ms", default=0),
            safe_get(data, db, "traversal", "2_hop", "p95_ms", default=0),
            safe_get(data, db, "traversal", "3_hop", "p95_ms", default=0),
        ] for db in DB_ORDER if db in data},
        "latency (ms)",
        "traversal_p95.png",
    )

    # 4. Lookup latency
    bar_chart(
        "Lookup p50 latency (ms) — lower is better",
        ["Point", "Filtered", "Aggregation"],
        {db: [
            safe_get(data, db, "lookup", "point",       "p50_ms", default=0),
            safe_get(data, db, "lookup", "filtered",    "p50_ms", default=0),
            safe_get(data, db, "lookup", "aggregation", "p50_ms", default=0),
        ] for db in DB_ORDER if db in data},
        "latency (ms)",
        "lookup_p50.png",
    )

    # 5. Mixed workload QPS
    bar_chart(
        "Mixed workload throughput (QPS) — higher is better",
        ["c=1", "c=10", "c=20", "c=40"],
        {db: [
            safe_get(data, db, "mixed", "c1",  "qps", default=0),
            safe_get(data, db, "mixed", "c10", "qps", default=0),
            safe_get(data, db, "mixed", "c20", "qps", default=0),
            safe_get(data, db, "mixed", "c40", "qps", default=0),
        ] for db in DB_ORDER if db in data},
        "queries/second",
        "mixed_qps.png",
    )


# ─── Generate report.md ───────────────────────────────────────────────────────

def row(cells): return "| " + " | ".join(str(c) for c in cells) + " |"
def sep(n):     return "| " + " | ".join(["---"] * n) + " |"
def val(v, suffix=""): return f"{v}{suffix}" if v not in (None, "N/A", 0) else "—"


def make_report(data: dict):
    dbs = [db for db in DB_ORDER if db in data]
    lines = []

    lines += [
        "# Graph Database Benchmark — Results",
        "",
        "> Auto-generated by `analyze.py`. See README.md for methodology and caveats.",
        "",
    ]

    # Ingest
    lines += ["## Ingest throughput", ""]
    lines += [row(["Database", "Nodes", "Nodes/s", "Edges", "Edges/s", "Total wall-clock (s)"])]
    lines += [sep(6)]
    for db in dbs:
        nd = data[db].get("ingest", {}).get("nodes", {})
        ed = data[db].get("ingest", {}).get("edges", {})
        total_s = (nd.get("wall_seconds",0) or 0) + (ed.get("wall_seconds",0) or 0)
        lines += [row([
            db,
            val(nd.get("count")),
            val(nd.get("nodes_per_second")),
            val(ed.get("count")),
            val(ed.get("edges_per_second")),
            val(round(total_s, 1), "s"),
        ])]
    lines.append("")

    # Traversal
    lines += ["## Traversal latency", ""]
    lines += [row(["Database", "1-hop p50", "1-hop p95", "2-hop p50", "2-hop p95", "3-hop p50", "3-hop p95"])]
    lines += [sep(7)]
    for db in dbs:
        t = data[db].get("traversal", {})
        lines += [row([
            db,
            val(t.get("1_hop",{}).get("p50_ms"), "ms"),
            val(t.get("1_hop",{}).get("p95_ms"), "ms"),
            val(t.get("2_hop",{}).get("p50_ms"), "ms"),
            val(t.get("2_hop",{}).get("p95_ms"), "ms"),
            val(t.get("3_hop",{}).get("p50_ms"), "ms"),
            val(t.get("3_hop",{}).get("p95_ms"), "ms"),
        ])]
    lines.append("")

    # Lookup
    lines += ["## Lookup & aggregation latency", ""]
    lines += [row(["Database", "Point p50", "Point p95", "Filtered p50", "Filtered p95", "Aggr p50", "Aggr p95"])]
    lines += [sep(7)]
    for db in dbs:
        lk = data[db].get("lookup", {})
        lines += [row([
            db,
            val(lk.get("point",{}).get("p50_ms"), "ms"),
            val(lk.get("point",{}).get("p95_ms"), "ms"),
            val(lk.get("filtered",{}).get("p50_ms"), "ms"),
            val(lk.get("filtered",{}).get("p95_ms"), "ms"),
            val(lk.get("aggregation",{}).get("p50_ms"), "ms"),
            val(lk.get("aggregation",{}).get("p95_ms"), "ms"),
        ])]
    lines.append("")

    # Mixed workload
    lines += ["## Mixed workload (80% read / 20% write)", ""]
    lines += [row(["Database", "c=1 QPS", "c=10 QPS", "c=20 QPS", "c=40 QPS", "c=40 errors"])]
    lines += [sep(6)]
    for db in dbs:
        mx = data[db].get("mixed", {})
        lines += [row([
            db,
            val(mx.get("c1",{}).get("qps")),
            val(mx.get("c10",{}).get("qps")),
            val(mx.get("c20",{}).get("qps")),
            val(mx.get("c40",{}).get("qps")),
            val(mx.get("c40",{}).get("errors")),
        ])]
    lines.append("")

    lines += [
        "## Charts",
        "",
        "![Ingest throughput](charts/ingest_throughput.png)",
        "![Traversal p50](charts/traversal_p50.png)",
        "![Traversal p95](charts/traversal_p95.png)",
        "![Lookup p50](charts/lookup_p50.png)",
        "![Mixed QPS](charts/mixed_qps.png)",
        "",
    ]

    with open(REPORT_PATH, "w") as f:
        f.write("\n".join(lines))
    print(f"  saved {REPORT_PATH}")


if __name__ == "__main__":
    print("=== analyze.py ===")
    data = load_all()
    if not data:
        print("No result files found in results/raw/ — run workloads first.")
    else:
        print(f"Loaded results for: {', '.join(data.keys())}")
        make_charts(data)
        make_report(data)
        print("Done.")
