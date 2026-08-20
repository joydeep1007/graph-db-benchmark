"""
Traversal benchmark: 1-hop, 2-hop, 3-hop neighbour queries.

For each database:
  - Pick 50 random start nodes from the dataset
  - Run each hop depth 100 times (across the 50 nodes, rotated)
  - Report p50 and p95 latency in ms

Equivalent logical query: "Find all nodes reachable in N hops from node X"

Cypher  (CognoDB / Memgraph):
  MATCH (u:User {id: $id})-[:FOLLOWS*1]->(v) RETURN count(v)   -- 1-hop
  MATCH (u:User {id: $id})-[:FOLLOWS*2]->(v) RETURN count(v)   -- 2-hop
  MATCH (u:User {id: $id})-[:FOLLOWS*3]->(v) RETURN count(v)   -- 3-hop

AQL (ArangoDB):
  FOR v IN 1..1 OUTBOUND CONCAT('users/', @id) FOLLOWS RETURN COUNT(v)
  FOR v IN 2..2 OUTBOUND CONCAT('users/', @id) FOLLOWS RETURN COUNT(v)
  FOR v IN 3..3 OUTBOUND CONCAT('users/', @id) FOLLOWS RETURN COUNT(v)

SurrealQL (SurrealDB):
  SELECT ->follows->user AS hop1 FROM user:<id>
  SELECT ->follows->user->follows->user AS hop2 FROM user:<id>
  (3-hop analogously)
"""

import os
import random
import sys
import csv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from workloads.utils import time_query, summarise, save_result

DATA_DIR  = os.path.join(os.path.dirname(__file__), "..", "data")
NODES_CSV = os.path.join(DATA_DIR, "nodes.csv")

ITERATIONS  = 100
SAMPLE_SIZE = 50   # random start nodes


def load_sample_ids() -> list[str]:
    ids = []
    with open(NODES_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ids.append(row["id:ID"])
    sample = random.sample(ids, min(SAMPLE_SIZE, len(ids)))
    print(f"  Using {len(sample)} random start nodes")
    return sample


# ─── CognoDB / Memgraph (Cypher) ─────────────────────────────────────

def bench_cypher(driver, db_name: str, sample_ids: list[str]) -> None:
    print(f"\n  {db_name} traversal benchmark")

    def make_hop_fn(session, hop: int, node_id: str):
        query = (
            f"MATCH (u:User {{id: $id}})-[:FOLLOWS*{hop}]->(v) RETURN count(v) AS c"
        )
        return lambda: session.run(query, id=node_id).single()

    with driver.session() as session:
        for hop in (1, 2, 3):
            latencies = []
            for i in range(ITERATIONS):
                nid = sample_ids[i % len(sample_ids)]
                fn  = make_hop_fn(session, hop, nid)
                lat = time_query(fn, iterations=1)
                latencies.extend(lat)
            result = summarise(latencies)
            save_result(db_name, "traversal", f"{hop}_hop", result)
            print(f"    {hop}-hop → p50={result['p50_ms']}ms  p95={result['p95_ms']}ms")


# ─── FalkorDB (Cypher) ────────────────────────────────────────────────────────

def bench_falkordb(graph, db_name: str, sample_ids: list[str]) -> None:
    print(f"\n  {db_name} traversal benchmark")

    def make_hop_fn(hop: int, node_id: str):
        query = (
            f"MATCH (u:User {{id: $id}})-[:FOLLOWS*{hop}]->(v) RETURN count(v) AS c"
        )
        return lambda: graph.query(query, params={"id": node_id})

    for hop in (1, 2, 3):
        latencies = []
        for i in range(ITERATIONS):
            nid = sample_ids[i % len(sample_ids)]
            fn  = make_hop_fn(hop, nid)
            lat = time_query(fn, iterations=1)
            latencies.extend(lat)
        result = summarise(latencies)
        save_result(db_name, "traversal", f"{hop}_hop", result)
        print(f"    {hop}-hop → p50={result['p50_ms']}ms  p95={result['p95_ms']}ms")


# ─── ArangoDB (AQL) ──────────────────────────────────────────────────────────

def bench_arango(db, sample_ids: list[str]) -> None:
    print("\n  ArangoDB traversal benchmark")
    for hop in (1, 2, 3):
        latencies = []
        for i in range(ITERATIONS):
            nid = sample_ids[i % len(sample_ids)]

            def run_aql(nid=nid, hop=hop):
                cursor = db.aql.execute(
                    f"""
                    FOR v IN {hop}..{hop} OUTBOUND @start follows
                    COLLECT WITH COUNT INTO c
                    RETURN c
                    """,
                    bind_vars={"start": f"users/{nid}"},
                )
                return list(cursor)

            lat = time_query(run_aql, iterations=1)
            latencies.extend(lat)

        result = summarise(latencies)
        save_result("arangodb", "traversal", f"{hop}_hop", result)
        print(f"    {hop}-hop → p50={result['p50_ms']}ms  p95={result['p95_ms']}ms")


# ─── SurrealDB (SurrealQL) ────────────────────────────────────────────────────

def bench_surreal(db_conn, sample_ids: list[str]) -> None:
    """db_conn is a synchronous wrapper returned by get_surreal_sync()."""
    import asyncio
    print("\n  SurrealDB traversal benchmark")

    async def run_hop(db, nid, hop):
        # Build nested arrow chain: ->follows->user repeated `hop` times
        chain = "->follows->user" * hop
        q = f"SELECT {chain} FROM user:`{nid}`"
        return await db.query(q)

    from surrealdb import Surreal

    async def bench():
        url  = os.environ.get("SURREALDB_URL", "ws://localhost:8000/rpc")
        user = os.environ.get("SURREALDB_USER", "root")
        pw   = os.environ["SURREALDB_PASSWORD"]
        ns   = os.environ.get("SURREALDB_NS",   "bench")
        dbn  = os.environ.get("SURREALDB_DB",   "pokec")

        db = Surreal(url)
        await db.connect()
        await db.signin({"user": user, "pass": pw})
        await db.use(ns, dbn)

        for hop in (1, 2, 3):
            latencies = []
            for i in range(ITERATIONS):
                nid = sample_ids[i % len(sample_ids)]
                import time
                t0 = time.perf_counter()
                await run_hop(db, nid, hop)
                latencies.append((time.perf_counter() - t0) * 1000)

            result = summarise(latencies)
            save_result("surrealdb", "traversal", f"{hop}_hop", result)
            print(f"    {hop}-hop → p50={result['p50_ms']}ms  p95={result['p95_ms']}ms")

        await db.close()

    asyncio.run(bench())


# ─── Entry points ─────────────────────────────────────────────────────────────

def run_cognodb():
    from neo4j import GraphDatabase
    uri  = os.environ["COGNODB_URI"]
    user = os.environ.get("COGNODB_USER", "cognodb")
    pw   = os.environ["COGNODB_PASSWORD"]
    driver = GraphDatabase.driver(uri, auth=(user, pw))
    sample = load_sample_ids()
    bench_cypher(driver, "cognodb", sample)
    driver.close()


def run_memgraph():
    from neo4j import GraphDatabase
    host = os.environ.get("MEMGRAPH_HOST", "localhost")
    port = os.environ.get("MEMGRAPH_PORT", "7687")
    user = os.environ.get("MEMGRAPH_USER", "")
    pw   = os.environ.get("MEMGRAPH_PASSWORD", "")
    uri  = f"bolt://{host}:{port}"
    auth = (user, pw) if user else None
    driver = GraphDatabase.driver(uri, auth=auth)
    sample = load_sample_ids()
    bench_cypher(driver, "memgraph", sample)
    driver.close()


def run_arangodb():
    from arango.client import ArangoClient
    host = os.environ.get("ARANGODB_HOST", "localhost")
    port = os.environ.get("ARANGODB_PORT", "8529")
    user = os.environ.get("ARANGODB_USER", "root")
    pw   = os.environ["ARANGODB_PASSWORD"]
    client = ArangoClient(hosts=f"http://{host}:{port}")
    db = client.db("pokec_bench", username=user, password=pw)
    sample = load_sample_ids()
    bench_arango(db, sample)


def run_surrealdb():
    sample = load_sample_ids()
    bench_surreal(None, sample)


def run_falkordb():
    from falkordb import FalkorDB
    host = os.environ.get("FALKORDB_HOST", "localhost")
    port = int(os.environ.get("FALKORDB_PORT", 6379))
    pw   = os.environ.get("FALKORDB_PASSWORD", "")
    kwargs = {"host": host, "port": port}
    if pw:
        kwargs["password"] = pw
    db = FalkorDB(**kwargs)
    graph = db.select_graph("pokec")
    sample = load_sample_ids()
    bench_falkordb(graph, "falkordb", sample)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("db", choices=["cognodb", "memgraph", "arangodb", "surrealdb", "falkordb"])
    args = parser.parse_args()
    {"cognodb": run_cognodb, "memgraph": run_memgraph,
     "arangodb": run_arangodb, "surrealdb": run_surrealdb,
     "falkordb": run_falkordb}[args.db]()
