from __future__ import annotations

import pandas as pd
import pytest

from marketstream.processing.alignment import align_trade_snapshots, alignment_report
from marketstream.processing.validation import validate_trades
from marketstream.exceptions import SchemaValidationError


def test_backward_no_future_and_cardinality(feeds):
    s, t = feeds
    delayed = t.copy()
    delayed["event_time"] += pd.Timedelta(seconds=1)
    merged = align_trade_snapshots(s, validate_trades(delayed), "4s")
    assert len(merged) == len(s)
    assert not merged["trade_matched"].all()
    assert (merged["trade_age_ms"].dropna() >= 0).all()
    assert (merged["trade_age_ms"].dropna() <= 4000).all()
    # The first snapshot of each symbol is before the first delayed trade.
    first = merged.groupby("symbol", sort=False).head(1)
    assert first["matched_trade_time"].isna().all()


def test_partition_safety_same_time_other_symbol(feeds):
    s, t = feeds
    only_stock1 = t.loc[t["symbol"] == "1"]
    m = align_trade_snapshots(s, only_stock1, "30s")
    assert not m.loc[m["symbol"] == "2", "trade_matched"].any()
    assert m.loc[m["symbol"] == "1", "trade_matched"].any()


def test_tolerance_and_report(feeds):
    s, t = feeds
    m = align_trade_snapshots(s, t, "2s")
    assert alignment_report(m)["match_rate"] < 1.0
    assert m.loc[m["trade_matched"], "trade_age_ms"].max() <= 2000


def test_duplicate_trade_time_fail_closed(feeds):
    s, t = feeds
    duplicate = pd.concat([t, t.iloc[[0]]], ignore_index=True)
    with pytest.raises(SchemaValidationError):
        validate_trades(duplicate)
