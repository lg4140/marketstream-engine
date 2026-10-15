from __future__ import annotations

import pandas as pd
import pytest

from marketstream.exceptions import SchemaValidationError
from marketstream.processing.validation import validate_snapshots, validate_trades


def test_valid_feed_schema(feeds):
    snapshots, trades = feeds
    assert len(snapshots) == 50
    assert set(snapshots["symbol"]) == {"1", "2"}
    assert len(trades) == 10


@pytest.mark.parametrize("field,value", [
    ("bid1p", -3), ("ask1p", 0), ("bid1q", -1), ("bid5p", 1e8),
    ("ask1p", 0.01), ("bid3q", 1.5),
])
def test_reject_invalid_books(feeds, field, value):
    s, _ = feeds
    bad = s.copy()
    if field == "bid3q":
        bad[field] = bad[field].astype(float)
    bad.loc[0, field] = value
    with pytest.raises(SchemaValidationError):
        validate_snapshots(bad)


def test_reject_duplicate_snapshot_keys(feeds):
    s, _ = feeds
    with pytest.raises(SchemaValidationError, match="duplicate"):
        validate_snapshots(pd.concat([s, s.iloc[[0]]], ignore_index=True))


def test_reject_crossed_book(feeds):
    s, _ = feeds
    s.loc[0, "ask1p"] = s.loc[0, "bid1p"]
    with pytest.raises(SchemaValidationError, match="Crossed"):
        validate_snapshots(s)


def test_reject_decreasing_trade_cumulative_amount(feeds):
    _, t = feeds
    bad = t.copy()
    ix = bad.index[bad["symbol"] == "1"][2]
    bad.loc[ix, "cum_amount"] = -1000.0
    with pytest.raises(SchemaValidationError):
        validate_trades(bad)


def test_legacy_schema_is_accepted(feeds):
    snapshots, _ = feeds
    legacy = snapshots.rename(columns={"symbol": "id", "trading_date": "date"})
    out = validate_snapshots(legacy)
    assert list(out.columns[:3]) == ["symbol", "trading_date", "event_time"]


def test_missing_time_and_bad_date_rejected(feeds):
    s, _ = feeds
    bad = s.drop(columns="event_time")
    with pytest.raises(SchemaValidationError):
        validate_snapshots(bad)
    bad = s.copy()
    bad.loc[0, "trading_date"] = "20210230"
    with pytest.raises(SchemaValidationError):
        validate_snapshots(bad)
