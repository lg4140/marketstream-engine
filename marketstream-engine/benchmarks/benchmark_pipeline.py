"""Example: python benchmarks/benchmark_pipeline.py --sizes 10000 100000"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

from marketstream.observability.benchmark import benchmark_rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", type=int, nargs="+", default=[10000, 100000])
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("outputs/benchmark_results.json"))
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    outputs = []
    for size in args.sizes:
        measurements = [benchmark_rows(size) for _ in range(args.repeats)]
        outputs.append({
            "size": size,
            "repeats": args.repeats,
            "median_elapsed_s": statistics.median(m["total_elapsed_s"] for m in measurements),
            "median_throughput_rows_s": statistics.median(
                m["throughput_snapshots_per_s"] for m in measurements
            ),
            "measurements": measurements,
        })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(outputs, indent=2) + "\n", encoding="utf-8")
    summary = [{k: v for k, v in item.items() if k != "measurements"}
               for item in outputs]
    print(json.dumps({"output": str(args.output), "summary": summary}, indent=2))


if __name__ == "__main__":
    main()
