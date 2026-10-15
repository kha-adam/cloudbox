import os
import time
import httpx
import statistics
from concurrent.futures import ThreadPoolExecutor

URL = "http://localhost:8000/files"

REQUESTS = 100
TOKEN = os.environ["CLOUDBOX_TOKEN"]
CONCURRENCY_LEVELS = [1, 5, 10]


def make_request(client):
    start = time.perf_counter()

    try:
        response = client.get(URL)
        elapsed_ms = (time.perf_counter() - start)*1000

        if response.status_code == 200:
            return elapsed_ms, True
        return elapsed_ms, False

    except httpx.RequestError:
        elapsed_ms = (time.perf_counter() - start)*1000
        return elapsed_ms, False

for concurrency in CONCURRENCY_LEVELS:
    latencies = []
    errors = 0
    
    def worker(_):
        return make_request(client)

    with httpx.Client(headers={"Authorization": f"Bearer {TOKEN}"}, timeout=10.0) as client:
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
