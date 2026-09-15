"""CLI benchmarking tool for evaluating API latency and Redis cache acceleration."""
from __future__ import annotations

import argparse
import statistics
import time
from typing import Any
import httpx

ENDPOINTS_TO_BENCHMARK = [
    {"name": "Team Standings", "path": "/teams?season=2024-25"},
    {"name": "Player Search", "path": "/players?search=LeBron&season=2024-25"},
    {"name": "Surging Players", "path": "/analytics/surging-players?limit=10&season=2024-25"},
    {"name": "Team Ratings", "path": "/analytics/team-ratings?season=2024-25&sort_by=adjusted_net_rating"},
    {"name": "Team Specific Ratings", "path": "/teams/1610612747/ratings?season=2024-25"},
]


def calculate_percentiles(latencies: list[float]) -> dict[str, float]:
    """Compute min, mean, p50, p95, and p99 response times in milliseconds."""
    sorted_latencies = sorted(latencies)
    count = len(sorted_latencies)
    return {
        "min": round(min(sorted_latencies), 2),
        "mean": round(statistics.mean(sorted_latencies), 2),
        "p50": round(sorted_latencies[int(count * 0.50)], 2),
        "p95": round(sorted_latencies[int(count * 0.95)], 2),
        "p99": round(sorted_latencies[min(int(count * 0.99), count - 1)], 2),
        "max": round(max(sorted_latencies), 2),
    }


def run_benchmark(base_url: str, iterations: int) -> None:
    """Execute cold vs. warm cache benchmarks across core API routes."""
    client = httpx.Client(base_url=base_url, timeout=30.0)

    print("\n" + "=" * 85)
    print(f"  NBA Lakehouse API Latency Benchmark ({iterations} warm iterations per route)")
    print(f"  Target: {base_url}")
    print("=" * 85)

    try:
        flush_resp = client.delete("/cache")
        if flush_resp.status_code == 200:
            print("[\u2713] Flushed Redis cache prior to benchmarking.\n")
    except Exception as exc:
        print(f"[!] Warning: Unable to issue cache flush: {exc}\n")

    results: list[dict[str, Any]] = []

    for route in ENDPOINTS_TO_BENCHMARK:
        name = route["name"]
        path = route["path"]

        # 1. Measure Cold Query (PostgreSQL Execution + Redis Store)
        start_cold = time.perf_counter()
        cold_resp = client.get(path)
        cold_latency = round((time.perf_counter() - start_cold) * 1000, 2)

        if cold_resp.status_code != 200:
            print(f"[ERROR] Route {path} returned status {cold_resp.status_code}")
            continue

        # 2. Measure Warm Queries (Redis Cache Hits)
        warm_latencies: list[float] = []
        for _ in range(iterations):
            start_warm = time.perf_counter()
            warm_resp = client.get(path)
            warm_lat = (time.perf_counter() - start_warm) * 1000
            if warm_resp.status_code == 200:
                warm_latencies.append(warm_lat)

        stats = calculate_percentiles(warm_latencies)
        speedup = round(cold_latency / max(stats["p50"], 0.1), 1)

        results.append({
            "name": name,
            "cold_ms": cold_latency,
            "p50_ms": stats["p50"],
            "p95_ms": stats["p95"],
            "p99_ms": stats["p99"],
            "speedup": f"{speedup}x",
        })

    header = f"{'Endpoint':<25} | {'Cold (DB)':<10} | {'Warm P50':<9} | {'Warm P95':<9} | {'Warm P99':<9} | {'Speedup':<8}"
    print(header)
    print("-" * len(header))
    for res in results:
        print(
            f"{res['name']:<25} | "
            f"{res['cold_ms']:>7.2f} ms | "
            f"{res['p50_ms']:>6.2f} ms | "
            f"{res['p95_ms']:>6.2f} ms | "
            f"{res['p99_ms']:>6.2f} ms | "
            f"{res['speedup']:>8}"
        )
    print("=" * 85 + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark NBA API latency.")
    parser.add_argument("--url", type=str, default="http://localhost:8000", help="Base API URL")
    parser.add_argument("-n", "--iterations", type=int, default=50, help="Number of warm sample requests")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_benchmark(base_url=args.url, iterations=args.iterations)