"""Seeded, vectorized synthetic five-level order-book and trade generator.

Designed to preserve the original portfolio project's 3-second snapshots and
15-second trade cadence. This is *not* a market simulator or real feed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def generate_synthetic_market_data(
    n_stocks: int = 3,
    dates: list[str] | None = None,
    n_snapshots: int = 1200,
    seed: int = 42,
    snapshot_period_seconds: int = 3,
    trade_every_n_snapshots: int = 5,
    tick_size: float = 0.01,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate canonical snapshots and cumulative trade records for tests/demos."""
    if n_stocks < 1 or n_snapshots < 2 or snapshot_period_seconds < 1 or trade_every_n_snapshots < 1:
        raise ValueError("Invalid generator dimensions/cadence")
    if not np.isfinite(tick_size) or tick_size <= 0:
        raise ValueError("tick_size must be finite and positive")
    if (n_snapshots - 1) * snapshot_period_seconds > 6 * 3600 + 30 * 60 - 3:
        raise ValueError("Generated timestamps exceed the 09:30:03–16:00 regular session")
    dates = dates or ["20210104"]
    rng = np.random.default_rng(seed)
    snapshots, trades = [], []
    for d in dates:
        start = pd.Timestamp(f"{d[:4]}-{d[4:6]}-{d[6:]} 09:30:03")
        times = pd.date_range(start, periods=n_snapshots, freq=f"{snapshot_period_seconds}s")
        for stock in range(1, n_stocks + 1):
            # Simulated prices are generated on the configured tick grid.
            mids = (50 + stock * 20 + rng.normal(0, 0.5)
                    + np.cumsum(rng.normal(0, 0.015, n_snapshots)))
            spread_ticks = rng.integers(2, 6, size=n_snapshots)
            bid_ticks = np.floor(mids / tick_size).astype(np.int64) - spread_ticks // 2
            ask_ticks = bid_ticks + spread_ticks
            snapshot = pd.DataFrame({"symbol": str(stock), "trading_date": d,
                                     "event_time": times})
            bid_offsets = np.concatenate((np.zeros((n_snapshots, 1), dtype=np.int64),
                                          np.cumsum(rng.integers(1, 4, size=(n_snapshots, 4)), axis=1)), axis=1)
            ask_offsets = np.concatenate((np.zeros((n_snapshots, 1), dtype=np.int64),
                                          np.cumsum(rng.integers(1, 4, size=(n_snapshots, 4)), axis=1)), axis=1)
            for level in range(1, 6):
                snapshot[f"bid{level}p"] = (bid_ticks - bid_offsets[:, level-1]) * tick_size
                snapshot[f"ask{level}p"] = (ask_ticks + ask_offsets[:, level-1]) * tick_size
                snapshot[f"bid{level}q"] = rng.integers(100, 9000, size=n_snapshots)
                snapshot[f"ask{level}q"] = rng.integers(100, 9000, size=n_snapshots)
            snapshots.append(snapshot)

            trade_index = np.arange(0, n_snapshots, trade_every_n_snapshots)
            choices = rng.integers(0, 5, size=len(trade_index))
            price_pool = np.column_stack([
                snapshot["bid1p"], snapshot["bid2p"], snapshot["ask1p"],
                snapshot["ask2p"], np.rint(mids / tick_size) * tick_size,
            ])[trade_index]
            last = price_pool[np.arange(len(trade_index)), choices]
            sizes = rng.integers(100, 5000, size=len(trade_index))
            trades.append(pd.DataFrame({
                "symbol": str(stock), "trading_date": d,
                "event_time": times[trade_index],
                "cum_volume": np.cumsum(sizes, dtype=np.int64),
                "cum_amount": np.cumsum(sizes * last, dtype=np.float64),
                "last": last,
            }))
    return (
        pd.concat(snapshots, ignore_index=True).sort_values(
            ["symbol", "trading_date", "event_time"], kind="stable").reset_index(drop=True),
        pd.concat(trades, ignore_index=True).sort_values(
            ["symbol", "trading_date", "event_time"], kind="stable").reset_index(drop=True),
    )
