"""
Download and sample the SNAP soc-Pokec social network dataset.
Output: data/nodes.csv and data/edges.csv
Target: ~50,000 nodes, ~200,000 relationships (fits every free tier).
"""

import os
import gzip
import random
import urllib.request
import csv

NODES_URL = "https://snap.stanford.edu/data/soc-pokec-profiles.txt.gz"
EDGES_URL  = "https://snap.stanford.edu/data/soc-pokec-relationships.txt.gz"

DATA_DIR    = os.path.dirname(__file__)
NODES_GZ    = os.path.join(DATA_DIR, "soc-pokec-profiles.txt.gz")
EDGES_GZ    = os.path.join(DATA_DIR, "soc-pokec-relationships.txt.gz")
NODES_CSV   = os.path.join(DATA_DIR, "nodes.csv")
EDGES_CSV   = os.path.join(DATA_DIR, "edges.csv")

TARGET_NODES = 50_000
TARGET_EDGES = 200_000

SEED = 42
random.seed(SEED)


def download(url: str, dest: str) -> None:
    if os.path.exists(dest):
        print(f"  already downloaded: {dest}")
        return
    print(f"  downloading {url} ...")
    urllib.request.urlretrieve(url, dest)
    print(f"  saved to {dest}")


def sample_nodes() -> set:
    """Stream the profiles file and pick TARGET_NODES at random (reservoir sampling)."""
    print("Sampling nodes ...")
    reservoir: list[str] = []
    n = 0
    with gzip.open(NODES_GZ, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if not parts[0].isdigit():
                continue
            n += 1
            if len(reservoir) < TARGET_NODES:
                reservoir.append(parts[0])
            else:
                j = random.randint(0, n - 1)
                if j < TARGET_NODES:
                    reservoir[j] = parts[0]
    sampled = set(reservoir)
    print(f"  sampled {len(sampled):,} nodes from {n:,} total")
    return sampled


def write_nodes(sampled: set) -> None:
    print("Writing nodes.csv ...")
    with open(NODES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id:ID", "age:INT", "gender:INT", ":LABEL"])
        # Re-stream to pick up age/gender from the profiles
        with gzip.open(NODES_GZ, "rt", encoding="utf-8", errors="replace") as gz:
            for line in gz:
                parts = line.rstrip("\n").split("\t")
                if not parts[0].isdigit() or parts[0] not in sampled:
                    continue
                nid    = parts[0]
                gender = parts[3] if len(parts) > 3 and parts[3] in ("0", "1") else ""
                age    = parts[2] if len(parts) > 2 and parts[2].isdigit() else ""
                writer.writerow([nid, age, gender, "User"])
    print(f"  wrote {NODES_CSV}")


def write_edges(sampled: set) -> int:
    print("Sampling edges ...")
    kept: list[tuple[str, str]] = []
    with gzip.open(EDGES_GZ, "rt", encoding="utf-8", errors="replace") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 2:
                continue
            src, dst = parts[0], parts[1]
            if src in sampled and dst in sampled:
                kept.append((src, dst))

    # If we have more than TARGET_EDGES, subsample
    if len(kept) > TARGET_EDGES:
        kept = random.sample(kept, TARGET_EDGES)

    print(f"  writing {len(kept):,} edges to edges.csv ...")
    with open(EDGES_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([":START_ID", ":END_ID", ":TYPE"])
        for src, dst in kept:
            writer.writerow([src, dst, "FOLLOWS"])

    print(f"  wrote {EDGES_CSV}")
    return len(kept)


def main() -> None:
    print("=== Pokec dataset preparation ===")
    download(NODES_URL, NODES_GZ)
    download(EDGES_URL,  EDGES_GZ)

    sampled = sample_nodes()
    write_nodes(sampled)
    n_edges = write_edges(sampled)

    print("\nDataset summary:")
    print(f"  Nodes : {len(sampled):,}  → data/nodes.csv")
    print(f"  Edges : {n_edges:,}  → data/edges.csv")
    print("  Label : User  |  Relationship : FOLLOWS")
    print("  Source: https://snap.stanford.edu/data/soc-Pokec.html")
    print("Done.")


if __name__ == "__main__":
    main()
