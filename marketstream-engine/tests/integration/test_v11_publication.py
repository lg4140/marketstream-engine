"""Versioned publication, reader consistency, and injected failure tests."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from typer.testing import CliRunner

from marketstream.cli import app
from marketstream.config import PipelineConfig
from marketstream.exceptions import StorageError
from marketstream.processing.pipeline import execute_pipeline
from marketstream.storage.writers import publish_outputs, read_current_manifest, resolve_current


def _publish(dest: Path, run_id: str, value: int):
    return publish_outputs(dest, {"data": pd.DataFrame({"a": [value]})},
                           {"run_id": run_id, "stage_seconds": {}}, "csv")


def test_versioned_commit_keeps_previous_reader_snapshot(tmp_path):
    dest = tmp_path / "output"
    _publish(dest, "A", 1)
    old = resolve_current(dest, verify=True)
    _publish(dest, "B", 2)
    new = resolve_current(dest, verify=True)
    assert old != new
    assert int(pd.read_csv(old / "data.csv")["a"].iloc[0]) == 1
    assert int(pd.read_csv(new / "data.csv")["a"].iloc[0]) == 2
    assert (old / "run_manifest.json").is_file()


def test_write_failure_does_not_change_pointer(tmp_path):
    dest = tmp_path / "output"
    _publish(dest, "A", 1)
    prior = (dest / "CURRENT.json").read_bytes()
    with patch("marketstream.storage.writers.write_frame", side_effect=OSError("disk-full")):
        with pytest.raises(StorageError, match="disk-full"):
            _publish(dest, "B", 2)
    assert (dest / "CURRENT.json").read_bytes() == prior
    assert pd.read_csv(resolve_current(dest) / "data.csv")["a"].iloc[0] == 1


def test_pointer_replace_failure_keeps_old_version(tmp_path):
    dest = tmp_path / "output"
    _publish(dest, "A", 1)
    old = resolve_current(dest)
    with patch("marketstream.storage.writers.os.replace", side_effect=OSError("injected")):
        with pytest.raises(StorageError, match="injected"):
            _publish(dest, "B", 2)
    assert resolve_current(dest) == old


def test_same_content_reuses_version_different_content_rejected(tmp_path):
    dest = tmp_path / "output"
    _publish(dest, "A", 1)
    original = resolve_current(dest)
    _publish(dest, "A", 1)
    assert resolve_current(dest) == original
    with pytest.raises(StorageError, match="DIFFERENT"):
        _publish(dest, "A", 3)
    assert resolve_current(dest) == original


def test_verify_rejects_tampered_product(tmp_path):
    dest = tmp_path / "output"
    _publish(dest, "A", 1)
    (resolve_current(dest) / "data.csv").write_text("malicious data", encoding="utf-8")
    with pytest.raises(StorageError, match="checksum"):
        resolve_current(dest, verify=True)


def test_run_manifest_matches_returned_manifest(tmp_path):
    cfg = PipelineConfig(output_dir=str(tmp_path / "output"), n_stocks=1,
                         n_snapshots=20, save_figure=False, trade_consistency="strict")
    result = execute_pipeline(cfg, "csv")
    assert result.manifest == read_current_manifest(result.destination, verify=True)
    assert "publish" not in result.manifest["stage_seconds"]


def test_cli_runs_from_foreign_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["validate"])
    assert result.exit_code == 0, result.output
    p = tmp_path / "demo.yaml"
    init = runner.invoke(app, ["init", "--output", str(p)])
    assert init.exit_code == 0, init.output
    assert p.is_file()
    assert runner.invoke(app, ["current", "--output-dir", "missing"]).exit_code != 0


def test_v11_cli_current_verify(tmp_path):
    output = tmp_path / "output"
    _publish(output, "A", 1)
    r = CliRunner().invoke(app, ["current", "--output-dir", str(output), "--verify"])
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout)["verified"]


def test_reader_sees_complete_version_during_concurrent_publish(tmp_path):
    import threading

    dest = tmp_path / "output"
    _publish(dest, "A", 1)
    errors: list[str] = []

    def writer():
        for number in range(2, 9):
            _publish(dest, f"run-{number}", number)

    thread = threading.Thread(target=writer, daemon=True)
    thread.start()
    while thread.is_alive():
        try:
            version = resolve_current(dest, verify=True)
            frame = pd.read_csv(version / "data.csv")
            assert len(frame) == 1
            assert frame["a"].iloc[0] >= 1
        except Exception as exc:
            errors.append(repr(exc))
            break
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert not errors


def test_current_rejects_unsafe_path_reference(tmp_path):
    dest = tmp_path / "output"
    _publish(dest, "A", 1)
    (dest / "CURRENT.json").write_text(
        json.dumps({"artifact_id": "../../bad", "manifest_sha256": "any"}),
        encoding="utf-8",
    )
    with pytest.raises(StorageError, match="Malformed"):
        resolve_current(dest)
