"""Microstructure features and trailing price statistics."""
from __future__ import annotations

import numpy as np
import pandas as pd


def add_market_features(aligned: pd.DataFrame) -> pd.DataFrame:
    df = aligned.sort_values(["symbol", "trading_date", "event_time"]).copy()
    bid = df["bid1q"].astype(float)
    ask = df["ask1q"].astype(float)
    sum_top = (bid + ask).replace(0, np.nan)
    bid5 = sum(df[f"bid{i}q"].astype(float) for i in range(1, 6))
    ask5 = sum(df[f"ask{i}q"].astype(float) for i in range(1, 6))
    sum_depth = (bid5 + ask5).replace(0, np.nan)
    df["bid_ask_imbalance"] = (bid - ask) / sum_top
    df["depth_imbalance_5"] = (bid5 - ask5) / sum_depth
    df["mid_price"] = (df["bid1p"] + df["ask1p"]) / 2
    df["quoted_spread"] = df["ask1p"] - df["bid1p"]
    df["relative_spread"] = df["quoted_spread"] / df["mid_price"]
    df["microprice"] = (df["ask1p"] * bid + df["bid1p"] * ask) / sum_top
    grouping = df.groupby(["symbol", "trading_date"], sort=False)["last"]
    df["intraday_high_last"] = grouping.cummax()
    df["intraday_low_last"] = grouping.cummin()
    # A 10-*snapshot* rolling mean of the latest known trade, not 10 trades.
    df["rolling_last_10_snapshots"] = grouping.transform(
        lambda x: x.rolling(10, min_periods=3).mean()
    )
    return df.reset_index(drop=True)


def reshape_best_bid_wide(snapshots: pd.DataFrame) -> pd.DataFrame:
    """Preserve the original notebook's bid1p unstack use case."""
    return (snapshots.pivot(index="event_time", columns="symbol", values="bid1p")
            .rename_axis(columns=None).reset_index())
