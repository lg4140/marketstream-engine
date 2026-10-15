from __future__ import annotations

import numpy as np
import pandas as pd

from marketstream.analytics.event_detection import detect_liquidity_gap_fills, EVENT_COLUMNS
from marketstream.analytics.features import add_market_features
from marketstream.analytics.order_book import classify_last_known_trade, category_proportions
from marketstream.processing.alignment import align_trade_snapshots
from marketstream.processing.resampling import downsample_market_data


def test_features_and_bar_aggregation(feeds):
    s, t = feeds
    result = add_market_features(align_trade_snapshots(s, t))
    assert len(result) == len(s)
    assert np.allclose(result["quoted_spread"], result["ask1p"]-result["bid1p"])
    assert result["bid_ask_imbalance"].between(-1, 1).all()
    bars = downsample_market_data(result)
    assert (bars["snapshot_count"] > 0).all()
    assert (bars["max_bid1p"] >= bars["min_bid1p"]).all()
    assert bars["source_event_time"].notna().all()
    assert (bars["source_event_time"] <= bars["bar_end"]).all()


def test_last_price_classification_distribution(feeds):
    s, t = feeds
    aligned = align_trade_snapshots(s, t)
    results = classify_last_known_trade(aligned)
    assert results["last_category"].dropna().between(-5, 5).all()
    props = category_proportions(results)
    assert np.allclose(props[[str(i) for i in range(-5, 6)]].sum(axis=1), 1)


def test_event_detector_reports_candidates_not_first_snapshot(feeds):
    s, _ = feeds
    events = detect_liquidity_gap_fills(s)
    assert list(events.columns) == EVENT_COLUMNS
    if not events.empty:
        assert (events["quantity"] > 0).all()
        assert (events["size_in_front"] >= 0).all()
        for symbol in s["symbol"].unique():
            assert s.loc[s["symbol"] == symbol, "event_time"].min() not in (
                events.loc[events["symbol"] == symbol, "event_time"].tolist()
            )


def test_all_zero_best_quantities_nan_imbalance(feeds):
    s, t = feeds
    s.loc[0, "bid1q"] = 0
    s.loc[0, "ask1q"] = 0
    result = add_market_features(align_trade_snapshots(s, t))
    assert pd.isna(result.loc[0, "bid_ask_imbalance"])
