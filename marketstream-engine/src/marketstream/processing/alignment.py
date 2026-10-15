"""Backward event-time as-of alignment with staleness and matching metrics."""
from __future__ import annotations

import pandas as pd

from marketstream.core.schemas import KEY_COLUMNS
from marketstream.exceptions import AlignmentError

TRADE_FIELDS = ["cum_volume", "cum_amount", "last"]


def align_trade_snapshots(
    snapshots: pd.DataFrame,
    trades: pd.DataFrame,
    tolerance: str = "30s",
) -> pd.DataFrame:
    """Keep all snapshot rows; never carry future or cross-symbol/day trades.

    Inputs must have passed validate_snapshots/validate_trades. Duplicate
    event-time trade keys are rejected instead of arbitrarily selecting a trade.
    """
    if snapshots.empty or trades.empty:
        raise AlignmentError("Both validated feeds must contain at least one row")
    try:
        max_age = pd.Timedelta(tolerance)
    except ValueError as exc:
        raise AlignmentError(f"Bad tolerance: {tolerance}") from exc
    if max_age <= pd.Timedelta(0):
        raise AlignmentError("tolerance must be positive")
    if trades.duplicated(KEY_COLUMNS).any():
        raise AlignmentError("Ambiguous duplicate trade keys; sequence policy required")
    optional_trade_fields = ["cum_amount_minor"] if "cum_amount_minor" in trades else []
    right = trades[["symbol", "trading_date", "event_time", *TRADE_FIELDS, *optional_trade_fields]].rename(
        columns={"event_time": "matched_trade_time"}
    )
    # pandas.merge_asof requires globally ordered join timestamps, even with by=.
    left_sorted = snapshots.sort_values("event_time", kind="stable").copy()
    left_sorted["_source_order"] = range(len(left_sorted))
    right_sorted = right.sort_values("matched_trade_time", kind="stable")
    merged = pd.merge_asof(
        left_sorted, right_sorted,
        left_on="event_time", right_on="matched_trade_time",
        by=["symbol", "trading_date"], tolerance=max_age,
        direction="backward", allow_exact_matches=True,
    )
    merged["trade_matched"] = merged["matched_trade_time"].notna()
    merged["trade_age_ms"] = (
        merged["event_time"] - merged["matched_trade_time"]
    ).dt.total_seconds() * 1000
    if (merged["trade_age_ms"].dropna() < 0).any():
        raise AlignmentError("Unexpected future-trade alignment")
    if len(merged) != len(snapshots):
        raise AlignmentError("Snapshot row cardinality changed")
    return merged.sort_values("_source_order").drop(columns="_source_order").reset_index(drop=True)


def alignment_report(aligned: pd.DataFrame) -> dict:
    ages = aligned["trade_age_ms"].dropna()
    count = int(aligned["trade_matched"].sum())
    total = len(aligned)
    groups = []
    for (symbol, date), frame in aligned.groupby(["symbol", "trading_date"], sort=True):
        group_count = int(frame["trade_matched"].sum())
        group_total = len(frame)
        groups.append({"symbol": str(symbol), "trading_date": str(date),
                       "matched_rows": group_count, "snapshot_rows": int(group_total),
                       "unmatched_rows": int(group_total - group_count),
                       "match_rate": group_count / group_total})
    return {
        "by_symbol_day": groups,
        "snapshot_rows": int(total),
        "matched_rows": count,
        "unmatched_rows": int(total - count),
        "match_rate": count / total if total else None,
        "trade_age_ms_p50": float(ages.quantile(.5)) if not ages.empty else None,
        "trade_age_ms_p95": float(ages.quantile(.95)) if not ages.empty else None,
        "trade_age_ms_p99": float(ages.quantile(.99)) if not ages.empty else None,
    }
