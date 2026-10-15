# Data Contract — MarketStream v1.3

## Identifiers and time

Every snapshot and trade record has `symbol` (string), `trading_date` (`YYYYMMDD` string) and `event_time` (naive datetime). CSV read preserves leading-zero `symbol` and legacy `id`. Duplicate timestamp keys `(symbol, trading_date, event_time)` are rejected. Source date must agree with event_time date. No exchange DST/timezone mapping or sequence ID is implemented.

## Five-depth snapshots

Required top-of-book and depth-5 fields are `bid1p..bid5p`, `ask1p..ask5p`, `bid1q..bid5q`, `ask1q..ask5q`. Quotes must have positive finite prices, monotonic ladders, positive best spread, and nonnegative integer quantities in signed int64 bounds. Locked/crossed states are intentionally rejected. Configured tick size is checked within floating-point tolerance; tick indices at or above 2^53 are rejected because float64 cannot distinguish every adjacent integer tick. This is not a fully exact integer-tick pricing model.

## Trades and amounts

Inputs: `cum_volume` (nonnegative int64, no silent overflow), `cum_amount` (nonnegative), `last` (> 0). Cumulative values must not decrease within symbol/day. In `strict` mode amount and volume increments must agree qualitatively; exact relation to execution price is not asserted because feed semantics differ.

`amount_minor_units_per_unit` is optional and disabled by default. When set (e.g. 100 for cents per currency unit), incoming decimal strings are converted using `Decimal` **before** float coercion. Values must be integral after scaling and within signed int64; otherwise validation fails, rather than rounding. The added `cum_amount_minor` column is retained through aligned snapshot outputs. `cum_amount` remains float64 for compatibility and cannot be used for accounting-exact arithmetic. Neither prices nor all derived features are exact Decimal values. A live financial system should add venue-specific currency/contract metadata and integer price-tick models before asserting ledger accuracy.

## Temporal matching and quality

Backward as-of join preserves all snapshots, uses a finite tolerance, and rejects ambiguous duplicate trades. `trade_age_ms` is age relative to event time, **not network latency**. Alignment report includes raw `matched_rows / snapshot_rows` and `by_symbol_day` group counts. Gates use `Decimal` comparison of integer counts rather than display-rounded ratios, and run directly after alignment. Policies include `min_trade_match_rate`, optional `per_symbol_day_min_match_rate`, and `on_breach=fail|warn`. There are no per-product gates and thresholds must reflect the data source and analysis purpose.

## Chart selection

With `save_figure: true`, `figure_symbol` selects a symbol and `figure_date` either explicitly chooses a date or `null` chooses that symbol's latest actual date in the computed bars. If no matching record, `figure_missing=fail|warn` controls behavior. Synthetic generation date settings do not dictate external-feed chart dates.

## Analytic semantics

- `quoted_spread = ask1p - bid1p`; `mid_price` arithmetic midpoint.
- First-level and depth-5 liquidity imbalance reflect displayed book quantities, not investor sentiment or future returns.
- `microprice` is top-of-book quantity-weighted price.
- `last_category` describes a latest-known trade relative to a snapshot; it is not a directly observed aggressor label.
- `gap_candidates` are differences between successive five-level snapshots, not reconstructed per-order addition events.
- Interval bars keep the final complete snapshot state with separate window statistics; the last matched trade is allowed to be null.
