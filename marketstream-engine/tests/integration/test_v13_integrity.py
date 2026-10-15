"""v1.3 contracts: independent seals, lossless minor units, scoped quality gates."""
from __future__ import annotations

import json
from unittest.mock import patch

import pandas as pd
import pytest

from marketstream.config import PipelineConfig, QualityGates
from marketstream.exceptions import SchemaValidationError, StorageError
from marketstream.ingestion.synthetic_generator import generate_synthetic_market_data
from marketstream.observability.metrics import DIGEST_CODEC, dataframe_digest
from marketstream.processing.pipeline import execute_pipeline
from marketstream.processing.validation import validate_snapshots, validate_trades
from marketstream.storage.writers import open_published_artifact, publish_outputs


def _pub(root):
    return publish_outputs(root, {"data": pd.DataFrame({"x": [4, 5]})},
                           {"run_id": "fixed"}, fmt="csv")


def test_modified_manifest_cannot_be_retrusted_by_republish(tmp_path):
    root = tmp_path / "out"
    original = _pub(root)
    first_pointer = (root / "CURRENT.json").read_bytes()
    mf = original.path / "run_manifest.json"
    altered = json.loads(mf.read_text())
    altered["quality"] = {"status": "FAKE-PASSED"}
    mf.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(StorageError, match="Committed manifest checksum mismatch"):
        _pub(root)
    assert (root / "CURRENT.json").read_bytes() == first_pointer
    with pytest.raises(StorageError, match="checksum"):
        open_published_artifact(root, verify=True)


def test_missing_seal_rejected_without_rewriting_current(tmp_path):
    root = tmp_path / "out"
    original = _pub(root)
    seal = root / "commits" / f"{original.artifact_id}.json"
    seal.unlink()
    pointer = (root / "CURRENT.json").read_bytes()
    with pytest.raises(StorageError, match="seal"):
        _pub(root)
    assert pointer == (root / "CURRENT.json").read_bytes()


def test_codec_reproducible_and_sensitive_to_numeric_changes():
    a = pd.DataFrame({"symbol": ["000001"], "price": [0.1],
                      "event_time": [pd.Timestamp("2021-01-04 09:30:03")]})
    b = a.copy()
    assert DIGEST_CODEC == "canonical-rows-v1"
    assert dataframe_digest(a) == dataframe_digest(b)
    b.loc[0, "price"] = 0.10000000000000002
    assert dataframe_digest(a) != dataframe_digest(b)


def test_quality_gate_uses_exact_counts_not_rounded_display(tmp_path, monkeypatch):
    from marketstream.processing import pipeline
    snapshots, trades = generate_synthetic_market_data(n_stocks=1, n_snapshots=25)
    monkeypatch.setattr(pipeline, "load_inputs", lambda _: (snapshots, trades))
    # Force one missing row; 24 / 25 < 1.0 must fail.
    trades = trades.iloc[1:].copy()
    monkeypatch.setattr(pipeline, "load_inputs", lambda _: (snapshots, trades))
    cfg = PipelineConfig(output_dir=str(tmp_path / "out"), n_stocks=1, n_snapshots=25,
                         save_figure=False,
                         quality_gates=QualityGates(min_trade_match_rate=1.0))
    with pytest.raises(SchemaValidationError, match="Trade match rate"):
        execute_pipeline(cfg, "csv")


def test_symbol_day_gate_detects_bad_group_while_global_passes(tmp_path, monkeypatch):
    from marketstream.processing import pipeline
    snapshots, trades = generate_synthetic_market_data(n_stocks=2, n_snapshots=25)
    # Different symbol with no available trade on the original snapshot timeline.
    trades.loc[trades["symbol"] == "2", "event_time"] += pd.Timedelta(hours=1)
    monkeypatch.setattr(pipeline, "load_inputs", lambda _: (snapshots, trades))
    cfg = PipelineConfig(output_dir=str(tmp_path / "out"), n_stocks=2, n_snapshots=25,
                         save_figure=False, quality_gates=QualityGates(
                             min_trade_match_rate=0.4, per_symbol_day_min_match_rate=0.9))
    with pytest.raises(SchemaValidationError, match="2/20210104"):
        execute_pipeline(cfg, "csv")
    assert not (tmp_path / "out" / "CURRENT.json").exists()


def test_early_gate_does_not_compute_features_when_failing(tmp_path, monkeypatch):
    from marketstream.processing import pipeline
    snapshots, trades = generate_synthetic_market_data(n_stocks=1, n_snapshots=25)
    trades["event_time"] += pd.Timedelta(hours=2)
    monkeypatch.setattr(pipeline, "load_inputs", lambda _: (snapshots, trades))
    cfg = PipelineConfig(output_dir=str(tmp_path / "out"), n_stocks=1, n_snapshots=25,
                         save_figure=False, quality_gates=QualityGates(min_trade_match_rate=0.9))
    with patch.object(pipeline, "add_market_features", side_effect=AssertionError("should not run")):
        with pytest.raises(SchemaValidationError, match="Trade match rate"):
            execute_pipeline(cfg, "csv")


def test_external_csv_figure_uses_actual_date_not_synthetic_dates(tmp_path):
    snapshots, trades = generate_synthetic_market_data(n_stocks=1, dates=["20261013"],
                                                        n_snapshots=25)
    source = tmp_path / "feed"
    for name, data in (("snapshots", snapshots), ("trades", trades)):
        folder = source / name
        folder.mkdir(parents=True)
        data.to_csv(folder / f"{name}.csv", index=False)
    cfg = PipelineConfig(input_dir=str(source), output_dir=str(tmp_path / "out"),
                         dates=["20210104"], save_figure=True, figure_symbol="1")
    result = execute_pipeline(cfg, "csv")
    assert "liquidity_chart.png" in result.files
    assert result.artifact_path is not None
    assert result.artifact_path.joinpath("liquidity_chart.png").is_file()


def test_decimal_minor_unit_import_survives_large_exact_strings():
    _, trades = generate_synthetic_market_data(n_stocks=1, n_snapshots=25)
    trades = trades.iloc[:2].copy()
    trades["cum_volume"] = pd.Series([1, 2], index=trades.index)
    trades["cum_amount"] = pd.Series(["1000000000.12", "1000000000.13"], index=trades.index)
    validated = validate_trades(trades, amount_minor_units_per_unit=100)
    assert validated["cum_amount_minor"].tolist() == [100000000012, 100000000013]


@pytest.mark.parametrize("column", ["cum_volume", "bid1q"])
def test_quantity_int64_overflow_rejected(column):
    snapshots, trades = generate_synthetic_market_data(n_stocks=1, n_snapshots=25)
    huge = str(2**63)
    if column == "cum_volume":
        trades[column] = trades[column].astype(object)
        trades.loc[0, column] = huge
        with pytest.raises(SchemaValidationError, match="int64 range"):
            validate_trades(trades)
    else:
        snapshots[column] = snapshots[column].astype(object)
        snapshots.loc[0, column] = huge
        with pytest.raises(SchemaValidationError, match="int64 range"):
            validate_snapshots(snapshots)


def test_amount_scale_rejects_sub_minor_value():
    _, trades = generate_synthetic_market_data(n_stocks=1, n_snapshots=25)
    trades["cum_amount"] = trades["cum_amount"].astype(object)
    trades.loc[0, "cum_amount"] = "0.001"
    with pytest.raises(SchemaValidationError, match="minor units"):
        validate_trades(trades, amount_minor_units_per_unit=100)


def test_full_pipeline_preserves_minor_units_in_output(tmp_path):
    snapshots, trades = generate_synthetic_market_data(n_stocks=1, n_snapshots=25)
    # Use a fixed, exactly representable accounting amount in CSV source.
    trades["cum_amount"] = [str(1000 + i) for i in range(len(trades))]
    source = tmp_path / "source"
    for label, frame in (("snapshots", snapshots), ("trades", trades)):
        folder = source / label
        folder.mkdir(parents=True)
        frame.to_csv(folder / "raw.csv", index=False)
    cfg = PipelineConfig(input_dir=str(source), output_dir=str(tmp_path / "output"),
                         amount_minor_units_per_unit=100, save_figure=False)
    run = execute_pipeline(cfg, "csv")
    output = pd.read_csv(run.artifact_path / "snapshot_features.csv")
    assert "cum_amount_minor" in output.columns
    assert (output["cum_amount_minor"].dropna().astype("int64") >= 100000).all()


def test_path_audit_catches_case_variants(tmp_path):
    import subprocess
    import sys
    from pathlib import Path
    import shutil
    project = Path(__file__).resolve().parents[2]
    (tmp_path / "tools").mkdir()
    shutil.copy2(project / "tools" / "check_public_repo.py", tmp_path / "tools")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "Data").mkdir()
    (tmp_path / "Data" / "private.csv").write_text("demo", encoding="utf8")
    (tmp_path / "nested" / "SECRETS").mkdir(parents=True)
    (tmp_path / "nested" / "SECRETS" / "key.txt").write_text("dummy", encoding="utf8")
    subprocess.run(["git", "add", "-f", "Data/private.csv", "nested/SECRETS/key.txt"],
                   cwd=tmp_path, check=True)
    process = subprocess.run([sys.executable, "tools/check_public_repo.py"],
                             cwd=tmp_path, capture_output=True, text=True)
    assert process.returncode == 1
    assert "Data/private.csv" in process.stderr
    assert "nested/SECRETS/key.txt" in process.stderr
