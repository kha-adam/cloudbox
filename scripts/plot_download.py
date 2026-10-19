from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

INPUT_PATH = Path("benchmarks/download_size_results.csv")
OUTPUT_DIR = Path("benchmarks/graphs")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(INPUT_PATH)

if df.empty:
    raise ValueError(f"No benchmark results found in {INPUT_PATH}")

required_columns = {
    "file_size_mib",
    "median_ms",
    "p95_ms",
    "throughput_mib_s",
}

missing = required_columns - set(df.columns)
if missing:
    raise ValueError(f"Missing required CSV columns: {missing}")

# Average each run's summary metrics by file size.
summary = (
    df.groupby("file_size_mib", as_index=False)
    .agg(
        median_ms=("median_ms", "mean"),
        p95_ms=("p95_ms", "mean"),
        throughput_mib_s=("throughput_mib_s", "mean"),
        runs=("file_size_mib", "count"),
    )
    .sort_values("file_size_mib")
)

print("\nDownload benchmark summary:")
print(summary.to_string(index=False))


def save_plot(y_column, y_label, title, filename):
    plt.figure()
    plt.plot(
        summary["file_size_mib"],
        summary[y_column],
        marker="o",
    )
    plt.xlabel("File size (MiB)")
    plt.ylabel(y_label)
    plt.title(title)
    plt.xticks(summary["file_size_mib"])
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(OUTPUT_DIR / filename, dpi=150)
    plt.close()


save_plot(
    "median_ms",
    "Median download latency (ms)",
    "CloudBox Download Latency vs File Size",
    "download_median_latency.png",
)

save_plot(
    "p95_ms",
    "P95 download latency (ms)",
    "CloudBox P95 Download Latency vs File Size",
    "download_p95_latency.png",
)

save_plot(
    "throughput_mib_s",
    "Effective throughput (MiB/s)",
    "CloudBox Download Throughput vs File Size",
    "download_throughput.png",
)

print(f"\nGraphs saved to {OUTPUT_DIR}")
