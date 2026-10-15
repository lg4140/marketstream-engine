"""Canonical DataFrame schema and input-level normalization.

Input compatibility: original project used id/date/time; canonical schema uses
symbol/trading_date/event_time and preserves five bid/ask price/quantity levels.
Exchange-local naive timestamps are used for this synthetic demonstration.
Production feeds need explicit timezone, venue, and sequence policies.
"""
from __future__ import annotations

import pandas as pd

from marketstream.exceptions import SchemaValidationError

PRICE_COLUMNS = [f"{side}{level}p" for side in ("bid", "ask") for level in range(1, 6)]
QUANTITY_COLUMNS = [f"{side}{level}q" for side in ("bid", "ask") for level in range(1, 6)]
KEY_COLUMNS = ["symbol", "trading_date", "event_time"]
SNAPSHOT_COLUMNS = KEY_COLUMNS + PRICE_COLUMNS + QUANTITY_COLUMNS
TRADE_COLUMNS = KEY_COLUMNS + ["cum_volume", "cum_amount", "last"]


def normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize legacy id/date/time records to the canonical identifier schema."""
    data = frame.copy()
    data = data.drop(columns=[c for c in data if c.startswith("Unnamed:")], errors="ignore")
    data = data.rename(columns={"id": "symbol", "date": "trading_date", "datetime": "event_time"})
    if "symbol" not in data or "trading_date" not in data:
        raise SchemaValidationError("Input requires symbol/trading_date or legacy id/date")
    if data["symbol"].isna().any() or data["trading_date"].isna().any():
        raise SchemaValidationError("Null symbol or trading_date")
    data["symbol"] = data["symbol"].astype(str)
    data["trading_date"] = data["trading_date"].astype(str)
    bad_date = pd.to_datetime(data["trading_date"], format="%Y%m%d", errors="coerce").isna()
    if bad_date.any():
        raise SchemaValidationError("Invalid trading_date; expected YYYYMMDD")
    if "event_time" not in data:
        if "time" not in data:
            raise SchemaValidationError("Input needs event_time or a time column")
        dt = data["trading_date"].str.replace(
            r"^(\d{4})(\d{2})(\d{2})$", r"\1-\2-\3", regex=True
        ) + " " + data["time"].astype(str)
        data["event_time"] = pd.to_datetime(dt, format="mixed", errors="coerce")
    else:
        data["event_time"] = pd.to_datetime(data["event_time"], errors="coerce")
    if data["event_time"].isna().any():
        raise SchemaValidationError("Invalid/null event_time")
    if data["event_time"].dt.tz is not None:
        raise SchemaValidationError("Timezone-aware input requires explicit conversion policy")
    if (data["event_time"].dt.strftime("%Y%m%d") != data["trading_date"]).any():
        raise SchemaValidationError("event_time and trading_date differ")
    return data.sort_values(KEY_COLUMNS, kind="stable").reset_index(drop=True)


def empty_canonical(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)
