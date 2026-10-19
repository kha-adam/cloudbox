import csv
import math
import os
import secrets
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import httpx

BASE_URL = os.getenv("CLOUDBOX_BASE_URL", "http://localhost:8000")
TOKEN = os.environ["CLOUDBOX_TOKEN"]

FILE_SIZE_MIB = 5
REQUESTS_PER_LEVEL = 30
CONCURRENCY_LEVELS = [1, 3, 5]
TIMEOUT_SECONDS = 120

OUTPUT_FILE = Path("benchmarks/concurrent_upload_results.csv")


def percentile(values: list[float], percent: float) -> float:
    """Return a nearest-rank percentile."""
    if not values:
        return 0.0

    ordered = sorted(values)
    index = max(0, math.ceil(percent / 100 * len(ordered)) - 1)
    return ordered[index]


def upload(
    client: httpx.Client,
    payload: bytes,
) -> tuple[float, int | None, str | None]:
    """Upload one file and return latency, file ID, and any error."""
    started = time.perf_counter()

    try:
        response = client.post(
            f"{BASE_URL}/files",
            files={
                "file": (
                    "concurrency_benchmark.bin",
                    payload,
                    "application/octet-stream",
                )
            },
        )

        latency_ms = (time.perf_counter() - started) * 1000
        response.raise_for_status()

        file_id = response.json().get("id")
        if not isinstance(file_id, int):
            return latency_ms, None, "Response did not contain an integer file ID"

        return latency_ms, file_id, None

    except httpx.HTTPError as exc:
        latency_ms = (time.perf_counter() - started) * 1000
        return latency_ms, None, f"{type(exc).__name__}: {exc}"


def worker(
    worker_id: int,
    concurrency: int,
    payload: bytes,
    start_barrier: threading.Barrier,
) -> list[tuple[float, int | None, str | None]]:
    """Warm up one client, then perform this worker's share of uploads."""
    headers = {"Authorization": f"Bearer {TOKEN}"}
    results = []

    with httpx.Client(
        headers=headers,
        timeout=TIMEOUT_SECONDS,
    ) as client:
        # Warm up the connection and API before timing.
        _, warmup_id, warmup_error = upload(client, payload)

        if warmup_error:
            raise RuntimeError(f"Worker {worker_id} warm-up failed: {warmup_error}")

        # Keep warm-up data out of the measured benchmark.
        if warmup_id is not None:
            cleanup = client.delete(f"{BASE_URL}/files/{warmup_id}")
            cleanup.raise_for_status()

        # All workers begin the measured phase together.
        start_barrier.wait()

        requests_per_worker = REQUESTS_PER_LEVEL // concurrency

        for _ in range(requests_per_worker):
            results.append(upload(client, payload))

    return results


def cleanup_files(file_ids: list[int]) -> None:
    """Delete benchmark files after timing has finished."""
    headers = {"Authorization": f"Bearer {TOKEN}"}

    with httpx.Client(headers=headers, timeout=TIMEOUT_SECONDS) as client:
        for file_id in file_ids:
            try:
                response = client.delete(f"{BASE_URL}/files/{file_id}")
                response.raise_for_status()
            except httpx.HTTPError as exc:
                print(f"WARNING: could not delete file {file_id}: {exc}")


def main() -> None:
    if REQUESTS_PER_LEVEL % max(CONCURRENCY_LEVELS) != 0:
        raise ValueError(
            "REQUESTS_PER_LEVEL must be divisible by every concurrency level"
        )

    payload = secrets.token_bytes(FILE_SIZE_MIB * 1024 * 1024)
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    columns = [
        "timestamp",
        "file_size_mib",
        "concurrency",
        "requests",
        "successes",
        "errors",
        "throughput_rps",
        "avg_ms",
        "p50_ms",
        "p95_ms",
        "p99_ms",
    ]

    for concurrency in CONCURRENCY_LEVELS:
        print(
            f"\nTesting {FILE_SIZE_MIB} MiB uploads with concurrency={concurrency}..."
        )

        barrier = threading.Barrier(concurrency + 1)
        started = time.perf_counter()
        all_results = []

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [
                executor.submit(
                    worker,
                    worker_id,
                    concurrency,
                    payload,
                    barrier,
                )
                for worker_id in range(concurrency)
            ]

            # Start the clock immediately before releasing all workers.
            started = time.perf_counter()
            barrier.wait()

            for future in futures:
                all_results.extend(future.result())

        elapsed_seconds = time.perf_counter() - started

        latencies = [result[0] for result in all_results]
        file_ids = [result[1] for result in all_results if result[1] is not None]
        errors = [result[2] for result in all_results if result[2] is not None]
        successes = len(all_results) - len(errors)

        row = {
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "file_size_mib": FILE_SIZE_MIB,
            "concurrency": concurrency,
            "requests": len(all_results),
            "successes": successes,
            "errors": len(errors),
            "throughput_rps": round(successes / elapsed_seconds, 2),
            "avg_ms": round(statistics.mean(latencies), 2) if latencies else 0,
            "p50_ms": round(percentile(latencies, 50), 2),
            "p95_ms": round(percentile(latencies, 95), 2),
            "p99_ms": round(percentile(latencies, 99), 2),
        }

        print(
            f"Successes: {successes}/{len(all_results)} | "
            f"Throughput: {row['throughput_rps']} uploads/s | "
            f"Median: {row['p50_ms']} ms | "
            f"P95: {row['p95_ms']} ms | "
            f"Errors: {row['errors']}"
        )

        if errors:
            print("First errors:")
            for error in errors[:3]:
                print(f"  {error}")

        # Delete only after the measured interval has ended.
        cleanup_files(file_ids)

        write_header = not OUTPUT_FILE.exists() or OUTPUT_FILE.stat().st_size == 0
        with OUTPUT_FILE.open("a", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=columns)
            if write_header:
                writer.writeheader()
            writer.writerow(row)

    print(f"\nResults appended to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
