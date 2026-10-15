"""Classification of last known trade price relative to five-level quoted book."""
from __future__ import annotations

import pandas as pd


def classify_last_known_trade(df: pd.DataFrame) -> pd.DataFrame:
    """Snapshot-level quote-relative classification; *not* trade-side inference."""
    out = df.copy()
    last = out["last"]
    cat = pd.Series(pd.NA, index=out.index, dtype="Int64")
    cat.loc[(out["bid1p"] < last) & (last < out["ask1p"])] = 0
    for i in range(1, 5):
        cat.loc[(out[f"bid{i+1}p"] < last) & (last <= out[f"bid{i}p"])] = -i
        cat.loc[(out[f"ask{i}p"] <= last) & (last < out[f"ask{i+1}p"])] = i
    cat.loc[last <= out["bid5p"]] = -5
    cat.loc[last >= out["ask5p"]] = 5
    out["last_category"] = cat
    return out


def category_proportions(df: pd.DataFrame) -> pd.DataFrame:
    valid = df.dropna(subset=["last_category"])
    if valid.empty:
        return pd.DataFrame(columns=["symbol", *[str(i) for i in range(-5, 6)]])
    counts = pd.crosstab(valid["symbol"], valid["last_category"], normalize="index")
    counts = counts.reindex(columns=list(range(-5, 6)), fill_value=0)
    counts.columns = [str(x) for x in counts.columns]
    return counts.reset_index()
