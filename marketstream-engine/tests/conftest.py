from __future__ import annotations

import pytest

from marketstream.ingestion.synthetic_generator import generate_synthetic_market_data
from marketstream.processing.validation import validate_snapshots, validate_trades


@pytest.fixture
def feeds():
    s, t = generate_synthetic_market_data(n_stocks=2, n_snapshots=25, seed=2)
    return validate_snapshots(s), validate_trades(t)
