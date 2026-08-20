"""
Mixed concurrent read/write workload.

Tests sustained throughput (queries/second) under concurrent clients.
Concurrency levels: 1, 10, 20, 40 clients.
Read/write mix: 80% reads (1-hop traversal), 20% writes (update age property).
Duration: 30 seconds per concurrency level.

Metrics reported:
  - Sustained queries/second (QPS)
  - p50 / p95 latency across all ops
  - Error count (timeouts, throttling)
"""

import csv
import os
import random
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from workloads.utils import summarise, save_result

DATA_DIR  = os.path.join(os.path.dirname(__file__), "..", "data")
NODES_CSV = os.path.join(DATA_DIR, "nodes.csv")

CONCURRENCY_LEVELS = [1, 10, 20, 40]
DURATION_SECONDS   = 30
READ_RATIO         = 0.8   # 80% reads, 20% writes


def load_ids(n=200) -> list[str]:
    ids = []
    with open(NODES_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ids.append(row["id:ID"])
    return random.sample(ids, min(n, len(ids)))


@dataclass
class WorkerResult:
    latencies: list[float] = field(default_factory=list)
    errors:    int = 0
    ops:       int = 0


def run_workers(
    n_workers:    int,
    duration:     float,
    make_read_fn: Callable,
    make_write_fn: Callable,
    sample_ids:   list[str],
) -> WorkerResult:
    """Spin up n_workers threads, each alternating reads and writes for `duration` seconds."""
    results: list[WorkerResult] = [WorkerResult() for _ in range(n_workers)]
    stop = threading.Event()

    def worker(wid: int):
        res = results[wid]
        read_fn  = make_read_fn(wid)
        write_fn = make_write_fn(wid)
        i = 0
        while not stop.is_set():
            nid = sample_ids[i % len(sample_ids)]
            is_read = random.random() < READ_RATIO
            fn = read_fn(nid) if is_read else write_fn(nid)
            t0 = time.perf_counter()
            try:
                fn()
                res.latencies.append((time.perf_counter() - t0) * 1000)
                res.ops += 1
            except Exception as e:
                res.errors += 1
            i += 1

    threads = [threading.Thread(target=worker, args=(wid,), daemon=True)
               for wid in range(n_workers)]
    for t in threads:
        t.start()
    time.sleep(duration)
    stop.set()
    for t in threads:
        t.join(timeout=5)

    combined = WorkerResult()
    for r in results:
        combined.latencies.extend(r.latencies)
        combined.errors    += r.errors
        combined.ops       += r.ops
    return combined


# ─── Cypher (CognoDB / Memgraph) ─────────────────────────────────────

def bench_cypher_mixed(make_driver_fn, db_name: str, sample_ids: list[str]) -> None:
    print(f"\n  {db_name} mixed workload")

    for n in CONCURRENCY_LEVELS:
        # Each worker gets its own session (driver is thread-safe)
        driver = make_driver_fn()
        sessions = [driver.session() for _ in range(n)]

        def make_read(wid):
            s = sessions[wid % len(sessions)]
            return lambda nid: s.run(
                "MATCH (u:User {id:$id})-[:FOLLOWS]->(v) RETURN count(v)", id=nid
            ).single()

        def make_write(wid):
            s = sessions[wid % len(sessions)]
            return lambda nid: s.run(
                "MATCH (u:User {id:$id}) SET u.last_seen=$ts",
                id=nid, ts=int(time.time()),
            )

        res = run_workers(n, DURATION_SECONDS, make_read, make_write, sample_ids)
        qps = res.ops / DURATION_SECONDS
        stats = summarise(res.latencies) if res.latencies else {}
        stats["qps"]         = round(qps, 1)
        stats["errors"]      = res.errors
        stats["concurrency"] = n
        stats["duration_s"]  = DURATION_SECONDS
        stats["read_ratio"]  = READ_RATIO
        save_result(db_name, "mixed", f"c{n}", stats)
        print(f"    c={n:2d} → {qps:6.1f} QPS  p50={stats.get('p50_ms','?')}ms"
              f"  p95={stats.get('p95_ms','?')}ms  errors={res.errors}")

        for s in sessions:
            s.close()
        driver.close()


# ─── FalkorDB ─────────────────────────────────────────────────────────────────

def bench_falkordb_mixed(sample_ids: list[str]) -> None:
    print("\n  FalkorDB mixed workload")
    from falkordb import FalkorDB
    host = os.environ.get("FALKORDB_HOST", "localhost")
    port = int(os.environ.get("FALKORDB_PORT", 6379))
    pw   = os.environ.get("FALKORDB_PASSWORD", "")
    kwargs = {"host": host, "port": port}
    if pw:
        kwargs["password"] = pw

    for n in CONCURRENCY_LEVELS:
        db = FalkorDB(**kwargs)
        graphs = [db.select_graph("pokec") for _ in range(n)]

        def make_read(wid):
            g = graphs[wid % len(graphs)]
            return lambda nid: g.query(
                "MATCH (u:User {id:$id})-[:FOLLOWS]->(v) RETURN count(v)", params={"id":nid}
            )

        def make_write(wid):
            g = graphs[wid % len(graphs)]
            return lambda nid: g.query(
                "MATCH (u:User {id:$id}) SET u.last_seen=$ts",
                params={"id":nid, "ts":int(time.time())},
            )

        res = run_workers(n, DURATION_SECONDS, make_read, make_write, sample_ids)
        qps = res.ops / DURATION_SECONDS
        stats = summarise(res.latencies) if res.latencies else {}
        stats.update({"qps": round(qps,1), "errors": res.errors,
                      "concurrency": n, "duration_s": DURATION_SECONDS})
        save_result("falkordb", "mixed", f"c{n}", stats)
        print(f"    c={n:2d} → {qps:6.1f} QPS  p50={stats.get('p50_ms','?')}ms"
              f"  p95={stats.get('p95_ms','?')}ms  errors={res.errors}")


# ─── ArangoDB ─────────────────────────────────────────────────────────────────

def bench_arango_mixed(db, sample_ids: list[str]) -> None:
    print("\n  ArangoDB mixed workload")

    for n in CONCURRENCY_LEVELS:
        def make_read(_wid):
            return lambda nid: list(db.aql.execute(
                "FOR v IN 1..1 OUTBOUND @s follows COLLECT WITH COUNT INTO c RETURN c",
                bind_vars={"s": f"users/{nid}"},
            ))

        def make_write(_wid):
            return lambda nid: db.aql.execute(
                "FOR u IN users FILTER u.user_id==@id UPDATE u WITH {last_seen:@ts} IN users",
                bind_vars={"id": nid, "ts": int(time.time())},
            )

        res = run_workers(n, DURATION_SECONDS, make_read, make_write, sample_ids)
        qps = res.ops / DURATION_SECONDS
        stats = summarise(res.latencies) if res.latencies else {}
        stats.update({"qps": round(qps,1), "errors": res.errors,
                      "concurrency": n, "duration_s": DURATION_SECONDS})
        save_result("arangodb", "mixed", f"c{n}", stats)
        print(f"    c={n:2d} → {qps:6.1f} QPS  p50={stats.get('p50_ms','?')}ms"
              f"  p95={stats.get('p95_ms','?')}ms  errors={res.errors}")


# ─── SurrealDB ────────────────────────────────────────────────────────────────

def bench_surreal_mixed(sample_ids: list[str]) -> None:
    """SurrealDB uses a separate connection per worker thread via asyncio."""
    import asyncio
    from surrealdb import Surreal
    print("\n  SurrealDB mixed workload")

    url  = os.environ.get("SURREALDB_URL", "ws://localhost:8000/rpc")
    user = os.environ.get("SURREALDB_USER", "root")
    pw   = os.environ["SURREALDB_PASSWORD"]
    ns   = os.environ.get("SURREALDB_NS",   "bench")
    dbn  = os.environ.get("SURREALDB_DB",   "pokec")

    async def worker_async(wid, stop_event, results, n_workers):
        db = Surreal(url)
        await db.connect()
        await db.signin({"user": user, "pass": pw})
        await db.use(ns, dbn)
        lats, ops, errors = [], 0, 0
        i = 0
        while not stop_event.is_set():
            nid = sample_ids[i % len(sample_ids)]
            is_read = random.random() < READ_RATIO
            t0 = time.perf_counter()
            try:
                if is_read:
                    await db.query(f"SELECT ->follows->user FROM user:`{nid}`")
                else:
                    await db.query(
                        f"UPDATE user:`{nid}` SET last_seen = {int(time.time())}"
                    )
                lats.append((time.perf_counter() - t0) * 1000)
                ops += 1
            except Exception:
                errors += 1
            i += 1
        await db.close()
        results.append((lats, ops, errors))

    for n in CONCURRENCY_LEVELS:
        async def run_level(n=n):
            stop_event = asyncio.Event()
            results_list = []
            tasks = [asyncio.create_task(
                worker_async(wid, stop_event, results_list, n)
            ) for wid in range(n)]
            await asyncio.sleep(DURATION_SECONDS)
            stop_event.set()
            await asyncio.gather(*tasks, return_exceptions=True)
            return results_list

        all_results = asyncio.run(run_level())
        all_lats = []
        total_ops = total_errors = 0
        for lats, ops, errs in all_results:
            all_lats.extend(lats)
            total_ops += ops
            total_errors += errs

        qps   = total_ops / DURATION_SECONDS
        stats = summarise(all_lats) if all_lats else {}
        stats.update({"qps": round(qps,1), "errors": total_errors,
                      "concurrency": n, "duration_s": DURATION_SECONDS})
        save_result("surrealdb", "mixed", f"c{n}", stats)
        print(f"    c={n:2d} → {qps:6.1f} QPS  p50={stats.get('p50_ms','?')}ms"
              f"  p95={stats.get('p95_ms','?')}ms  errors={total_errors}")


# ─── Entry points ─────────────────────────────────────────────────────────────

def _cypher_runner(env_uri, env_user_key, env_user_default, env_pw, bolt_prefix=""):
    from neo4j import GraphDatabase
    uri  = os.environ[env_uri]
    user = os.environ.get(env_user_key, env_user_default)
    pw   = os.environ[env_pw]
    return lambda: GraphDatabase.driver(uri, auth=(user, pw))


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("db", choices=["cognodb","memgraph","arangodb","surrealdb","falkordb"])
    args = p.parse_args()
    sample = load_ids()

    if args.db == "cognodb":
        bench_cypher_mixed(
            _cypher_runner("COGNODB_URI","COGNODB_USER","cognodb","COGNODB_PASSWORD"),
            "cognodb", sample)

    elif args.db == "memgraph":
        from neo4j import GraphDatabase
        host = os.environ.get("MEMGRAPH_HOST","localhost")
        port = os.environ.get("MEMGRAPH_PORT","7687")
        user = os.environ.get("MEMGRAPH_USER","")
        pw   = os.environ.get("MEMGRAPH_PASSWORD","")
        auth = (user, pw) if user else None
        bench_cypher_mixed(
            lambda: GraphDatabase.driver(f"bolt://{host}:{port}", auth=auth),
            "memgraph", sample)
    elif args.db == "arangodb":
        from arango.client import ArangoClient
        client = ArangoClient(
            hosts=f"http://{os.environ.get('ARANGODB_HOST','localhost')}:{os.environ.get('ARANGODB_PORT','8529')}"
        )
        db = client.db("pokec_bench",
                       username=os.environ.get("ARANGODB_USER","root"),
                       password=os.environ["ARANGODB_PASSWORD"])
        bench_arango_mixed(db, sample)
    elif args.db == "surrealdb":
        bench_surreal_mixed(sample)
    elif args.db == "falkordb":
        bench_falkordb_mixed(sample)
