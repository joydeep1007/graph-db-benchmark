# Graph Database Cloud Benchmark

A reproducible benchmark comparing **CognoDB Cloud** against four other graph database platforms on identical resource tiers, the same public dataset, and the same logical workloads.

Submitted for: Wexa AI — CognoDB Assignment 1  
Author: Joydeep Dey  
Repository: <!-- github URL -->

---

## Quick start (reproduce from scratch)

```bash
git clone <this-repo>
cd graph-db-benchmark

# 1. Install dependencies
pip install -r requirements.txt

# 2. Set up credentials
cp .env.example .env
# Edit .env with your connection details for each platform

# 3. Load credentials into shell
source .env

# 4. Run everything (dataset download + load + benchmark + analysis)
bash run_all.sh

# Results land in results/report.md and results/charts/
```

To run only a subset of databases:

```bash
bash run_all.sh cognodb neo4j
```

---

## Databases compared

| Platform          | Tier                      | Protocol             | Query lang | vCPU          | RAM                 | Disk           |
| ----------------- | ------------------------- | -------------------- | ---------- | ------------- | ------------------- | -------------- |
| **CognoDB Cloud** | Free (c0)                 | Bolt (Neo4j-compat.) | Cypher     | 0.5 burstable | 256 MB              | 1 GB           |

| **Memgraph**      | Self-hosted (Render free) | Bolt                 | Cypher     | 0.1 shared    | 256 MB (capped)     | 1 GB           |
| **ArangoDB**      | Self-hosted (Render free) | HTTP/REST            | AQL        | 0.1 shared    | 256 MB (capped)     | 1 GB           |
| **SurrealDB**     | Self-hosted (Render free) | WebSocket            | SurrealQL  | 0.1 shared    | 256 MB (native min) | 1 GB           |

### Resource-capping methodology

- **Memgraph**: started with `--storage-mode=ON_DISK_TRANSACTIONAL --memory-limit=256` to stay within 256 MB. Default in-memory mode would require ≥ 1 GB.
- **ArangoDB**: started with env var `ARANGODB_OVERRIDE_DETECTED_TOTAL_MEMORY=268435456` (256 MB in bytes), which causes ArangoDB to size its internal caches proportionally.
- **SurrealDB**: minimum required RAM is exactly 256 MB; no cap flag needed.
- All self-hosted instances run on Render's free tier (512 MB host, shared 0.1 vCPU), with caps applied above.

### Query language equivalence

Two of the four databases (CognoDB, Memgraph) use identical Cypher queries over Bolt — zero translation required. For the other two:

| Logical query   | Cypher                                                    | AQL (ArangoDB)                                                                  | SurrealQL (SurrealDB)                              |
| --------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------- | -------------------------------------------------- |
| 1-hop traversal | `MATCH (u:User {id:$id})-[:FOLLOWS]->(v) RETURN count(v)` | `FOR v IN 1..1 OUTBOUND @s follows COLLECT WITH COUNT INTO c RETURN c`          | `SELECT ->follows->user FROM user:<id>`            |
| Point lookup    | `MATCH (u:User {id:$id}) RETURN u`                        | `FOR u IN users FILTER u.user_id==@id RETURN u`                                 | `SELECT * FROM user:<id>`                          |
| Aggregation     | `MATCH (u:User) RETURN u.gender, count(u)`                | `FOR u IN users COLLECT g=u.gender WITH COUNT INTO c RETURN {gender:g,count:c}` | `SELECT gender, count() FROM user GROUP BY gender` |

---

## Dataset

**Source**: [SNAP soc-Pokec social network](https://snap.stanford.edu/data/soc-Pokec.html) (J. Takac and M. Zabovsky, 2012)

**Full dataset**: 1,632,803 nodes, 30,622,564 edges  
**Sampled subset** (used in this benchmark):

| Metric            | Value                                                                           |
| ----------------- | ------------------------------------------------------------------------------- |
| Nodes             | ~50,000                                                                         |
| Relationships     | ~200,000                                                                        |
| Node label        | `User`                                                                          |
| Relationship type | `FOLLOWS`                                                                       |
| Node properties   | `id` (string, unique), `age` (int), `gender` (int 0/1)                          |
| Sampling method   | Reservoir sampling (seed=42) over nodes; edges kept if both endpoints in sample |

**Why this size?** At 50k nodes / 200k edges, the dataset fits every platform's free tier with headroom.

**Reproducible sampling**:

```bash
python data/sample_pokec.py
# Downloads ~1 GB, outputs data/nodes.csv and data/edges.csv
# Deterministic: seed=42
```

---

## Methodology

### Load method per platform

| Platform     | Load method                                    | Batch size |
| ------------ | ---------------------------------------------- | ---------- |
| CognoDB      | Neo4j driver `UNWIND ... MERGE`                | 500        |

| Memgraph     | Neo4j driver `UNWIND ... MERGE` (Bolt-compat.) | 500        |
| ArangoDB     | `import_bulk()` via python-arango              | 500        |
| SurrealDB    | `INSERT INTO` + `RELATE` over WebSocket        | 200        |

### Measurement rules

- **Warm-up**: one full query execution discarded before timing starts.
- **Iterations**: 100 per query type per database (50 random start nodes, rotated).
- **Metrics**: p50 and p95 latency in milliseconds (not averages alone).
- **Client machine**: same machine for all databases (where remote — over public internet).
- **Region**: all cloud instances provisioned in the same region where possible.
- **Mixed workload**: 30 seconds per concurrency level (1 / 10 / 20 / 40 concurrent threads), 80% reads / 20% writes.
- **Indexes**: `id` property indexed on all platforms before workloads run.

### Honest caveats

- Self-hosted instances (Memgraph, ArangoDB, SurrealDB) are on Render's **shared** free tier. Cold starts, shared CPU burst, and network variance between Render and cloud-hosted platforms (CognoDB) will inflate latency for self-hosted options. This is documented, not hidden.
- Memgraph's **on-disk mode** is significantly slower than its default in-memory mode. Results reflect a storage-mode constraint, not Memgraph's peak capability.

- ArangoDB and SurrealDB use **different query languages**. We verified logical equivalence of all queries, but some micro-optimisations available in Cypher (e.g. `shortestPath`) have no 1:1 counterpart.
- Network latency between the benchmark client and cloud-hosted instances is included in all latency numbers. The client machine is documented below.

### Client environment

| Property    | Value                                                 |
| ----------- | ----------------------------------------------------- |
| OS          | <!-- e.g. Ubuntu 22.04 -->                            |
| Python      | 3.12.x                                                |
| Network     | <!-- e.g. 100 Mbps home broadband, Kolkata, India --> |
| Date of run | <!-- YYYY-MM-DD -->                                   |

---

## Results

> Auto-generated tables below. For the human analysis see the section after.

<!-- results/report.md is appended here by analyze.py, or copy-paste the tables -->

### Ingest throughput

| Database  | Nodes | Nodes/s | Edges | Edges/s | Total wall-clock |
| --------- | ----- | ------- | ----- | ------- | ---------------- |
| CognoDB   |       |         |       |         |                  |

| Memgraph  |       |         |       |         |                  |
| ArangoDB  |       |         |       |         |                  |
| SurrealDB |       |         |       |         |                  |

### Traversal latency

| Database  | 1-hop p50 | 1-hop p95 | 2-hop p50 | 2-hop p95 | 3-hop p50 | 3-hop p95 |
| --------- | --------- | --------- | --------- | --------- | --------- | --------- |
| CognoDB   |           |           |           |           |           |           |

| Memgraph  |           |           |           |           |           |           |
| ArangoDB  |           |           |           |           |           |           |
| SurrealDB |           |           |           |           |           |           |

### Lookup & aggregation latency

| Database  | Point p50 | Point p95 | Filtered p50 | Filtered p95 | Aggr p50 | Aggr p95 |
| --------- | --------- | --------- | ------------ | ------------ | -------- | -------- |
| CognoDB   |           |           |              |              |          |          |

| Memgraph  |           |           |              |              |          |          |
| ArangoDB  |           |           |              |              |          |          |
| SurrealDB |           |           |              |              |          |          |

### Mixed workload (80% read / 20% write)

| Database  | c=1 QPS | c=10 QPS | c=20 QPS | c=40 QPS | c=40 errors |
| --------- | ------- | -------- | -------- | -------- | ----------- |
| CognoDB   |         |          |          |          |             |

| Memgraph  |         |          |          |          |             |
| ArangoDB  |         |          |          |          |             |
| SurrealDB |         |          |          |          |             |

### Resource footprint

| Database     | Stored data size          | RAM observed     | Notes                              |
| ------------ | ------------------------- | ---------------- | ---------------------------------- |
| CognoDB      | Not observable            | Not observable   | Free tier exposes no metrics       |

| Memgraph     | Via `SHOW STORAGE INFO`   | Via Docker stats | On-disk mode; lower than in-memory |
| ArangoDB     | Via ArangoDB UI → Stats   | Via Docker stats |                                    |
| SurrealDB    | Via `INFO FOR DB`         | Via Docker stats |                                    |

---

## Charts

![Ingest throughput](results/charts/ingest_throughput.png)
![Traversal p50](results/charts/traversal_p50.png)
![Traversal p95](results/charts/traversal_p95.png)
![Lookup p50](results/charts/lookup_p50.png)
![Mixed QPS](results/charts/mixed_qps.png)

---

## Analysis

<!-- Fill this in after running the benchmark. Template below. -->

### What the numbers show

**Ingest**: …

**Traversal**: The Cypher-native databases (CognoDB, Memgraph) show…  
2-hop vs 3-hop latency growth rate reveals how each engine handles intermediate result set explosion…

**Lookup**: Point lookups are fast across all platforms because every database indexes `id`.  
Aggregation latency diverges because…

**Mixed workload**: Under concurrency, … degrades fastest because…  
CognoDB's free tier …

### Why the platforms differ


- **Memgraph (on-disk)**: On-disk transactional mode serialises every node/edge access through RocksDB. This is a resource-constraint artefact, not Memgraph's design target.
- **ArangoDB**: Multi-model architecture adds flexibility but may add overhead for pure graph traversals vs native graph engines.
- **SurrealDB**: SurrealQL's `->follows->user` chained traversal syntax is expressive, but the engine's traversal implementation at 256 MB RAM…

### Fairness note

The two Cypher databases (CognoDB, Memgraph) share identical client code and query text. ArangoDB and SurrealDB use translated queries that are logically equivalent but may have different query plan characteristics. We consider this an honest reflection of using each platform as its designers intended.

---

## File structure

```
graph-db-benchmark/
├── data/
│   ├── sample_pokec.py      # Download + sample the Pokec dataset
│   ├── nodes.csv            # Generated: ~50k nodes
│   └── edges.csv            # Generated: ~200k edges
├── loaders/
│   ├── cognodb_loader.py

│   ├── memgraph_loader.py
│   ├── arangodb_loader.py
│   └── surrealdb_loader.py
├── workloads/
│   ├── utils.py             # Shared timing + result utilities
│   ├── traversal.py         # 1/2/3-hop traversal benchmark
│   ├── lookup.py            # Point + filtered + aggregation
│   └── mixed_workload.py    # Concurrent read/write sweep
├── results/
│   ├── raw/                 # Per-DB JSON result files (git-ignored)
│   ├── charts/              # Generated PNG charts
│   └── report.md            # Auto-generated results matrix
├── analyze.py               # Reads raw/ → charts + report.md
├── run_all.sh               # One-command full pipeline
├── requirements.txt
├── .env.example
└── README.md
```

---

## License

MIT
