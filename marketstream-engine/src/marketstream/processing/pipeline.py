"""Orchestrator for validated, reproducible analytics; no network dependencies."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from marketstream.analytics.event_detection import detect_liquidity_gap_fills
from marketstream.analytics.features import add_market_features
from marketstream.analytics.order_book import category_proportions, classify_last_known_trade
from marketstream.config import PipelineConfig
from marketstream.ingestion.readers import load_pair
from marketstream.ingestion.synthetic_generator import generate_synthetic_market_data
from marketstream.observability.metrics import dataframe_digest, run_identity, timed_stage
from marketstream.processing.alignment import align_trade_snapshots, alignment_report
from marketstream.processing.resampling import downsample_market_data
from marketstream.processing.validation import quality_report, validate_snapshots, validate_trades
from marketstream.storage.writers import publish_outputs, write_execution_receipt

LOGGER = logging.getLogger("marketstream")


@dataclass
class PipelineResult:
    manifest: dict
    files: list[str]
    destination: Path
    artifact_id: str = ""
    artifact_path: Path | None = None
    execution_id: str = ""
    publish_reused: bool = False
    warnings: list[str] = field(default_factory=list)
    receipt_path: Path | None = None


def load_inputs(config: PipelineConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    if config.input_dir:
        return load_pair(config.input_dir)
    return generate_synthetic_market_data(
        n_stocks=config.n_stocks, dates=config.dates,
        n_snapshots=config.n_snapshots, seed=config.seed,
        snapshot_period_seconds=config.snapshot_period_seconds,
        trade_every_n_snapshots=config.trade_every_n_snapshots,
        tick_size=config.tick_size,
    )


def validate_inputs(config: PipelineConfig) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    raw_snapshots, raw_trades = load_inputs(config)
    snapshots = validate_snapshots(raw_snapshots, config.tick_size,
                                   config.tick_size_by_symbol)
    trades = validate_trades(raw_trades, config.trade_consistency,
                             config.amount_minor_units_per_unit)
    return snapshots, trades, {
        "snapshots": quality_report(snapshots),
        "trades": quality_report(trades),
    }


def execute_pipeline(config: PipelineConfig, output_format: str = "parquet") -> PipelineResult:
    """Fail-closed, deterministic analytical results; timing metrics vary by run."""
    timings: dict[str, float] = {}
    execution_id = uuid4().hex
    started_at = datetime.now(timezone.utc).isoformat()
    with timed_stage("ingest_validate", timings):
        snapshots, trades, quality = validate_inputs(config)
    with timed_stage("align", timings):
        aligned = align_trade_snapshots(snapshots, trades, config.join_tolerance)
    # Fail early: downstream expensive feature/event stages never execute on
    # rejected alignments. Compare raw counts, not rounded display statistics.
    join_stats = alignment_report(aligned)
    warnings: list[str] = []
    gate = config.quality_gates

    def enforce_rate(matched: int, total: int, minimum: float, label: str) -> None:
        from decimal import Decimal
        from marketstream.exceptions import SchemaValidationError
        observed = Decimal(matched) / Decimal(total)
        if observed < Decimal(str(minimum)):
            message = f"{label}: Trade match rate {observed:.9f} below required {minimum:.9f}"
            if gate.on_breach == "fail":
                raise SchemaValidationError(message)
            warnings.append(message)

    if gate.min_trade_match_rate is not None:
        enforce_rate(join_stats["matched_rows"], join_stats["snapshot_rows"],
                     gate.min_trade_match_rate, "global")
    if gate.per_symbol_day_min_match_rate is not None:
        for group in join_stats["by_symbol_day"]:
            enforce_rate(group["matched_rows"], group["snapshot_rows"],
                         gate.per_symbol_day_min_match_rate,
                         f"{group['symbol']}/{group['trading_date']}")
    with timed_stage("features", timings):
        features = add_market_features(aligned)
        classified = classify_last_known_trade(features)
    with timed_stage("bars", timings):
        bars = downsample_market_data(classified, config.resample_rule)
    with timed_stage("gap_detection", timings):
        events = detect_liquidity_gap_fills(snapshots, config.tick_size,
                                            config.tick_size_by_symbol)
    with timed_stage("category_summary", timings):
        proportions = category_proportions(classified)
    inputs_hash = {"snapshots": dataframe_digest(snapshots), "trades": dataframe_digest(trades)}
    output_id = run_identity(inputs_hash["snapshots"], inputs_hash["trades"],
                             config.model_dump(exclude={"output_dir", "save_figure", "figure_symbol", "figure_date", "figure_missing"}))
    manifest = {
        "run_id": output_id,
        "engine_version": "1.3.0",
        "data_source": "local_files" if config.input_dir else "synthetic_demo",
        "synthetic_data_only": not bool(config.input_dir),
        "quality": quality,
        "alignment": join_stats,
        "input_sha256": inputs_hash,
        "record_counts": {
            "features": len(classified), "bars": len(bars),
            "gap_candidates": len(events), "category_rows": len(proportions),
        },
        "stage_seconds": timings,
        # Describe calculation-affecting inputs only. Execution-specific
        # presentation requests belong to PipelineResult, not a cached artifact.
        "config": config.model_dump(exclude={"output_dir", "save_figure",
                                           "figure_symbol", "figure_date", "figure_missing"}),
        "quality_gate_warnings": list(warnings),
        "caveats": [
            "Last-category classification is snapshot-based, not trade-side inference.",
            "Gap fills are candidates from depth-5 snapshots, not reconstructed orders.",
            "Synthetic inputs do not establish market performance or throughput guarantees.",
        ],
    }

    callback = None
    if config.save_figure:
        dates_for_symbol = bars.loc[bars["symbol"] == config.figure_symbol, "trading_date"]
        selected_date = (config.figure_date if config.figure_date is not None
                         else (str(dates_for_symbol.max()) if not dates_for_symbol.empty else None))
        view = bars[(bars["symbol"] == config.figure_symbol) &
                    (bars["trading_date"] == selected_date)]
        if view.empty:
            message = ("Requested figure has no data for "
                       f"symbol={config.figure_symbol}, trading_date={selected_date}")
            if config.figure_missing == "fail":
                from marketstream.exceptions import SchemaValidationError
                raise SchemaValidationError(message)
            warnings.append(message)
        else:
            from marketstream.analytics.visualization import plot_liquidity_chart
            def save_figure(path: Path):
                fig = plot_liquidity_chart(view, path)
                import matplotlib.pyplot as plt
                plt.close(fig)
            callback = save_figure
    with timed_stage("publish", timings):
        published = publish_outputs(
            config.output_dir,
            {"snapshot_features": classified, "interval_bars": bars,
             "gap_candidates": events, "category_proportions": proportions},
            manifest, fmt=output_format, figure_callback=callback,
            figure_key=(f"{config.figure_symbol}:{selected_date}" if callback else None),
        )
    LOGGER.info("run_id=%s published=%s", output_id, config.output_dir)
    # Committed manifests contain only stages complete *before* commit; publish
    # latency is operational telemetry, intentionally not persisted in manifest.
    LOGGER.info("run_id=%s publish_elapsed_seconds=%.6f", output_id, timings["publish"])
    receipt = {
        "execution_id": execution_id,
        "run_id": output_id,
        "artifact_id": published.artifact_id,
        "artifact_path": str(published.path),
        "started_utc": started_at,
        "finished_utc": datetime.now(timezone.utc).isoformat(),
        "reused_artifact": published.reused,
        "requested_config": config.model_dump(),
        "requested_format": output_format,
        "stage_seconds": timings,
        "warnings": warnings,
        "status": "artifact_committed",
    }
    receipt_path = None
    try:
        receipt_path = write_execution_receipt(config.output_dir, receipt)
    except Exception as exc:
        # The artifact is already committed. Surface a clear warning rather
        # than claiming rollback or retroactively declaring publication failed.
        LOGGER.warning("Could not persist execution receipt: %s", exc)
        warnings.append(f"Could not persist execution receipt: {exc}")
    # Never consult mutable CURRENT again: another writer may have committed.
    # execution_id represents this invocation even when the artifact is reused.
    return PipelineResult(manifest=published.manifest, files=list(published.files),
                          destination=Path(config.output_dir),
                          artifact_id=published.artifact_id,
                          artifact_path=published.path,
                          execution_id=execution_id,
                          publish_reused=published.reused,
                          warnings=warnings,
                          receipt_path=receipt_path)
