"""
Load the sampled Pokec dataset into self-hosted Memgraph.

Deployment: Render free instance (512 MB RAM cap, 0.1 CPU burstable),
running Memgraph in ON_DISK_TRANSACTIONAL storage mode to stay within
the 256 MB RAM constraint comparable to CognoDB's free tier.

Start command:
  docker run -p 7687:7687 memgraph/memgraph \
    --storage-mode=ON_DISK_TRANSACTIONAL \
    --memory-limit=256

Env vars:
  MEMGRAPH_HOST      localhost (or Render host)
  MEMGRAPH_PORT      7687
  MEMGRAPH_USER      ""   (no auth on Community)
  MEMGRAPH_PASSWORD  ""

Cypher queries are identical to CognoDB/Neo4j — Memgraph is
fully Bolt+Cypher compatible, so zero translation needed.
"""

import csv
import os
import time
import sys
from dotenv import load_dotenv
from neo4j import GraphDatabase  # Memgraph speaks the Bolt protocol

load_dotenv()

DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
NODES_CSV  = os.path.join(DATA_DIR, "nodes.csv")
EDGES_CSV  = os.path.join(DATA_DIR, "edges.csv")
BATCH_SIZE = 200


def get_driver():
    host = os.environ.get("MEMGRAPH_HOST", "localhost")
    port = os.environ.get("MEMGRAPH_PORT", "7687")
    user = os.environ.get("MEMGRAPH_USER", "")
    pw   = os.environ.get("MEMGRAPH_PASSWORD", "")
    uri  = f"bolt://{host}:{port}"
    if user:
        return GraphDatabase.driver(uri, auth=(user, pw))
    return GraphDatabase.driver(uri, auth=None)


def clear_db(session):
    print("  Clearing existing data ...")
    session.run("MATCH (n) DETACH DELETE n")


def create_index(session):
    print("  Creating index on User.id ...")
    # Memgraph uses CREATE INDEX ON instead of constraints
    session.run("CREATE INDEX ON :User(id)")


def load_nodes(session) -> tuple[int, float]:
    print("  Loading nodes ...")
    rows = []
    with open(NODES_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "id":     row["id:ID"],
                "age":    int(row["age:INT"]) if row["age:INT"] else None,
                "gender": int(row["gender:INT"]) if row["gender:INT"] else None,
            })

    t0 = time.perf_counter()
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        session.run(
            """
            UNWIND $batch AS row
            MERGE (u:User {id: row.id})
            SET u.age = row.age, u.gender = row.gender
            """,
            batch=batch,
        )
        total += len(batch)
        print(f"    {total:,} / {len(rows):,} nodes", end="\r")

    elapsed = time.perf_counter() - t0
    print(f"\n  Loaded {total:,} nodes in {elapsed:.2f}s  ({total/elapsed:,.0f} nodes/s)")
    return total, elapsed


def load_edges(session) -> tuple[int, float]:
    print("  Loading edges ...")
    rows = []
    with open(EDGES_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({"src": row[":START_ID"], "dst": row[":END_ID"]})

    t0 = time.perf_counter()
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        session.run(
            """
            UNWIND $batch AS row
            MATCH (a:User {id: row.src}), (b:User {id: row.dst})
            CREATE (a)-[:FOLLOWS]->(b)
            """,
            batch=batch,
        )
        total += len(batch)
        print(f"    {total:,} / {len(rows):,} edges", end="\r")

    elapsed = time.perf_counter() - t0
    print(f"\n  Loaded {total:,} edges in {elapsed:.2f}s  ({total/elapsed:,.0f} edges/s)")
    return total, elapsed


def main():
    print("=== Memgraph loader ===")
    driver = get_driver()
    with driver.session() as session:
        clear_db(session)
        create_index(session)
        n_nodes, t_nodes = load_nodes(session)
        n_edges, t_edges = load_edges(session)
    driver.close()

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from workloads.utils import save_result
    save_result("memgraph", "ingest", "nodes", {
        "count": n_nodes, "wall_seconds": round(t_nodes, 3),
        "nodes_per_second": round(n_nodes / t_nodes),
        "caveat": "ON_DISK_TRANSACTIONAL mode — slower than default in-memory",
    })
    save_result("memgraph", "ingest", "edges", {
        "count": n_edges, "wall_seconds": round(t_edges, 3),
        "edges_per_second": round(n_edges / t_edges),
    })
    print("Done.")


if __name__ == "__main__":
    main()
