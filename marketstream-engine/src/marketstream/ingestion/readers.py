"""Input adapters: paired snapshot/trade CSV or Parquet directories."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from marketstream.exceptions import SchemaValidationError


def read_dataset(folder: str | Path) -> pd.DataFrame:
    directory = Path(folder)
    if not directory.is_dir():
        raise FileNotFoundError(f"Missing dataset directory: {directory}")
    files = sorted(list(directory.rglob("*.csv")) + list(directory.rglob("*.parquet")))
    if not files:
        raise FileNotFoundError(f"No CSV/Parquet files under {directory}")
    pieces: list[pd.DataFrame] = []
    for file in files:
        try:
            pieces.append(
                pd.read_csv(file, dtype={"symbol": "string", "id": "string",
                                         "trading_date": "string", "date": "string",
                                         "cum_volume": "string", "cum_amount": "string"})
                if file.suffix == ".csv" else pd.read_parquet(file)
            )
        except Exception as exc:
            raise SchemaValidationError(f"Cannot read {file}: {exc}") from exc
    return pd.concat(pieces, ignore_index=True)


def load_pair(input_dir: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    root = Path(input_dir)
    return read_dataset(root / "snapshots"), read_dataset(root / "trades")
