import os
import statistics
import time

import httpx

URL = "http://localhost:8000/files"

REQUESTS = 100
TOKEN = os.environ["CLOUDBOX_TOKEN"]

latencies = []
errors = 0

with httpx.Client(headers={"Authorization": f"Bearer {TOKEN}"}) as client:
    for _ in range(REQUESTS):
        start = time.perf_counter()
        try:
            response = client.get(URL)
            elapsed = time.perf_counter() - start

            if response.status_code == 200:
                latencies.append(elapsed * 1000)
            else:
                errors += 1
                print(f"Request failed: HTTP {response.status_code}")
        except httpx.RequestError as exc:
            errors += 1
            print(f"Network error: {exc}")

if latencies:
    ordered = sorted(latencies)

    print(f"Successful requests: {len(latencies)}")
    print(f"Failed requests: {errors}")

    print(f"Average latency: {statistics.mean(ordered):.2f} ms")

    print(f"p50 latency: {statistics.median(ordered):.2f} ms")
    print(f"p95 latency: {statistics.quantiles(ordered, n=100)[94]:.2f} ms")
    print(f"p99 latency: {statistics.quantiles(ordered, n=100)[98]:.2f} ms")

else:
    print("No successful requests. Check the API and authentication.")
    print(f"Failed requests: {errors}")
