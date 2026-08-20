"""
Load the sampled Pokec dataset into Neo4j AuraDB Free.

Env vars:
  NEO4J_URI       neo4j+s://<instance>.databases.neo4j.io
  NEO4J_USER      neo4j
  NEO4J_PASSWORD  <aura password>

Logic is identical to cognodb_loader.py — same driver, same Cypher.
This ensures query-language parity for the benchmark.
"""

import csv
import os
import time
import sys

from neo4j import GraphDatabase

DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
NODES_CSV  = os.path.join(DATA_DIR, "nodes.csv")
EDGES_CSV  = os.path.join(DATA_DIR, "edges.csv")
BATCH_SIZE = 500


def get_driver():
    uri  = os.environ["NEO4J_URI"]
    user = os.environ.get("NEO4J_USER", "neo4j")
    pw   = os.environ["NEO4J_PASSWORD"]
    return GraphDatabase.driver(uri, auth=(user, pw))


def clear_db(session):
    print("  Clearing existing data ...")
    session.run("MATCH (n) DETACH DELETE n")


def create_constraints(session):
    print("  Creating constraints ...")
    session.run("CREATE CONSTRAINT IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE")


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
            MERGE (a)-[:FOLLOWS]->(b)
            """,
            batch=batch,
        )
        total += len(batch)
        print(f"    {total:,} / {len(rows):,} edges", end="\r")

    elapsed = time.perf_counter() - t0
    print(f"\n  Loaded {total:,} edges in {elapsed:.2f}s  ({total/elapsed:,.0f} edges/s)")
    return total, elapsed


def main():
    print("=== Neo4j AuraDB loader ===")
    driver = get_driver()
    with driver.session() as session:
        clear_db(session)
        create_constraints(session)
        n_nodes, t_nodes = load_nodes(session)
        n_edges, t_edges = load_edges(session)
    driver.close()

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from workloads.utils import save_result
    save_result("neo4j", "ingest", "nodes", {
        "count": n_nodes, "wall_seconds": round(t_nodes, 3),
        "nodes_per_second": round(n_nodes / t_nodes),
    })
    save_result("neo4j", "ingest", "edges", {
        "count": n_edges, "wall_seconds": round(t_edges, 3),
        "edges_per_second": round(n_edges / t_edges),
    })
    print("Done.")


if __name__ == "__main__":
    main()
