"""Snapshot-only *candidate* liquidity gap-fill events, in validated tick space."""
from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

EVENT_COLUMNS = ["symbol", "trading_date", "event_time", "side", "price_level",
                 "price", "quantity", "size_in_front"]


def detect_liquidity_gap_fills(
    snapshots: pd.DataFrame,
    tick_size: float = 0.01,
    tick_size_by_symbol: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    """Find newly visible levels inside previous five-level ranges (NOT orders).

    A symbol's tick scale must be correct; off-grid prices are rejected rather
    than silently rounded into the wrong level identity.
    """
    if not np.isfinite(tick_size) or tick_size <= 0:
        raise ValueError("tick_size must be positive and finite")
    base = snapshots.sort_values(["symbol", "trading_date", "event_time"]).copy()
    if base.empty:
        return pd.DataFrame(columns=EVENT_COLUMNS)
    mapping = tick_size_by_symbol or {}
    scale = base["symbol"].map(mapping).fillna(tick_size).to_numpy(dtype=float)
    if (scale <= 0).any() or not np.isfinite(scale).all():
        raise ValueError("Invalid tick-size mapping")
    records: list[pd.DataFrame] = []
    for side in ("bid", "ask"):
        levels = [f"{side}{i}p" for i in range(1, 6)]
        scaled = base[levels].to_numpy(dtype=float) / scale[:, None]
        ticks = np.rint(scaled)
        if not np.allclose(scaled, ticks, rtol=0, atol=1e-6):
            raise ValueError("Off-grid price: wrong tick_size or invalid input")
        if not np.isfinite(scaled).all() or (np.abs(ticks) >= 2**53).any():
            raise ValueError("Tick index outside exact float64 integer range")
        current = pd.DataFrame(ticks.astype("int64"), columns=levels, index=base.index)
        previous = current.groupby([base["symbol"], base["trading_date"]], sort=False).shift(1)
        prev_min = previous[levels[-1]] if side == "bid" else previous[levels[0]]
        prev_max = previous[levels[0]] if side == "bid" else previous[levels[-1]]
        for level in range(1, 6):
            tick = current[f"{side}{level}p"]
            mask = (tick.gt(prev_min) & tick.lt(prev_max)
                    & ~previous.eq(tick, axis=0).any(axis=1)
                    & base[f"{side}{level}q"].gt(0))
            if not mask.any():
                continue
            found = base.loc[mask, ["symbol", "trading_date", "event_time"]].copy()
            found["side"] = side
            found["price_level"] = level
            found["price"] = base.loc[mask, f"{side}{level}p"].to_numpy()
            found["quantity"] = base.loc[mask, f"{side}{level}q"].to_numpy()
            found["size_in_front"] = (
                0 if level == 1 else sum(
                    base.loc[mask, f"{side}{i}q"] for i in range(1, level)
                )
            )
            records.append(found)
    if not records:
        return pd.DataFrame(columns=EVENT_COLUMNS)
    return (pd.concat(records, ignore_index=True)[EVENT_COLUMNS]
            .sort_values(["symbol", "trading_date", "event_time", "side", "price_level"])
            .reset_index(drop=True))
