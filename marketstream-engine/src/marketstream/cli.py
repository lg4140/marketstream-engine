"""User-facing CLI. Install via `pip install -e .` to get `marketstream`."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import typer

from marketstream.config import load_config
from marketstream.storage.writers import open_published_artifact
from marketstream.ingestion.synthetic_generator import generate_synthetic_market_data
from marketstream.processing.pipeline import execute_pipeline, validate_inputs

app = typer.Typer(no_args_is_help=True, help="Validated high-frequency market data engine")


def _config(path: Path | None):
    return load_config(path)


@app.command()
def run(config: Path | None = typer.Option(None, "--config", "-c"),
        format: str = typer.Option("parquet", "--format", help="Output: parquet or csv")):
    """Generate/load feeds and publish analytical data products."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    result = execute_pipeline(_config(config), output_format=format)
    typer.echo(json.dumps({"run_id": result.manifest["run_id"],
                           "output_dir": str(result.destination),
                           "alignment": result.manifest["alignment"],
                           "files": result.files,
                           "current_version": str(result.artifact_path),
                           "artifact_id": result.artifact_id,
                           "execution_id": result.execution_id,
                           "publish_reused": result.publish_reused,
                           "execution_receipt": str(result.receipt_path) if result.receipt_path else None,
                           "warnings": result.warnings}, indent=2))


@app.command()
def validate(config: Path | None = typer.Option(None, "--config", "-c")):
    """Run strict input validation without publishing outputs."""
    _, _, report = validate_inputs(_config(config))
    typer.echo(json.dumps(report, indent=2))


@app.command()
def generate(config: Path | None = typer.Option(None, "--config", "-c"),
             output_dir: Path = typer.Option(Path("sample_data/generated"), "--output-dir")):
    """Export synthetic raw CSV files, not original confidential datasets."""
    cfg = _config(config)
    snapshots, trades = generate_synthetic_market_data(
        cfg.n_stocks, cfg.dates, cfg.n_snapshots, cfg.seed,
        cfg.snapshot_period_seconds, cfg.trade_every_n_snapshots, cfg.tick_size,
    )
    for name, df in (("snapshots", snapshots), ("trades", trades)):
        folder = output_dir / name
        folder.mkdir(parents=True, exist_ok=True)
        df.to_csv(folder / f"demo_{name}.csv", index=False)
    typer.echo(f"Synthetic raw feeds written to {output_dir}")


@app.command()
def benchmark(rows: int = typer.Option(10000, "--rows", min=1000, max=1000000)):
    """Run a local synthetic benchmark (one repetition, no SLA claim)."""
    from marketstream.observability.benchmark import benchmark_rows
    typer.echo(json.dumps(benchmark_rows(rows), indent=2))


@app.command()
def init(output: Path = typer.Option(Path("marketstream.yaml"), "--output"),
         force: bool = typer.Option(False, "--force")):
    """Write a standalone demo configuration in the current directory."""
    from importlib.resources import files
    if output.exists() and not force:
        raise typer.BadParameter(f"File already exists: {output}; use --force")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(files("marketstream").joinpath("resources/demo.yaml").read_text(),
                      encoding="utf-8")
    typer.echo(str(output))


@app.command()
def current(output_dir: Path = typer.Option(Path("outputs/demo"), "--output-dir"),
            verify: bool = typer.Option(False, "--verify")):
    """Resolve current immutable version and optionally verify product checksums."""
    artifact = open_published_artifact(output_dir, verify=verify)
    typer.echo(json.dumps({"version": str(artifact.path),
                           "run_id": artifact.manifest["run_id"],
                           "artifact_id": artifact.artifact_id,
                           "verified": bool(verify)}, indent=2))


if __name__ == "__main__":
    app()
