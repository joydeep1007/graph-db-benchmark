import csv
import os
import time
import sys
from dotenv import load_dotenv
from arango.client import ArangoClient

load_dotenv()

DATA_DIR   = os.path.join(os.path.dirname(__file__), "..", "data")
NODES_CSV  = os.path.join(DATA_DIR, "nodes.csv")
EDGES_CSV  = os.path.join(DATA_DIR, "edges.csv")
BATCH_SIZE = 500

DB_NAME     = "pokec_bench"
VERTEX_COLL = "users"
EDGE_COLL   = "follows"
GRAPH_NAME  = "social"


def get_db():
    host = os.environ.get("ARANGODB_HOST", "localhost")
    port = os.environ.get("ARANGODB_PORT", "8529")
    user = os.environ.get("ARANGODB_USER", "root")
    pw   = os.environ["ARANGODB_PASSWORD"]
    client = ArangoClient(hosts=f"http://{host}:{port}")
    sys_db = client.db("_system", username=user, password=pw)

    if not sys_db.has_database(DB_NAME):
        sys_db.create_database(DB_NAME)
    return client.db(DB_NAME, username=user, password=pw)


def setup_collections(db):
    print("  Setting up collections and graph ...")
    if db.has_collection(VERTEX_COLL):
        db.collection(VERTEX_COLL).truncate()
    else:
        db.create_collection(VERTEX_COLL)

    if db.has_collection(EDGE_COLL):
        db.collection(EDGE_COLL).truncate()
    else:
        db.create_collection(EDGE_COLL, edge=True)

    if db.has_graph(GRAPH_NAME):
        db.delete_graph(GRAPH_NAME)
    db.create_graph(
        GRAPH_NAME,
        edge_definitions=[{
            "edge_collection":    EDGE_COLL,
            "from_vertex_collections": [VERTEX_COLL],
            "to_vertex_collections":   [VERTEX_COLL],
        }],
    )

    # Index on id field (ArangoDB uses _key internally, but we keep
    # a `user_id` property for cross-platform parity)
    col = db.collection(VERTEX_COLL)
    col.add_persistent_index(fields=["user_id"], unique=True)


def load_nodes(db) -> tuple[int, float]:
    print("  Loading nodes ...")
    col = db.collection(VERTEX_COLL)
    rows = []
    with open(NODES_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            doc = {
                "_key":    row["id:ID"],   # ArangoDB _key must be a string
                "user_id": row["id:ID"],
            }
            if row["age:INT"]:
                doc["age"] = int(row["age:INT"])
            if row["gender:INT"]:
                doc["gender"] = int(row["gender:INT"])
            rows.append(doc)

    t0 = time.perf_counter()
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        col.import_bulk(rows[i : i + BATCH_SIZE], on_duplicate="replace")
        total += min(BATCH_SIZE, len(rows) - i)
        print(f"    {total:,} / {len(rows):,} nodes", end="\r")

    elapsed = time.perf_counter() - t0
    print(f"\n  Loaded {total:,} nodes in {elapsed:.2f}s  ({total/elapsed:,.0f} nodes/s)")
    return total, elapsed


def load_edges(db) -> tuple[int, float]:
    print("  Loading edges ...")
    col = db.collection(EDGE_COLL)
    rows = []
    with open(EDGES_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "_from": f"{VERTEX_COLL}/{row[':START_ID']}",
                "_to":   f"{VERTEX_COLL}/{row[':END_ID']}",
            })

    t0 = time.perf_counter()
    total = 0
    for i in range(0, len(rows), BATCH_SIZE):
        col.import_bulk(rows[i : i + BATCH_SIZE], on_duplicate="ignore")
        total += min(BATCH_SIZE, len(rows) - i)
        print(f"    {total:,} / {len(rows):,} edges", end="\r")

    elapsed = time.perf_counter() - t0
    print(f"\n  Loaded {total:,} edges in {elapsed:.2f}s  ({total/elapsed:,.0f} edges/s)")
    return total, elapsed


def main():
    print("=== ArangoDB loader ===")
    db = get_db()
    setup_collections(db)
    n_nodes, t_nodes = load_nodes(db)
    n_edges, t_edges = load_edges(db)

    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from workloads.utils import save_result
    save_result("arangodb", "ingest", "nodes", {
        "count": n_nodes, "wall_seconds": round(t_nodes, 3),
        "nodes_per_second": round(n_nodes / t_nodes),
    })
    save_result("arangodb", "ingest", "edges", {
        "count": n_edges, "wall_seconds": round(t_edges, 3),
        "edges_per_second": round(n_edges / t_edges),
        "caveat": "import_bulk used; AQL UPSERT would be ~3x slower",
    })
    print("Done.")


if __name__ == "__main__":
    main()
