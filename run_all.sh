#!/usr/bin/env bash
# ============================================================
# run_all.sh — full benchmark pipeline, one command
#
# Usage:
#   cp .env.example .env      # fill in credentials
#   source .env
#   bash run_all.sh
#
# To run only specific databases:
#   bash run_all.sh cognodb falkordb
# ============================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Which databases to benchmark ──────────────────────────────
ALL_DBS=(cognodb memgraph arangodb surrealdb falkordb)

if [ $# -gt 0 ]; then
    DBS=("$@")
else
    DBS=("${ALL_DBS[@]}")
fi

echo "═══════════════════════════════════════════"
echo "  Graph DB Benchmark"
echo "  Databases: ${DBS[*]}"
echo "  $(date)"
echo "═══════════════════════════════════════════"

# ── Step 1: Sample dataset ────────────────────────────────────
echo ""
echo "▶ Step 1: Prepare dataset"
if [ ! -f data/nodes.csv ] || [ ! -f data/edges.csv ]; then
    python data/sample_pokec.py
else
    echo "  data/nodes.csv and data/edges.csv already exist — skipping download"
    echo "  (delete them to re-sample)"
fi

# ── Step 2: Load data into each database ─────────────────────
echo ""
echo "▶ Step 2: Load data"
for db in "${DBS[@]}"; do
    echo ""
    echo "  ── Loading $db ──"
    python loaders/${db}_loader.py
done

# ── Step 3: Traversal workload ────────────────────────────────
echo ""
echo "▶ Step 3: Traversal workload"
for db in "${DBS[@]}"; do
    echo ""
    echo "  ── $db traversal ──"
    python workloads/traversal.py "$db"
done

# ── Step 4: Lookup + aggregation workload ────────────────────
echo ""
echo "▶ Step 4: Lookup workload"
for db in "${DBS[@]}"; do
    echo ""
    echo "  ── $db lookup ──"
    python workloads/lookup.py "$db"
done

# ── Step 5: Mixed workload ────────────────────────────────────
echo ""
echo "▶ Step 5: Mixed concurrent workload (this takes ~8 min per DB)"
for db in "${DBS[@]}"; do
    echo ""
    echo "  ── $db mixed ──"
    python workloads/mixed_workload.py "$db"
done

# ── Step 6: Analyze + generate report and charts ─────────────
echo ""
echo "▶ Step 6: Analyze results"
python analyze.py

echo ""
echo "═══════════════════════════════════════════"
echo "  Done!  See results/report.md and results/charts/"
echo "═══════════════════════════════════════════"
