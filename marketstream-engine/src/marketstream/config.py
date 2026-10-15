"""Strict, source-aware configuration; unknown keys are deployment errors."""
from __future__ import annotations

from datetime import datetime
from importlib.resources import files
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class QualityGates(BaseModel):
    """Optional join-quality policy; thresholds depend on the upstream feed."""
    model_config = ConfigDict(extra="forbid")
    min_trade_match_rate: float | None = Field(default=None, ge=0, le=1)
    per_symbol_day_min_match_rate: float | None = Field(default=None, ge=0, le=1)
    on_breach: Literal["fail", "warn"] = "fail"


class PipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_dir: str = "outputs/demo"
    input_dir: str | None = None
    n_stocks: int = Field(default=3, ge=1, le=1000)
    n_snapshots: int = Field(default=1200, ge=2, le=1_000_000)
    dates: list[str] = Field(default_factory=lambda: ["20210104"])
    seed: int = 42
    snapshot_period_seconds: int = Field(default=3, ge=1)
    trade_every_n_snapshots: int = Field(default=5, ge=1)
    join_tolerance: str = "30s"
    resample_rule: str = "10min"
    tick_size: float = Field(default=0.01, gt=0)
    tick_size_by_symbol: dict[str, float] = Field(default_factory=dict)
    trade_consistency: Literal["off", "strict"] = "off"
    amount_minor_units_per_unit: int | None = Field(default=None, ge=1, le=1_000_000_000)
    on_invalid: Literal["fail"] = "fail"
    save_figure: bool = True
    figure_symbol: str = "1"
    figure_date: str | None = None  # If omitted, latest available date for figure_symbol
    figure_missing: Literal["fail", "warn"] = "fail"
    quality_gates: QualityGates = Field(default_factory=QualityGates)

    @field_validator("figure_date")
    @classmethod
    def validate_figure_date(cls, value: str | None) -> str | None:
        if value is not None:
            if len(value) != 8 or not value.isdigit():
                raise ValueError("figure_date must be YYYYMMDD")
            datetime.strptime(value, "%Y%m%d")
        return value

    @field_validator("dates")
    @classmethod
    def validate_dates(cls, dates: list[str]) -> list[str]:
        if not dates:
            raise ValueError("dates cannot be empty")
        for item in dates:
            if len(item) != 8 or not item.isdigit():
                raise ValueError("dates must be YYYYMMDD strings")
            try:
                datetime.strptime(item, "%Y%m%d")
            except ValueError as exc:
                raise ValueError(f"Invalid trading date: {item}") from exc
        if len(set(dates)) != len(dates):
            raise ValueError("Duplicate trading dates")
        return dates

    @field_validator("tick_size", "tick_size_by_symbol")
    @classmethod
    def validate_tick_config(cls, value):
        if isinstance(value, dict):
            if not all(isinstance(k, str) and k and np.isfinite(v) and v > 0
                       for k, v in value.items()):
                raise ValueError("Symbol tick sizes must be finite and positive")
        elif not np.isfinite(value) or value <= 0:
            raise ValueError("Tick size must be finite and positive")
        return value

    @field_validator("join_tolerance", "resample_rule")
    @classmethod
    def validate_durations(cls, value: str) -> str:
        try:
            duration = pd.Timedelta(value)
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(f"Invalid fixed duration: {value}") from exc
        if pd.isna(duration) or duration <= pd.Timedelta(0):
            raise ValueError("Duration must be a positive fixed interval (not NaT)")
        if duration > pd.Timedelta(days=1):
            raise ValueError("Duration must not exceed one day")
        return value

    @model_validator(mode="after")
    def validate_synthetic_session(self):
        # Synthetic feeds represent one continuous regular session, 09:30:03..16:00.
        if self.input_dir is None:
            seconds = (self.n_snapshots - 1) * self.snapshot_period_seconds
            if seconds > 6 * 3600 + 30 * 60 - 3:
                raise ValueError(
                    "Synthetic snapshots exceed the 09:30:03–16:00:00 session; "
                    "use fewer snapshots or multiple dates"
                )
            if self.tick_size_by_symbol:
                raise ValueError("Synthetic generator uses one tick_size for all symbols")
        return self


def load_config(path: str | Path | None = None) -> PipelineConfig:
    if path is None:
        source = files("marketstream").joinpath("resources/demo.yaml")
        content = source.read_text(encoding="utf-8")
    else:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Config not found: {p}")
        content = p.read_text(encoding="utf-8")
    payload = yaml.safe_load(content)
    if not isinstance(payload, dict):
        raise ValueError("Configuration must be a YAML mapping")
    return PipelineConfig.model_validate(payload)
