"""Fail-closed, vectorized market data checks."""
from __future__ import annotations

import numpy as np
import pandas as pd
from decimal import Decimal, InvalidOperation

from marketstream.core.schemas import (KEY_COLUMNS, PRICE_COLUMNS, QUANTITY_COLUMNS,
                                       SNAPSHOT_COLUMNS, TRADE_COLUMNS, normalize_frame)
from marketstream.exceptions import SchemaValidationError


MAX_INT64 = 2**63 - 1


def _checked_int64(series: pd.Series, name: str) -> pd.Series:
    """Validate before int conversion; never silently round oversized numerics."""
    values = []
    for value in series:
        try:
            decimal = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise SchemaValidationError(f"{name} contains non-numeric values") from exc
        if not decimal.is_finite() or decimal != decimal.to_integral_value():
            raise SchemaValidationError(f"{name} must contain finite integers")
        if decimal < 0 or decimal > MAX_INT64:
            raise SchemaValidationError(f"{name} outside nonnegative int64 range")
        values.append(int(decimal))
    return pd.Series(values, index=series.index, dtype="int64")


def _amount_minor_units(series: pd.Series, units: int) -> pd.Series:
    values = []
    for value in series:
        try:
            amount = Decimal(str(value)) * Decimal(units)
        except (InvalidOperation, ValueError) as exc:
            raise SchemaValidationError("Invalid precise cumulative amount") from exc
        if (not amount.is_finite() or amount != amount.to_integral_value()
                or amount < 0 or amount > MAX_INT64):
            raise SchemaValidationError("Cumulative amount cannot be represented exactly in minor units")
        values.append(int(amount))
    return pd.Series(values, index=series.index, dtype="int64")


def _require_columns(df: pd.DataFrame, names: list[str]) -> None:
    missing = sorted(set(names) - set(df.columns))
    if missing:
        raise SchemaValidationError(f"Missing fields: {missing}")


def _validate_keys(df: pd.DataFrame) -> None:
    if df.empty:
        raise SchemaValidationError("Empty input is not a valid data feed")
    duplicates = df.duplicated(KEY_COLUMNS)
    if duplicates.any():
        example = df.loc[duplicates, KEY_COLUMNS].iloc[0].to_dict()
        raise SchemaValidationError(f"Ambiguous duplicate event key (example): {example}")


def validate_snapshots(input_df: pd.DataFrame, tick_size: float | None = None,
                       tick_size_by_symbol: dict[str, float] | None = None) -> pd.DataFrame:
    """Validate canonical 5-level LOB ordering, spread and nonnegative liquidity."""
    df = normalize_frame(input_df)
    _require_columns(df, SNAPSHOT_COLUMNS)
    _validate_keys(df)
    for col in PRICE_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in QUANTITY_COLUMNS:
        df[col] = _checked_int64(df[col], col)
    if df[PRICE_COLUMNS + QUANTITY_COLUMNS].isna().any().any():
        raise SchemaValidationError("Missing or nonnumeric LOB price/quantity")
    if not np.isfinite(df[PRICE_COLUMNS + QUANTITY_COLUMNS].to_numpy(dtype=float)).all():
        raise SchemaValidationError("Nonfinite LOB price/quantity")
    if (df[PRICE_COLUMNS] <= 0).any().any():
        raise SchemaValidationError("LOB prices must be positive")
    if (df[QUANTITY_COLUMNS] < 0).any().any():
        raise SchemaValidationError("LOB quantities must be nonnegative")
    if not (df[QUANTITY_COLUMNS] % 1 == 0).all().all():
        raise SchemaValidationError("LOB quantities must be integral")
    if (df["bid1p"] >= df["ask1p"]).any():
        raise SchemaValidationError("Crossed or locked top-of-book; unsupported feed mode")
    for level in range(1, 5):
        if (df[f"bid{level}p"] <= df[f"bid{level+1}p"]).any():
            raise SchemaValidationError("Bid prices must strictly decrease with depth")
        if (df[f"ask{level}p"] >= df[f"ask{level+1}p"]).any():
            raise SchemaValidationError("Ask prices must strictly increase with depth")
    if tick_size is not None:
        mapping = tick_size_by_symbol or {}
        scale = df["symbol"].map(mapping).fillna(tick_size).to_numpy(dtype=float)
        if not np.isfinite(scale).all() or (scale <= 0).any():
            raise SchemaValidationError("Invalid asset tick size")
        prices = df[PRICE_COLUMNS].to_numpy(dtype=float)
        scaled = prices / scale[:, None]
        if not np.isfinite(scaled).all() or (abs(scaled) >= 2**53).any():
            raise SchemaValidationError("Tick index exceeds exact float64 integer range")
        if not np.allclose(scaled, np.rint(scaled), rtol=0, atol=1e-6):
            raise SchemaValidationError("Off-grid snapshot price for configured tick size")
    df[QUANTITY_COLUMNS] = df[QUANTITY_COLUMNS].astype("int64")
    return df


def validate_trades(input_df: pd.DataFrame, consistency: str = "off",
                    amount_minor_units_per_unit: int | None = None) -> pd.DataFrame:
    """Validate cumulative trade records; distinct same-time trades need a sequence policy."""
    df = normalize_frame(input_df)
    _require_columns(df, TRADE_COLUMNS)
    _validate_keys(df)
    df["cum_volume"] = _checked_int64(df["cum_volume"], "cum_volume")
    # Parse optional accounting-exact integer minor units from ORIGINAL strings
    # before pandas is allowed to coerce decimal strings to float64.
    if amount_minor_units_per_unit is not None:
        if not isinstance(amount_minor_units_per_unit, int) or amount_minor_units_per_unit < 1:
            raise SchemaValidationError("Invalid amount minor-unit scale")
        df["cum_amount_minor"] = _amount_minor_units(
            df["cum_amount"], amount_minor_units_per_unit)
    for col in ("cum_amount", "last"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if df[["cum_volume", "cum_amount", "last"]].isna().any().any():
        raise SchemaValidationError("Missing or nonnumeric trade fields")
    if not np.isfinite(df[["cum_volume", "cum_amount", "last"]].to_numpy(dtype=float)).all():
        raise SchemaValidationError("Nonfinite trade fields")
    if ((df["cum_volume"] < 0) | (df["cum_amount"] < 0) | (df["last"] <= 0)).any():
        raise SchemaValidationError("Invalid cumulative volume/amount or trade price")
    for col in ("cum_volume", "cum_amount_minor" if amount_minor_units_per_unit else "cum_amount"):
        change = df.groupby(["symbol", "trading_date"], sort=False)[col].diff()
        if (change.dropna() < -1e-8).any():
            raise SchemaValidationError(f"{col} must be nondecreasing within each trading day")
    if consistency not in ("off", "strict"):
        raise SchemaValidationError("Trade consistency policy must be off or strict")
    if consistency == "strict":
        # Requires: cum_amount represents a positive notional in the same units,
        # without corrections/reset events; it does NOT assert delta A=delta V*last.
        v = df.groupby(["symbol", "trading_date"], sort=False)["cum_volume"].diff()
        amount_col = "cum_amount_minor" if amount_minor_units_per_unit else "cum_amount"
        a = df.groupby(["symbol", "trading_date"], sort=False)[amount_col].diff()
        inconsistent = ((v > 0) & (a <= 1e-8)) | ((v == 0) & (a.abs() > 1e-8))
        if inconsistent.any():
            raise SchemaValidationError("Cumulative amount/volume increments disagree")
    # cum_amount remains an analytical float64 compatibility column. When an
    # explicit scale is configured, cum_amount_minor is the accounting-exact
    # source of truth within signed int64 bounds.
    return df


def quality_report(df: pd.DataFrame) -> dict:
    return {
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "unique_symbols": int(df["symbol"].nunique()) if "symbol" in df else None,
        "duplicate_keys": int(df.duplicated(KEY_COLUMNS).sum())
        if all(c in df for c in KEY_COLUMNS) else None,
        "null_counts": {str(k): int(v) for k, v in df.isna().sum().items()},
    }
