from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from marketstream.cli import app
from marketstream.config import PipelineConfig, load_config
from marketstream.storage.writers import resolve_current

runner = CliRunner()


def _write_config(path: Path, dest: Path):
    path.write_text(
        "output_dir: " + str(dest) + "\n"
        "n_stocks: 1\nn_snapshots: 20\ndates: ['20210104']\n"
        "save_figure: false\n", encoding="utf-8"
    )


def test_cli_validate_and_run(tmp_path):
    c = tmp_path / "demo.yaml"
    _write_config(c, tmp_path / "run")
    v = runner.invoke(app, ["validate", "--config", str(c)])
    assert v.exit_code == 0, v.output
    assert json.loads(v.output)["snapshots"]["rows"] == 20
    result = runner.invoke(app, ["run", "--config", str(c), "--format", "csv"])
    assert result.exit_code == 0, result.output
    assert (resolve_current(tmp_path / "run") / "run_manifest.json").exists()


def test_cli_generate_and_read_back(tmp_path):
    cfg = tmp_path / "demo.yaml"
    _write_config(cfg, tmp_path / "run")
    raw = tmp_path / "raw"
    result = runner.invoke(app, ["generate", "--config", str(cfg), "--output-dir", str(raw)])
    assert result.exit_code == 0, result.output
    assert (raw / "snapshots" / "demo_snapshots.csv").exists()
    assert (raw / "trades" / "demo_trades.csv").exists()


def test_cli_benchmark():
    r = runner.invoke(app, ["benchmark", "--rows", "1000"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.output)["processed_snapshot_rows"] == 1000


def test_config_invalid_date_and_duration():
    from pydantic import ValidationError
    import pytest
    with pytest.raises(ValidationError):
        PipelineConfig(dates=["20210230"])
    with pytest.raises(ValidationError):
        PipelineConfig(join_tolerance="0s")
    with pytest.raises(ValidationError):
        PipelineConfig(on_invalid="quarantine")
