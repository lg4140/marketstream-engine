from __future__ import annotations

import pytest

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings, strategies as st

from marketstream.ingestion.synthetic_generator import generate_synthetic_market_data
from marketstream.processing.validation import validate_snapshots, validate_trades
from marketstream.processing.alignment import align_trade_snapshots


@given(st.integers(min_value=1, max_value=3), st.integers(min_value=5, max_value=40),
       st.integers(min_value=0, max_value=100))
@settings(max_examples=20, deadline=None)
def test_generated_books_are_valid_and_alignment_preserves_rows(stocks, count, seed):
    s, t = generate_synthetic_market_data(stocks, ["20210104"], count, seed)
    s, t = validate_snapshots(s), validate_trades(t)
    aligned = align_trade_snapshots(s, t)
    assert len(aligned) == len(s)
    assert not aligned["trade_age_ms"].dropna().lt(0).any()
