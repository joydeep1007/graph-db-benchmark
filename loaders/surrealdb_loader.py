"""
Load the sampled Pokec dataset into self-hosted SurrealDB.

Deployment: Render free instance (256 MB RAM native minimum):
  docker run -p 8000:8000 surrealdb/surrealdb:latest start \
    --log info \
    --user root \
    --pass $SURREALDB_PASSWORD \
    file:/data/pokec.db

Env vars:
  SURREALDB_URL       ws://localhost:8000/rpc
  SURREALDB_USER      root
  SURREALDB_PASSWORD  <password>
  SURREALDB_NS        bench
  SURREALDB_DB        pokec

Query language note:
  SurrealDB uses SurrealQL (SQL-like with graph extensions).
  Equivalent queries are documented in workloads/traversal.py.
  Graph traversal in SurrealQL uses -> and <- operators.
"""

import asyncio
import csv
import os
import sys
import time
from dotenv import load_dotenv
from surrealdb import Surreal

load_dotenv()

DATA_DIR  = os.path.join(os.path.dirname(__file__), "..", "data")
NODES_CSV = os.path.join(DATA_DIR, "nodes.csv")
EDGES_CSV = os.path.join(DATA_DIR, "edges.csv")
BATCH_SIZE = 200  # SurrealDB WS messages are size-sensitive; keep batches smaller


async def load(url, user, pw, ns, db_name):
    db = Surreal(url)
    await db.connect()
    await db.signin({"user": user, "pass": pw})
    await db.use(ns, db_name)

    # Clear
    print("  Clearing existing data ...")
    await db.query("DELETE user; DELETE follows;")

    # Index
    print("  Creating index ...")
    await db.query("DEFINE INDEX user_id_idx ON TABLE user COLUMNS user_id UNIQUE")

    # Load nodes
    print("  Loading nodes ...")
    rows = []
    with open(NODES_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            r = {"user_id": row["id:ID"]}
            if row["age:INT"]:
                r["age"] = int(row["age:INT"])
            if row["gender:INT"]:
                r["gender"] = int(row["gender:INT"])
            rows.append(r)

    t0 = time.perf_counter()
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        # SurrealQL INSERT with array of objects
        await db.query(
            "INSERT INTO user $batch",
            {"batch": batch},
        )
        total += len(batch)
        print(f"    {total:,} / {len(rows):,} nodes", end="\r")
    t_nodes = time.perf_counter() - t0
    print(f"\n  Loaded {total:,} nodes in {t_nodes:.2f}s  ({total/t_nodes:,.0f} nodes/s)")
    n_nodes = total

    # Load edges
    # In SurrealDB, graph edges are RELATE statements
    print("  Loading edges ...")
    edge_rows = []
    with open(EDGES_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            edge_rows.append((row[":START_ID"], row[":END_ID"]))

    t0 = time.perf_counter()
    total = 0
    for i in range(0, len(edge_rows), BATCH_SIZE):
        batch = edge_rows[i : i + BATCH_SIZE]
        # Build batch RELATE via SurrealQL
        # RELATE user:<src> -> follows -> user:<dst>
        stmts = " ".join(
            f"RELATE user:`{src}`->follows->user:`{dst}`;"
            for src, dst in batch
        )
        await db.query(stmts)
        total += len(batch)
        print(f"    {total:,} / {len(edge_rows):,} edges", end="\r")
    t_edges = time.perf_counter() - t0
    print(f"\n  Loaded {total:,} edges in {t_edges:.2f}s  ({total/t_edges:,.0f} edges/s)")
    n_edges = total

    await db.close()
    return n_nodes, t_nodes, n_edges, t_edges


def main():
    print("=== SurrealDB loader ===")
    url  = os.environ.get("SURREALDB_URL", "ws://localhost:8000/rpc")
    user = os.environ.get("SURREALDB_USER", "root")
    pw   = os.environ["SURREALDB_PASSWORD"]
    ns   = os.environ.get("SURREALDB_NS",   "bench")
    db   = os.environ.get("SURREALDB_DB",   "pokec")

    n_nodes, t_nodes, n_edges, t_edges = asyncio.run(load(url, user, pw, ns, db))

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from workloads.utils import save_result
    save_result("surrealdb", "ingest", "nodes", {
        "count": n_nodes, "wall_seconds": round(t_nodes, 3),
        "nodes_per_second": round(n_nodes / t_nodes),
    })
    save_result("surrealdb", "ingest", "edges", {
        "count": n_edges, "wall_seconds": round(t_edges, 3),
        "edges_per_second": round(n_edges / t_edges),
        "caveat": "RELATE batching via concatenated statements; larger batches may timeout",
    })
    print("Done.")


if __name__ == "__main__":
    main()
