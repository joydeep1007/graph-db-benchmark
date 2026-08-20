"""
Shared utilities for all benchmark workloads.
- time_query()  : run a callable N times, return latency list (ms)
- percentile()  : compute p50 / p95
- save_result() : append a result dict to results/raw/<db_name>.json
"""

import json
import os
import statistics
import time
from typing import Any, Callable


RESULTS_DIR = os.path.join(os.path.dirname(__file__), "..", "results", "raw")
os.makedirs(RESULTS_DIR, exist_ok=True)


def time_query(fn: Callable, iterations: int = 100) -> list[float]:
    """
    Run fn() `iterations` times and return latencies in milliseconds.
    First call is a warm-up and is excluded from results.
    """
    fn()  # warm-up
    latencies: list[float] = []
    for _ in range(iterations):
        t0 = time.perf_counter()
        fn()
        latencies.append((time.perf_counter() - t0) * 1000)
    return latencies


def percentile(data: list[float], p: float) -> float:
    """Return the p-th percentile of data (0–100)."""
    if not data:
        return float("nan")
    sorted_data = sorted(data)
    idx = (p / 100) * (len(sorted_data) - 1)
    lower = int(idx)
    upper = lower + 1
    if upper >= len(sorted_data):
        return sorted_data[-1]
    frac = idx - lower
    return sorted_data[lower] + frac * (sorted_data[upper] - sorted_data[lower])


def summarise(latencies: list[float]) -> dict:
    return {
        "p50_ms":  round(percentile(latencies, 50), 3),
        "p95_ms":  round(percentile(latencies, 95), 3),
        "mean_ms": round(statistics.mean(latencies), 3),
        "min_ms":  round(min(latencies), 3),
        "max_ms":  round(max(latencies), 3),
        "n":       len(latencies),
    }


def save_result(db_name: str, category: str, metric: str, data: Any) -> None:
    path = os.path.join(RESULTS_DIR, f"{db_name}.json")
    results: dict = {}
    if os.path.exists(path):
        with open(path) as f:
            results = json.load(f)
    results.setdefault(category, {})[metric] = data
    with open(path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"  [{db_name}] {category}/{metric} saved")
