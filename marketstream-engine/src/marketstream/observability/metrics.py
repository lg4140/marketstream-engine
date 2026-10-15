"""Stage timing and documented, cross-pandas stable canonical data fingerprint."""
from __future__ import annotations

import hashlib
import json
import logging
import math
import numbers
import time
import unicodedata
from contextlib import contextmanager
from decimal import Decimal

import numpy as np
import pandas as pd

LOGGER = logging.getLogger("marketstream")
DIGEST_CODEC = "canonical-rows-v1"
ENGINE_VERSION = "1.3.0"


@contextmanager
def timed_stage(label: str, timings: dict[str, float]):
    start = time.perf_counter()
    try:
        yield
    finally:
        timings[label] = round(time.perf_counter() - start, 6)
        LOGGER.info("stage=%s elapsed_seconds=%.6f", label, timings[label])


def _field_bytes(value: object) -> bytes:
    """Canonical scalar encoding: type-tagged, length-delimited, no pandas hash ABI."""
    if value is None or value is pd.NA or value is pd.NaT:
        return b"null"
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        ts = pd.Timestamp(value)
        return b"T" + str(ts.value).encode("ascii")
    if isinstance(value, (bool, np.bool_)):
        return b"B1" if value else b"B0"
    if isinstance(value, numbers.Integral):
        return b"I" + str(int(value)).encode("ascii")
    if isinstance(value, numbers.Real):
        v = float(value)
        if math.isnan(v):
            return b"null"
        return b"F" + v.hex().encode("ascii")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("Non-finite Decimal in canonical digest")
        return b"D" + str(value.normalize()).encode("ascii")
    if isinstance(value, str):
        return b"S" + unicodedata.normalize("NFC", value).encode("utf-8")
    raise TypeError(f"Unsupported canonical digest value: {type(value).__name__}")


def _update_field(h, chunk: bytes) -> None:
    h.update(len(chunk).to_bytes(8, "big"))
    h.update(chunk)


def dataframe_digest(df: pd.DataFrame) -> str:
    """Stable for the same ordered semantic cell values and column order.

    Deliberately not invariant to row/column order. This codec is portable across
    pandas releases for supported scalar values, but changes of numeric types
    (integer vs float) are treated as meaningful schema changes.
    """
    h = hashlib.sha256()
    _update_field(h, DIGEST_CODEC.encode("ascii"))
    _update_field(h, str(len(df)).encode("ascii"))
    for col in df.columns:
        _update_field(h, _field_bytes(str(col)))
    for row in df.itertuples(index=False, name=None):
        for cell in row:
            _update_field(h, _field_bytes(cell))
    return h.hexdigest()


def run_identity(snapshot_hash: str, trade_hash: str, config: dict) -> str:
    blob = json.dumps({"snapshots": snapshot_hash, "trades": trade_hash,
                       "config": config, "digest_codec": DIGEST_CODEC,
                       "engine_version": ENGINE_VERSION}, sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]
