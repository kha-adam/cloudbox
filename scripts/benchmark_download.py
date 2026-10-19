import csv
import math
import os
import statistics
import time
from datetime import datetime
from pathlib import Path

import httpx

BASE_URL = "http://localhost:8000"
UPLOAD_URL = f"{BASE_URL}/files"

TOKEN = os.environ["CLOUDBOX_TOKEN"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

FILE_SIZES_MIB = [1, 5, 10]
REQUESTS = 30
WARMUP_REQUESTS = 3

OUTPUT_PATH = Path("benchmarks/download_size_results.csv")


def upload_test_file(client, size_mib):
    """Create one test file outside the measured download interval."""
    payload = os.urandom(size_mib * 1024 * 1024)
    filename = f"download-benchmark-{size_mib}MiB.bin"

    response = client.post(
        UPLOAD_URL,
        headers=HEADERS,
        files={
            "file": (
                filename,
                payload,
                "application/octet-stream",
            )
        },
    )
    response.raise_for_status()

    result = response.json()
    return result["id"], len(payload)


def download_once(client, file_id):
    """Download a file and return elapsed time and bytes received."""
    start = time.perf_counter()

    response = client.get(
        f"{BASE_URL}/files/{file_id}/download",
        headers=HEADERS,
    )

    elapsed_ms = (time.perf_counter() - start) * 1000
    response.raise_for_status()

    return elapsed_ms, len(response.content)


def delete_test_file(client, file_id):
    response = client.delete(
        f"{BASE_URL}/files/{file_id}",
        headers=HEADERS,
    )
    response.raise_for_status()


def main():
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_rows = []

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client(timeout=60.0) as client:
        for size_mib in FILE_SIZES_MIB:
            print(f"\nPreparing {size_mib} MiB test file...")

            file_id, expected_bytes = upload_test_file(client, size_mib)

            latencies_ms = []

            try:
                print(f"Warming up with {WARMUP_REQUESTS} downloads...")

                for _ in range(WARMUP_REQUESTS):
                    _, received_bytes = download_once(client, file_id)

                    if received_bytes != expected_bytes:
                        raise ValueError(
                            f"Expected {expected_bytes} bytes, "
                            f"received {received_bytes}"
                        )

                print(f"Measuring {REQUESTS} downloads...")

                for i in range(REQUESTS):
                    elapsed_ms, received_bytes = download_once(client, file_id)

                    if received_bytes != expected_bytes:
                        raise ValueError(
                            f"Expected {expected_bytes} bytes, "
                            f"received {received_bytes}"
                        )

                    latencies_ms.append(elapsed_ms)

                ordered = sorted(latencies_ms)
                p95_index = math.ceil(0.95 * len(ordered)) - 1

                median_ms = statistics.median(latencies_ms)
                p95_ms = ordered[p95_index]

                # Effective throughput based on median latency.
                throughput_mib_s = size_mib / (median_ms / 1000)

                print(f"\nResults for {size_mib} MiB")
                print(f"Successful downloads: {len(latencies_ms)}/{REQUESTS}")
                print(f"Median latency: {median_ms:.2f} ms")
                print(f"P95 latency: {p95_ms:.2f} ms")
                print(f"Throughput: {throughput_mib_s:.2f} MiB/s")

                summary_rows.append(
                    {
                        "run_id": run_id,
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                        "file_size_mib": size_mib,
                        "requests": REQUESTS,
                        "successes": len(latencies_ms),
                        "median_ms": round(median_ms, 2),
                        "p95_ms": round(p95_ms, 2),
                        "throughput_mib_s": round(throughput_mib_s, 2),
                    }
                )

            finally:
                # Remove the test file even if a download fails.
                delete_test_file(client, file_id)

    fieldnames = list(summary_rows[0].keys())

    with open(OUTPUT_PATH, "a", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        if csvfile.tell() == 0:
            writer.writeheader()

        writer.writerows(summary_rows)

    print(f"\nResults saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
