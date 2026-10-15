"""Regression tests based on the v1.0 senior SDE code review."""
from __future__ import annotations

import pandas as pd
import pytest
from pydantic import ValidationError

from marketstream.analytics.event_detection import detect_liquidity_gap_fills
from marketstream.analytics.features import add_market_features
from marketstream.config import PipelineConfig
from marketstream.exceptions import SchemaValidationError
from marketstream.ingestion.synthetic_generator import generate_synthetic_market_data
from marketstream.processing.alignment import align_trade_snapshots
from marketstream.processing.resampling import downsample_market_data
from marketstream.processing.validation import validate_snapshots, validate_trades


def test_last_row_missing_trade_is_not_forward_filled_into_bar():
    snapshots, trades = generate_synthetic_market_data(1, ["20210104"], 10)
    s = validate_snapshots(snapshots)
    t = validate_trades(trades.iloc[:1])
    merged = align_trade_snapshots(s, t, tolerance="3s")
    state = add_market_features(merged)
    assert pd.isna(state.iloc[-1]["last"])
    bars = downsample_market_data(state, "10min")
    assert len(bars) == 1
    bar = bars.iloc[0]
    assert bar["source_event_time"] == state.iloc[-1]["event_time"]
    assert not bool(bar["trade_matched"])
    assert pd.isna(bar["last"])
    assert bar["bid1p"] == state.iloc[-1]["bid1p"]


@pytest.mark.parametrize("bad", [
    {"join_tolerence": "2s"},
    {"resample_rule": "NaT"},
    {"tick_size": float("nan")},
    {"tick_size_by_symbol": {"AAPL": -0.01}},
    {"n_snapshots": 18000},
])
def test_config_rejects_bad_values(bad):
    with pytest.raises(ValidationError):
        PipelineConfig.model_validate(bad)


def test_session_generator_rejects_cross_day():
    with pytest.raises(ValueError, match="session"):
        generate_synthetic_market_data(n_stocks=1, n_snapshots=18000)


def test_strict_cumulative_increments_detection():
    s, t = generate_synthetic_market_data(1, ["20210104"], 50)
    ix = t.index[2]
    t.loc[ix, "cum_amount"] = t.loc[ix - 1, "cum_amount"]
    with pytest.raises(SchemaValidationError, match="increments"):
        validate_trades(t, consistency="strict")


def test_half_cent_ticks_are_preserved_and_wrong_grid_rejected():
    snap, _ = generate_synthetic_market_data(1, ["20210104"], 10, tick_size=0.005)
    validate_snapshots(snap, 0.005)
    with pytest.raises(SchemaValidationError, match="Off-grid"):
        validate_snapshots(snap, 0.01)
    events = detect_liquidity_gap_fills(snap, 0.005)
    assert "price_level" in events.columns


def test_price_level_gap_fixture_on_half_cent_grid():
    snap, _ = generate_synthetic_market_data(1, ["20210104"], 2, tick_size=0.005)
    for j, p in enumerate([100.04, 100.03, 100.02, 100.01, 100.00], start=1):
        snap.loc[0, f"bid{j}p"] = p
    for j, p in enumerate([100.04, 100.03, 100.025, 100.02, 100.01], start=1):
        snap.loc[1, f"bid{j}p"] = p
    for i in [0, 1]:
        for j in range(1, 6):
            snap.loc[i, f"ask{j}p"] = 100.05 + j * 0.01
    snap = validate_snapshots(snap, 0.005)
    ev = detect_liquidity_gap_fills(snap, 0.005)
    assert ((ev["side"] == "bid") & (ev["price_level"] == 3) &
            (ev["price"].sub(100.025).abs() < 1e-8)).any()
