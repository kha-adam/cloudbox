import csv
import os
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import httpx

URL = "http://localhost:8000/files"
TOKEN = os.environ["CLOUDBOX_TOKEN"]
CSV_PATH = "benchmarks/concurrency_results_auto.csv"

REQUESTS = 100
CONCURRENCY_LEVELS = [1, 5, 10]

all_results = []


def make_request(client):
    start = time.perf_counter()

    try:
        response = client.get(URL)
        elapsed_ms = (time.perf_counter() - start) * 1000

        if response.status_code == 200:
            return elapsed_ms, True
        return elapsed_ms, False

    except httpx.RequestError:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return elapsed_ms, False


for concurrency in CONCURRENCY_LEVELS:
    latencies = []
    errors = 0

    def worker(_):
        return make_request(client)

    with httpx.Client(
        headers={"Authorization": f"Bearer {TOKEN}"}, timeout=10.0
    ) as client:
        # Warm up the connection and endpoint.
        for _ in range(10):
            response = client.get(URL)
            response.raise_for_status()

        start_run = time.perf_counter()

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            results = list(executor.map(worker, range(REQUESTS)))

        elapsed_seconds = time.perf_counter() - start_run

    for latency_ms, success in results:
        if success:
            latencies.append(latency_ms)
        else:
            errors += 1
    print(f"\nConcurrency: {concurrency}")
    print(f"Successful requests: {len(latencies)}")
    print(f"Failed requests: {errors}")
    print(f"Throughput: {REQUESTS / elapsed_seconds:.2f} requests/second")

    if len(latencies) >= 2:
        ordered = sorted(latencies)
        print(f"Average latency: {statistics.mean(ordered):.2f} ms")
        print(f"p50 latency: {statistics.median(ordered):.2f} ms")
        print(f"p95 latency: {statistics.quantiles(ordered, n=100)[94]:.2f} ms")
        print(f"p99 latency: {statistics.quantiles(ordered, n=100)[98]:.2f} ms")

    all_results.append(
        {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "concurrency": concurrency,
            "requests": REQUESTS,
            "successes": len(latencies),
            "errors": errors,
            "throughput_rps": round(REQUESTS / elapsed_seconds, 2),
            "avg_ms": round(statistics.mean(latencies), 2),
            "p50_ms": round(statistics.median(latencies), 2),
            "p95_ms": round(statistics.quantiles(latencies, n=100)[94], 2),
            "p99_ms": round(statistics.quantiles(latencies, n=100)[98], 2),
        }
    )


with open(CSV_PATH, "a", newline="") as csvfile:
    fieldnames = all_results[0].keys()

    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

    if csvfile.tell() == 0:
        writer.writeheader()

    writer.writerows(all_results)

print(f"\nResults appended to {CSV_PATH}")
