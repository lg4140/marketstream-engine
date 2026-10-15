"""Optional presentation chart, separate from analytical transformations."""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def plot_liquidity_chart(bars: pd.DataFrame, save_path: str | Path):
    frame = bars.sort_values("bar_end")
    x = frame["bar_end"]
    ask_ret = frame["ask1p"] / frame["ask1p"].iloc[0] - 1
    bid_ret = frame["bid1p"] / frame["bid1p"].iloc[0] - 1
    fig, axes = plt.subplots(2, 1, figsize=(12, 7), sharex=True,
                             gridspec_kw={"height_ratios": [2, 1]}, constrained_layout=True)
    axes[0].plot(x, bid_ret * 100, label="Best bid", lw=1.8)
    axes[0].plot(x, ask_ret * 100, label="Best ask", lw=1.8)
    axes[0].axhline(0, color="0.5", linewidth=.7, linestyle="--")
    axes[0].set_ylabel("Relative quoted price change (%)")
    axes[0].set_title(f"Best bid/ask movement and visible depth — {frame['symbol'].iloc[0]}")
    axes[0].legend(loc="best")
    axes[0].grid(alpha=.16)
    dt_width = np.timedelta64(150, "s")
    axes[1].bar(x - pd.Timedelta(seconds=75), frame["bid1q"] / 1000,
                width=dt_width, label="Best bid quantity")
    axes[1].bar(x + pd.Timedelta(seconds=75), frame["ask1q"] / 1000,
                width=dt_width, label="Best ask quantity")
    axes[1].set_ylabel("Visible quantity (thousands)")
    axes[1].set_xlabel("Interval end (local exchange time)")
    axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    axes[1].legend(loc="best")
    axes[1].grid(axis="y", alpha=.16)
    fig.savefig(save_path, dpi=175)
    return fig
