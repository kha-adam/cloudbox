import csv
import math
import os
import statistics
import time
import uuid
from datetime import datetime
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8000"
UPLOAD_URL = f"{BASE_URL}/files"

TOKEN = os.environ["CLOUDBOX_TOKEN"]

FILE_SIZES_MIB = [1, 5, 10]

filename = f"benchmark-{uuid.uuid4().hex}.bin"
headers = {"Authorization": f"Bearer {TOKEN}"}


REQUESTS = 30
summary_rows = []


def upload_and_delete(client, payload, headers):
    filename = f"benchmark-{uuid.uuid4().hex}.bin"
    start = time.perf_counter()
    response = client.post(
        UPLOAD_URL,
        headers=headers,
        files={
            "file": (
                filename,
                payload,
                "application/octet-stream",
            )
        },
    )
    elapsed_ms = (time.perf_counter() - start) * 1000

    response.raise_for_status()
    result = response.json()

    delete_response = client.delete(
        f"{BASE_URL}/files/{result['id']}",
        headers=headers,
    )
    delete_response.raise_for_status()

    return elapsed_ms, result


for size_mb in FILE_SIZES_MIB:
    FILE_SIZES_BYTES = size_mb * 1024 * 1024
    payload = os.urandom(FILE_SIZES_BYTES)
    latencies_ms = []

    print(f"\nWarming up with {size_mb} MiB files...")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    with httpx.Client(timeout=30.0) as client:
        for _ in range(10):
            upload_and_delete(client, payload, headers)
        for i in range(REQUESTS):
            start = time.perf_counter()

            elapsed_ms, result = upload_and_delete(
                client, payload=payload, headers=headers
            )

            latencies_ms.append(elapsed_ms)

    ordered = sorted(latencies_ms)
    p95_index = math.ceil(0.95 * len(ordered)) - 1

    print("\n=== Upload Benchmark Results ===")
    print(f"\nBenchmarking {size_mb} MiB files")
    print(f"Successful uploads: {len(latencies_ms)}/{REQUESTS}")
    print(f"Average latency: {statistics.mean(latencies_ms):.2f} ms")
    print(f"Median latency: {statistics.median(latencies_ms):.2f} ms")
    print(f"P95 latency: {ordered[p95_index]:.2f} ms")
    print(f"Min latency: {min(latencies_ms):.2f} ms")
    print(f"Max latency: {max(latencies_ms):.2f} ms")
    summary_rows.append(
        {
            "run_id": run_id,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "file_size_mib": size_mb,
            "requests": REQUESTS,
            "successes": len(latencies_ms),
            "mean_ms": round(statistics.mean(latencies_ms), 2),
            "median_ms": round(statistics.median(latencies_ms), 2),
            "p95_ms": round(ordered[p95_index], 2),
            "min_ms": round(min(latencies_ms), 2),
            "max_ms": round(max(latencies_ms), 2),
        }
    )

output_path = Path("benchmarks/upload_size_results_opti_try_1.csv")
output_path.parent.mkdir(parents=True, exist_ok=True)

with open(output_path, "a", newline="") as csvfile:
    fieldnames = summary_rows[0].keys()

    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

    if csvfile.tell() == 0:
        writer.writeheader()
    writer.writerows(summary_rows)

print(f"Results saved to {output_path}")
