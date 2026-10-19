from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# Paths
INPUT_PATH = Path("benchmarks/upload_size_results.csv")
OUTPUT_DIR = Path("benchmarks/graphs")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Load benchmark results
df = pd.read_csv(INPUT_PATH)

if df.empty:
    raise ValueError(f"No benchmark results found in {INPUT_PATH}")

required_columns = {"file_size_mib", "median_ms", "p95_ms"}
missing = required_columns - set(df.columns)

if missing:
    raise ValueError(f"Missing required CSV columns: {missing}")

# Average results across runs for each file size
summary = (
    df.groupby("file_size_mib", as_index=False)
    .agg(
        median_ms=("median_ms", "mean"),
        p95_ms=("p95_ms", "mean"),
        runs=("file_size_mib", "count"),
    )
    .sort_values("file_size_mib")
)

print("\nUpload benchmark summary:")
print(summary.to_string(index=False))

# Graph 1: Median upload latency
plt.figure()
plt.plot(
    summary["file_size_mib"],
    summary["median_ms"],
    marker="o",
)
plt.xlabel("File size (MiB)")
plt.ylabel("Median upload latency (ms)")
plt.title("CloudBox Upload Latency vs File Size")
plt.xticks(summary["file_size_mib"])
plt.grid(True)
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "upload_median_latency.png", dpi=150)
plt.close()

# Graph 2: P95 upload latency
plt.figure()
plt.plot(
    summary["file_size_mib"],
    summary["p95_ms"],
    marker="o",
)
plt.xlabel("File size (MiB)")
plt.ylabel("P95 upload latency (ms)")
plt.title("CloudBox P95 Upload Latency vs File Size")
plt.xticks(summary["file_size_mib"])
plt.grid(True)
plt.tight_layout()
plt.savefig(OUTPUT_DIR / "upload_p95_latency.png", dpi=150)
plt.close()

print(f"\nGraphs saved to {OUTPUT_DIR}")
