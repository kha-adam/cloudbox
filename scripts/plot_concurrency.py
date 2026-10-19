import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt

CSV_PATH = Path("benchmarks/concurrency_results_auto.csv")
OUTPUT_DIR = Path("benchmarks/graphs")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

results = []

with CSV_PATH.open(newline="") as csvfile:
    reader = csv.DictReader(csvfile)

    for row in reader:
        results.append(
            {
                "concurrency": int(row["concurrency"]),
                "throughput": float(row["throughput_rps"]),
                "p95": float(row["p95_ms"]),
            }
        )

if not results:
    raise ValueError("The CSV contains no benchmark results.")

# Group measurements by concurrency level.
groups = defaultdict(list)

for result in results:
    groups[result["concurrency"]].append(result)

levels = sorted(groups)

# Calculate the mean across repeated runs at each concurrency level.
mean_throughput = [
    sum(r["throughput"] for r in groups[level]) / len(groups[level]) for level in levels
]
mean_p95 = [
    sum(r["p95"] for r in groups[level]) / len(groups[level]) for level in levels
]

# Graph 1: throughput
plt.figure()
plt.scatter(
    [r["concurrency"] for r in results],
    [r["throughput"] for r in results],
    label="Individual runs",
)
plt.plot(levels, mean_throughput, marker="o", label="Mean")
plt.xlabel("Concurrency (simultaneous workers)")
plt.ylabel("Throughput (requests/second)")
plt.title("CloudBox: Throughput vs Concurrency")
plt.xticks(levels)
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "throughput.png", dpi=150)

# Graph 2: p95 latency
plt.figure()
plt.scatter(
    [r["concurrency"] for r in results],
    [r["p95"] for r in results],
    label="Individual runs",
)
plt.plot(levels, mean_p95, marker="o", label="Mean")
plt.xlabel("Concurrency (simultaneous workers)")
plt.ylabel("p95 latency (milliseconds)")
plt.title("CloudBox: p95 Latency vs Concurrency")
plt.xticks(levels)
plt.grid(True)
plt.legend()
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "p95_latency.png", dpi=150)

print(f"Graphs saved to {OUTPUT_DIR}/")
