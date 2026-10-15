"""Synthetic benchmark: truthful measurements, no preset performance claims."""
from __future__ import annotations

import math
import os
import platform
import resource
import sys
import time

from marketstream.analytics.event_detection import detect_liquidity_gap_fills
from marketstream.analytics.features import add_market_features
from marketstream.ingestion.synthetic_generator import generate_synthetic_market_data
from marketstream.processing.alignment import align_trade_snapshots
from marketstream.processing.validation import validate_snapshots, validate_trades


def _peak_rss_mib() -> float:
    """Process high-water mark, NOT isolated per-run peak; platform-specific."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return round(peak / (1024 * 1024 if sys.platform == "darwin" else 1024), 2)


def benchmark_rows(requested: int = 10000, seed: int = 42) -> dict:
    if requested < 1000 or requested > 1_000_000:
        raise ValueError("Benchmark row target must be 1000..1000000")
    stocks = math.ceil(requested / 1500)
    per_stock = math.ceil(requested / stocks)
    stage = {}
    t0 = time.perf_counter()
    s, t = generate_synthetic_market_data(n_stocks=stocks, n_snapshots=per_stock, seed=seed)
    stage["generate_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    s = validate_snapshots(s)
    t = validate_trades(t)
    stage["validation_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    aligned = align_trade_snapshots(s, t)
    stage["alignment_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    features = add_market_features(aligned)
    stage["features_s"] = time.perf_counter() - t0
    t0 = time.perf_counter()
    events = detect_liquidity_gap_fills(s)
    stage["events_s"] = time.perf_counter() - t0
    total = sum(stage.values())
    return {
        "requested_rows": requested,
        "processed_snapshot_rows": len(features),
        "trade_rows": len(t),
        "candidate_events": len(events),
        "total_elapsed_s": round(total, 4),
        "throughput_snapshots_per_s": round(len(features) / total, 2),
        "stage_seconds": {k: round(v, 4) for k, v in stage.items()},
        "process_peak_rss_mib_high_water": _peak_rss_mib(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "pid": os.getpid(),
        "notes": "Single process; synthetic feed; high-water RSS is process-global; cold/warm effects not controlled",
    }
