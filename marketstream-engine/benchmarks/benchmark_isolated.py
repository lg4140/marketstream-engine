"""Run independent-process synthetic compute/E2E benchmarks; no SLA or speedup claims.

Example:
  python benchmarks/benchmark_isolated.py --mode e2e --rows 10000 --repeats 5
"""
from __future__ import annotations

import argparse
import json
import math
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def worker(mode: str, rows: int) -> dict:
    import resource

    from marketstream.config import PipelineConfig
    from marketstream.observability.benchmark import benchmark_rows
    from marketstream.processing.pipeline import execute_pipeline

    if mode == "compute":
        m = benchmark_rows(rows)
        return {"elapsed_s": m["total_elapsed_s"],
                "actual_rows": m["processed_snapshot_rows"],
                "peak_rss_mib": m["process_peak_rss_mib_high_water"]}
    stocks = math.ceil(rows / 1500)
    per_stock = math.ceil(rows / stocks)
    with tempfile.TemporaryDirectory(prefix="marketstream-benchmark-") as temp:
        config = PipelineConfig(output_dir=str(Path(temp) / "out"),
                                n_stocks=stocks, n_snapshots=per_stock,
                                save_figure=False, trade_consistency="strict")
        start = time.perf_counter()
        result = execute_pipeline(config, "csv")
        elapsed = time.perf_counter() - start
        actual = result.manifest["record_counts"]["features"]
        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        mib = usage / (1024 * 1024 if sys.platform == "darwin" else 1024)
    return {"elapsed_s": round(elapsed, 6), "actual_rows": actual,
            "peak_rss_mib": round(mib, 2)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["compute", "e2e"], default="e2e")
    p.add_argument("--rows", type=int, default=10000)
    p.add_argument("--repeats", type=int, default=5)
    p.add_argument("--output", type=Path, default=None)
    p.add_argument("--worker", action="store_true")
    args = p.parse_args()
    if not 1000 <= args.rows <= 1_000_000 or not 1 <= args.repeats <= 20:
        p.error("rows must be 1000..1000000 and repeats 1..20")
    if args.worker:
        print(json.dumps(worker(args.mode, args.rows)))
        return
    measurements = []
    for i in range(args.repeats):
        command = [sys.executable, str(Path(__file__).resolve()), "--worker", "--mode",
                   args.mode, "--rows", str(args.rows)]
        child = subprocess.run(command, capture_output=True, text=True, check=True)
        item = json.loads(child.stdout.strip().splitlines()[-1])
        item["throughput_rows_per_s"] = round(item["actual_rows"] / item["elapsed_s"], 2)
        measurements.append(item)
    output = {
        "mode": args.mode,
        "requested_rows": args.rows,
        "repetitions": args.repeats,
        "median_elapsed_s": statistics.median(m["elapsed_s"] for m in measurements),
        "median_throughput_rows_s": statistics.median(m["throughput_rows_per_s"] for m in measurements),
        "max_process_rss_mib": max(m["peak_rss_mib"] for m in measurements),
        "python": sys.version.split()[0],
        "pandas": __import__("pandas").__version__,
        "platform": platform.platform(),
        "measurements": measurements,
        "limitations": "Synthetic only; fresh process each repetition; no legacy baseline; RSS is process high-water, not incremental allocation; no plot",
    }
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
