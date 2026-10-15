from __future__ import annotations

import json
import pandas as pd
import pytest

from marketstream.config import PipelineConfig, load_config
from marketstream.ingestion.readers import load_pair
from marketstream.processing.pipeline import execute_pipeline
from marketstream.storage.writers import publish_outputs, resolve_current
from marketstream.exceptions import StorageError


def test_end_to_end_and_repeatability(tmp_path):
    cfg = PipelineConfig(output_dir=str(tmp_path / "publish"), n_stocks=3,
                         n_snapshots=35, save_figure=True)
    a = execute_pipeline(cfg, output_format="csv")
    snapshot_before = pd.read_csv(resolve_current(a.destination) / "snapshot_features.csv")
    b = execute_pipeline(cfg, output_format="csv")
    snapshot_after = pd.read_csv(resolve_current(b.destination) / "snapshot_features.csv")
    assert a.manifest["run_id"] == b.manifest["run_id"]
    pd.testing.assert_frame_equal(snapshot_before, snapshot_after)
    assert (resolve_current(b.destination) / "run_manifest.json").exists()
    assert (resolve_current(b.destination) / "liquidity_chart.png").exists()
    manifest = json.loads((resolve_current(b.destination) / "run_manifest.json").read_text())
    assert manifest["alignment"]["match_rate"] == 1.0
    assert manifest["record_counts"]["features"] == 105


def test_failed_publish_preserves_previous_directory(tmp_path):
    dest = tmp_path / "committed"
    publish_outputs(dest, {"small": pd.DataFrame({"x": [1]})}, {"run_id": "old"}, "csv")
    assert (resolve_current(dest) / "small.csv").exists()
    with pytest.raises(StorageError):
        publish_outputs(dest, {"small": pd.DataFrame({"x": [5]})}, {}, "badformat")
    assert pd.read_csv(resolve_current(dest) / "small.csv")["x"].iloc[0] == 1


def test_input_csv_adapter(tmp_path, feeds):
    root = tmp_path / "raw"
    for name, frame in zip(("snapshots", "trades"), feeds):
        folder = root / name
        folder.mkdir(parents=True)
        frame.to_csv(folder / "part.csv", index=False)
    s, t = load_pair(root)
    assert len(s) == 50 and len(t) == 10
    cfg = PipelineConfig(output_dir=str(tmp_path / "out"), input_dir=str(root), save_figure=False)
    result = execute_pipeline(cfg, "csv")
    assert result.manifest["data_source"] == "local_files"


def test_parquet_when_engine_available(tmp_path):
    pytest.importorskip("pyarrow")
    cfg = PipelineConfig(output_dir=str(tmp_path / "parquet"), n_snapshots=25,
                         n_stocks=1, save_figure=False)
    result = execute_pipeline(cfg, "parquet")
    assert len(pd.read_parquet(resolve_current(result.destination) / "snapshot_features.parquet")) == 25
