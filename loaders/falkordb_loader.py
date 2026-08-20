import csv
import os
import time
import sys
from dotenv import load_dotenv
from falkordb import FalkorDB

load_dotenv()

DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
NODES_CSV  = os.path.join(DATA_DIR, "nodes.csv")
EDGES_CSV  = os.path.join(DATA_DIR, "edges.csv")
BATCH_SIZE = 500


def get_graph():
    host = os.environ.get("FALKORDB_HOST", "localhost")
    port = int(os.environ.get("FALKORDB_PORT", 6379))
    pw   = os.environ.get("FALKORDB_PASSWORD", "")
    
    kwargs = {"host": host, "port": port}
    if pw:
        kwargs["password"] = pw
        
    db = FalkorDB(**kwargs)
    return db.select_graph("pokec")


def clear_db(graph):
    print("  Clearing existing data ...")
    graph.query("MATCH (n) DETACH DELETE n")


def create_index(graph):
    print("  Creating index on User.id ...")
    graph.query("CREATE INDEX FOR (u:User) ON (u.id)")


def load_nodes(graph) -> tuple[int, float]:
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
        graph.query(
            """
            UNWIND $batch AS row
            MERGE (u:User {id: row.id})
            SET u.age = row.age, u.gender = row.gender
            """,
            params={"batch": batch},
        )
        total += len(batch)
        print(f"    {total:,} / {len(rows):,} nodes", end="\r")

    elapsed = time.perf_counter() - t0
    print(f"\n  Loaded {total:,} nodes in {elapsed:.2f}s  ({total/elapsed:,.0f} nodes/s)")
    return total, elapsed


def load_edges(graph) -> tuple[int, float]:
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
        graph.query(
            """
            UNWIND $batch AS row
            MATCH (a:User {id: row.src}), (b:User {id: row.dst})
            MERGE (a)-[:FOLLOWS]->(b)
            """,
            params={"batch": batch},
        )
        total += len(batch)
        print(f"    {total:,} / {len(rows):,} edges", end="\r")

    elapsed = time.perf_counter() - t0
    print(f"\n  Loaded {total:,} edges in {elapsed:.2f}s  ({total/elapsed:,.0f} edges/s)")
    return total, elapsed


def main():
    print("=== FalkorDB loader ===")
    graph = get_graph()
    
    clear_db(graph)
    create_index(graph)
    n_nodes, t_nodes = load_nodes(graph)
    n_edges, t_edges = load_edges(graph)

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from workloads.utils import save_result
    
    save_result("falkordb", "ingest", "nodes", {
        "count": n_nodes, "wall_seconds": round(t_nodes, 3),
        "nodes_per_second": round(n_nodes / t_nodes),
    })
    save_result("falkordb", "ingest", "edges", {
        "count": n_edges, "wall_seconds": round(t_edges, 3),
        "edges_per_second": round(n_edges / t_edges),
    })
    print("Done.")


if __name__ == "__main__":
    main()
