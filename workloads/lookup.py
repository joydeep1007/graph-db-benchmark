"""
Lookup benchmark: point lookup and filtered/aggregation queries.

Queries:
  Point lookup    — fetch one node by indexed id
  Filtered lookup — fetch all nodes where gender=1 (indexed scan)
  Aggregation     — count nodes grouped by gender

Cypher (CognoDB / Memgraph/ FalkorDB):
  MATCH (u:User {id: $id}) RETURN u                          -- point
  MATCH (u:User {gender: 1}) RETURN count(u)                 -- filtered
  MATCH (u:User) RETURN u.gender, count(u) ORDER BY u.gender -- aggregation

AQL (ArangoDB):
  FOR u IN users FILTER u.user_id == @id RETURN u           -- point
  FOR u IN users FILTER u.gender == 1
    COLLECT WITH COUNT INTO c RETURN c                        -- filtered
  FOR u IN users COLLECT g = u.gender WITH COUNT INTO c
    RETURN {gender: g, count: c}                              -- aggregation

SurrealQL (SurrealDB):
  SELECT * FROM user WHERE user_id = $id                     -- point
  SELECT count() FROM user WHERE gender = 1 GROUP ALL        -- filtered
  SELECT gender, count() FROM user GROUP BY gender           -- aggregation
"""

import csv
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from workloads.utils import time_query, summarise, save_result

DATA_DIR  = os.path.join(os.path.dirname(__file__), "..", "data")
NODES_CSV = os.path.join(DATA_DIR, "nodes.csv")
ITERATIONS = 100


def load_sample_ids(n=50) -> list[str]:
    ids = []
    with open(NODES_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ids.append(row["id:ID"])
    return random.sample(ids, min(n, len(ids)))


# ─── Cypher (CognoDB / Memgraph) ─────────────────────────────────────

def bench_cypher(driver, db_name: str, sample_ids: list[str]) -> None:
    print(f"\n  {db_name} lookup benchmark")
    with driver.session() as session:

        # Point lookup
        lats = []
        for i in range(ITERATIONS):
            nid = sample_ids[i % len(sample_ids)]
            fn  = lambda nid=nid: session.run("MATCH (u:User {id:$id}) RETURN u", id=nid).single()
            lats.extend(time_query(fn, 1))
        r = summarise(lats)
        save_result(db_name, "lookup", "point", r)
        print(f"    point   → p50={r['p50_ms']}ms  p95={r['p95_ms']}ms")

        # Filtered lookup
        lats = []
        fn = lambda: session.run("MATCH (u:User {gender:1}) RETURN count(u) AS c").single()
        lats = time_query(fn, ITERATIONS)
        r = summarise(lats)
        save_result(db_name, "lookup", "filtered", r)
        print(f"    filtered→ p50={r['p50_ms']}ms  p95={r['p95_ms']}ms")

        # Aggregation
        fn = lambda: session.run(
            "MATCH (u:User) RETURN u.gender AS g, count(u) AS c ORDER BY g"
        ).data()
        lats = time_query(fn, ITERATIONS)
        r = summarise(lats)
        save_result(db_name, "lookup", "aggregation", r)
        print(f"    aggr    → p50={r['p50_ms']}ms  p95={r['p95_ms']}ms")


# ─── FalkorDB (Cypher) ────────────────────────────────────────────────────────

def bench_falkordb(graph, db_name: str, sample_ids: list[str]) -> None:
    print(f"\n  {db_name} lookup benchmark")

    # Point lookup
    lats = []
    for i in range(ITERATIONS):
        nid = sample_ids[i % len(sample_ids)]
        fn  = lambda nid=nid: graph.query("MATCH (u:User {id:$id}) RETURN u", params={"id": nid})
        lats.extend(time_query(fn, 1))
    r = summarise(lats)
    save_result(db_name, "lookup", "point", r)
    print(f"    point   → p50={r['p50_ms']}ms  p95={r['p95_ms']}ms")

    # Filtered lookup
    fn = lambda: graph.query("MATCH (u:User {gender:1}) RETURN count(u) AS c")
    lats = time_query(fn, ITERATIONS)
    r = summarise(lats)
    save_result(db_name, "lookup", "filtered", r)
    print(f"    filtered→ p50={r['p50_ms']}ms  p95={r['p95_ms']}ms")

    # Aggregation
    fn = lambda: graph.query(
        "MATCH (u:User) RETURN u.gender AS g, count(u) AS c ORDER BY g"
    )
    lats = time_query(fn, ITERATIONS)
    r = summarise(lats)
    save_result(db_name, "lookup", "aggregation", r)
    print(f"    aggr    → p50={r['p50_ms']}ms  p95={r['p95_ms']}ms")


# ─── ArangoDB (AQL) ──────────────────────────────────────────────────────────

def bench_arango(db, sample_ids: list[str]) -> None:
    print("\n  ArangoDB lookup benchmark")

    # Point lookup
    lats = []
    for i in range(ITERATIONS):
        nid = sample_ids[i % len(sample_ids)]
        fn  = lambda nid=nid: list(db.aql.execute(
            "FOR u IN users FILTER u.user_id == @id RETURN u", bind_vars={"id": nid}
        ))
        lats.extend(time_query(fn, 1))
    r = summarise(lats)
    save_result("arangodb", "lookup", "point", r)
    print(f"    point   → p50={r['p50_ms']}ms  p95={r['p95_ms']}ms")

    # Filtered
    fn = lambda: list(db.aql.execute(
        "FOR u IN users FILTER u.gender == 1 COLLECT WITH COUNT INTO c RETURN c"
    ))
    lats = time_query(fn, ITERATIONS)
    r = summarise(lats)
    save_result("arangodb", "lookup", "filtered", r)
    print(f"    filtered→ p50={r['p50_ms']}ms  p95={r['p95_ms']}ms")

    # Aggregation
    fn = lambda: list(db.aql.execute(
        "FOR u IN users COLLECT g = u.gender WITH COUNT INTO c RETURN {gender:g, count:c}"
    ))
    lats = time_query(fn, ITERATIONS)
    r = summarise(lats)
    save_result("arangodb", "lookup", "aggregation", r)
    print(f"    aggr    → p50={r['p50_ms']}ms  p95={r['p95_ms']}ms")


# ─── SurrealDB (async) ────────────────────────────────────────────────────────

def bench_surrealdb(sample_ids: list[str]) -> None:
    import asyncio, time
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

        # Point lookup
        lats = []
        for i in range(ITERATIONS):
            nid = sample_ids[i % len(sample_ids)]
            t0 = time.perf_counter()
            await db.query(f"SELECT * FROM user:`{nid}`")
            lats.append((time.perf_counter() - t0) * 1000)
        r = summarise(lats)
        save_result("surrealdb", "lookup", "point", r)
        print(f"    point   → p50={r['p50_ms']}ms  p95={r['p95_ms']}ms")

        # Filtered
        lats = []
        for _ in range(ITERATIONS):
            t0 = time.perf_counter()
            await db.query("SELECT count() FROM user WHERE gender = 1 GROUP ALL")
            lats.append((time.perf_counter() - t0) * 1000)
        r = summarise(lats)
        save_result("surrealdb", "lookup", "filtered", r)
        print(f"    filtered→ p50={r['p50_ms']}ms  p95={r['p95_ms']}ms")

        # Aggregation
        lats = []
        for _ in range(ITERATIONS):
            t0 = time.perf_counter()
            await db.query("SELECT gender, count() FROM user GROUP BY gender")
            lats.append((time.perf_counter() - t0) * 1000)
        r = summarise(lats)
        save_result("surrealdb", "lookup", "aggregation", r)
        print(f"    aggr    → p50={r['p50_ms']}ms  p95={r['p95_ms']}ms")

        await db.close()

    print("\n  SurrealDB lookup benchmark")
    asyncio.run(bench())


# ─── Entry points ─────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()
def run_cognodb():
    from neo4j import GraphDatabase
    driver = GraphDatabase.driver(os.environ["COGNODB_URI"],
                                  auth=(os.environ.get("COGNODB_USER","cognodb"),
                                        os.environ["COGNODB_PASSWORD"]))
    bench_cypher(driver, "cognodb", load_sample_ids())
    driver.close()



def run_memgraph():
    from neo4j import GraphDatabase
    host = os.environ.get("MEMGRAPH_HOST","localhost")
    port = os.environ.get("MEMGRAPH_PORT","7687")
    user = os.environ.get("MEMGRAPH_USER","")
    pw   = os.environ.get("MEMGRAPH_PASSWORD","")
    auth = (user, pw) if user else None
    driver = GraphDatabase.driver(f"bolt://{host}:{port}", auth=auth)
    bench_cypher(driver, "memgraph", load_sample_ids())
    driver.close()


def run_arangodb():
    from arango.client import ArangoClient
    host = os.environ.get("ARANGODB_HOST","localhost")
    port = os.environ.get("ARANGODB_PORT","8529")
    user = os.environ.get("ARANGODB_USER","root")
    pw   = os.environ["ARANGODB_PASSWORD"]
    client = ArangoClient(hosts=f"http://{host}:{port}")
    db = client.db("pokec_bench", username=user, password=pw)
    bench_arango(db, load_sample_ids())


def run_surrealdb():
    bench_surrealdb(load_sample_ids())


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
    bench_falkordb(graph, "falkordb", load_sample_ids())


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("db", choices=["cognodb","memgraph","arangodb","surrealdb","falkordb"])
    args = p.parse_args()
    {"cognodb":run_cognodb,"memgraph":run_memgraph,
     "arangodb":run_arangodb,"surrealdb":run_surrealdb,
     "falkordb":run_falkordb}[args.db]()
