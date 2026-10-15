"""Right-closed, right-labeled windows with *row-atomic* final snapshots.

Resampler.last() is intentionally forbidden: it selects last non-null data per column
and can construct a state that never existed at any one point in event time.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _price_change_count(prices: pd.Series) -> int:
    return int(prices.diff().iloc[1:].ne(0).sum())


def _price_cv(prices: pd.Series) -> float:
    return float(prices.std() / prices.mean()) if len(prices) > 1 and prices.mean() else float("nan")


def _realized_volatility(mid: pd.Series) -> float:
    """Within-window sqrt(sum(log(mid_t/mid_(t-1)) ** 2)), unannualized."""
    if len(mid) < 2 or mid.isna().any() or (mid <= 0).any():
        return float("nan")
    values = np.log(mid.to_numpy(dtype=float))
    return float(np.sqrt(np.square(np.diff(values)).sum()))


def downsample_market_data(df: pd.DataFrame, rule: str = "10min") -> pd.DataFrame:
    """Preserve nulls on the FINAL source row; compute independent window metrics."""
    if df.empty:
        return pd.DataFrame()
    outputs: list[pd.DataFrame] = []
    for (symbol, day), group in df.groupby(["symbol", "trading_date"], sort=True):
        frame = group.sort_values("event_time", kind="stable").set_index("event_time")
        resampler = frame.resample(rule, closed="right", label="right")
        # Map every nonempty window label to its final *position*, not to the
        # last non-null value of each column.
        indices = resampler.indices
        if not indices:
            continue
        labels = list(indices)
        last_positions = [int(indices[label][-1]) for label in labels]
        out = frame.iloc[last_positions].copy()
        out.insert(0, "source_event_time", out.index)
        out.index = pd.DatetimeIndex(labels, name="bar_end")
        out["max_bid1p"] = resampler["bid1p"].max().reindex(out.index)
        out["min_bid1p"] = resampler["bid1p"].min().reindex(out.index)
        out["bid1p_change_count"] = resampler["bid1p"].apply(_price_change_count).reindex(out.index)
        out["bid1p_cv"] = resampler["bid1p"].apply(_price_cv).reindex(out.index)
        out["realized_mid_vol"] = resampler["mid_price"].apply(_realized_volatility).reindex(out.index)
        out["snapshot_count"] = resampler.size().reindex(out.index).astype(int)
        out["symbol"] = symbol
        out["trading_date"] = day
        outputs.append(out.reset_index())
    if not outputs:
        return pd.DataFrame()
    return (pd.concat(outputs, ignore_index=True)
            .sort_values(["symbol", "trading_date", "bar_end"]).reset_index(drop=True))
