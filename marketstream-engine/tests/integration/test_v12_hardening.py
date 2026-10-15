"""v1.2 regression tests: provenance, integrity, identifiers, precision and gates."""
from __future__ import annotations

import json
from unittest.mock import patch

import pandas as pd
import pytest

from marketstream.config import PipelineConfig, QualityGates
from marketstream.exceptions import SchemaValidationError, StorageError
from marketstream.ingestion.readers import read_dataset
from marketstream.ingestion.synthetic_generator import generate_synthetic_market_data
from marketstream.processing.pipeline import execute_pipeline
from marketstream.storage.writers import (
    open_published_artifact,
    publish_outputs,
    read_current_manifest,
    resolve_current,
)


def _pub(path, run_id='abc', val=1, **kwargs):
    return publish_outputs(path, {'data': pd.DataFrame({'x':[val]})},
                           {'run_id':run_id, 'stage_seconds':{}}, fmt='csv', **kwargs)


def test_publisher_returns_pinned_version_when_another_writer_wins(tmp_path):
    dest = tmp_path / 'out'
    a = _pub(dest, 'A', 1)
    _pub(dest, 'B', 2)
    assert open_published_artifact(dest).manifest['run_id'] == 'B'
    assert a.manifest['run_id'] == 'A'
    assert a.path != resolve_current(dest)
    assert pd.read_csv(a.product_path('data.csv')).iloc[0, 0] == 1


def test_pipeline_does_not_reread_mutable_current_after_commit(tmp_path):
    from marketstream.processing import pipeline
    original = pipeline.publish_outputs
    def racing(*args, **kwargs):
        own = original(*args, **kwargs)
        _pub(tmp_path / 'out', 'OTHER', 900)
        return own
    cfg = PipelineConfig(output_dir=str(tmp_path / 'out'), n_stocks=1,
                         n_snapshots=25, save_figure=False)
    with patch.object(pipeline, 'publish_outputs', side_effect=racing):
        run = execute_pipeline(cfg, 'csv')
    assert run.manifest['run_id'] != 'OTHER'
    assert read_current_manifest(cfg.output_dir)['run_id'] == 'OTHER'
    assert run.artifact_path is not None
    assert run.artifact_path.name == run.artifact_id


def test_refuse_to_reuse_tampered_product(tmp_path):
    d = tmp_path / 'pub'
    old = _pub(d)
    old.product_path('data.csv').write_text('x\n999\n', encoding='utf-8')
    pointer = (d / 'CURRENT.json').read_bytes()
    with pytest.raises(StorageError, match='checksum'):
        _pub(d)
    assert (d / 'CURRENT.json').read_bytes() == pointer


def test_refuse_to_reuse_missing_product(tmp_path):
    d = tmp_path / 'pub'
    a = _pub(d)
    a.product_path('data.csv').unlink()
    with pytest.raises(StorageError, match='missing'):
        _pub(d)


@pytest.mark.parametrize('name', ['../escape','sub/escape','./x','bad name','..','data\\escape','run_manifest','liquidity_chart','数据'])
def test_publish_rejects_unsafe_dataset_label(tmp_path, name):
    with pytest.raises(StorageError, match='(Unsafe|collides)'):
        publish_outputs(tmp_path / 'target', {name:pd.DataFrame({'x':[1]})},
                        {'run_id':'X'}, fmt='csv')
    assert not (tmp_path / 'escape.csv').exists()


def test_precision_round_trip_float64_and_minor_units(tmp_path):
    df = pd.DataFrame({'cum_amount':[1000000000.12, 0.0000000123456789],
                       'last':[12345.67890123, 1.0000000000000002],
                       'minor_units':pd.Series([123456789123, 10], dtype='int64')})
    a = publish_outputs(tmp_path/'pub', {'numbers':df}, {'run_id':'money'}, fmt='csv')
    loaded = pd.read_csv(a.product_path('numbers.csv'), float_precision='round_trip')
    assert loaded['cum_amount'].tolist() == df['cum_amount'].tolist()
    assert loaded['last'].tolist() == df['last'].tolist()
    assert loaded['minor_units'].tolist() == df['minor_units'].tolist()
    assert '1000000000.12' in a.product_path('numbers.csv').read_text()


def test_csv_reader_preserves_symbol_leading_zero(tmp_path):
    folder = tmp_path / 'input'
    folder.mkdir()
    (folder/'a.csv').write_text('symbol,trading_date,x\n000001,20210104,4\n', encoding='utf-8')
    data = read_dataset(folder)
    assert data['symbol'].iloc[0] == '000001'
    assert data['trading_date'].iloc[0] == '20210104'


def test_quality_gate_fails_on_unmatched_feed(tmp_path, monkeypatch):
    from marketstream.processing import pipeline
    s, t = generate_synthetic_market_data(n_stocks=1,n_snapshots=25)
    t['event_time'] = t['event_time'] + pd.Timedelta(hours=2)
    monkeypatch.setattr(pipeline, 'load_inputs', lambda _: (s,t))
    cfg = PipelineConfig(output_dir=str(tmp_path/'out'),n_stocks=1,n_snapshots=25,
                         save_figure=False,quality_gates=QualityGates(min_trade_match_rate=.5))
    with pytest.raises(SchemaValidationError, match='match rate'):
        execute_pipeline(cfg, 'csv')
    assert not (tmp_path/'out'/'CURRENT.json').exists()


def test_quality_gate_warns_and_includes_warning(tmp_path, monkeypatch):
    from marketstream.processing import pipeline
    s,t = generate_synthetic_market_data(n_stocks=1,n_snapshots=25)
    t['event_time'] += pd.Timedelta(hours=2)
    monkeypatch.setattr(pipeline,'load_inputs',lambda _: (s,t))
    cfg = PipelineConfig(output_dir=str(tmp_path/'out'),n_stocks=1,n_snapshots=25,
                         save_figure=False,quality_gates=QualityGates(min_trade_match_rate=.5,on_breach='warn'))
    result = execute_pipeline(cfg,'csv')
    assert result.warnings and 'Trade match rate' in result.warnings[0]
    assert result.receipt_path.is_file()
    assert json.loads(result.receipt_path.read_text())['warnings'] == result.warnings


def test_missing_chart_fails_or_warns(tmp_path):
    args = dict(output_dir=str(tmp_path/'out'),n_stocks=1,n_snapshots=25,
                save_figure=True,figure_symbol='UNKNOWN')
    with pytest.raises(SchemaValidationError, match='figure has no data'):
        execute_pipeline(PipelineConfig(**args),'csv')
    a = execute_pipeline(PipelineConfig(**args, figure_missing='warn'),'csv')
    assert any('figure' in w for w in a.warnings)
    assert 'liquidity_chart.png' not in a.files
    assert json.loads(a.receipt_path.read_text())['requested_config']['save_figure']


def test_execution_receipt_unique_on_reused_artifact(tmp_path):
    cfg = PipelineConfig(output_dir=str(tmp_path/'out'),n_stocks=1,n_snapshots=25,save_figure=False)
    a=execute_pipeline(cfg,'csv')
    b=execute_pipeline(cfg,'csv')
    assert a.artifact_id == b.artifact_id
    assert a.execution_id != b.execution_id
    assert not a.publish_reused and b.publish_reused
    assert a.receipt_path.is_file() and b.receipt_path.is_file()
    assert json.loads(b.receipt_path.read_text())['reused_artifact'] is True
    assert a.manifest == b.manifest


def test_figure_symbol_changes_artifact_identity(tmp_path):
    cfg = PipelineConfig(output_dir=str(tmp_path/'out'), n_stocks=2,n_snapshots=25,save_figure=True,figure_symbol='1')
    a = execute_pipeline(cfg,'csv')
    b = execute_pipeline(cfg.model_copy(update={'figure_symbol':'2'}),'csv')
    assert a.manifest['run_id'] == b.manifest['run_id']
    assert a.artifact_id != b.artifact_id
    assert a.artifact_path.is_dir()
    assert b.artifact_path.is_dir()


def test_pinned_reader_cannot_open_unlisted_file(tmp_path):
    a = _pub(tmp_path/'out')
    with pytest.raises(StorageError, match='not included'):
        a.product_path('../../data')


def test_dockerignore_protects_private_inputs():
    from pathlib import Path
    root=Path(__file__).resolve().parents[2]
    rules=(root/'.dockerignore').read_text()
    for path in ('data/','private_data/','secrets/','.env.*','outputs/'):
        assert path in rules


def test_two_processes_share_root_without_crossing_return_identity(tmp_path):
    """Real cross-process publication: each CLI response refers to its own run."""
    import os
    import subprocess
    import sys
    from pathlib import Path
    import yaml

    root = Path(__file__).resolve().parents[2]
    procs = []
    for seed in (101, 202):
        conf = tmp_path / f"config_{seed}.yaml"
        conf.write_text(yaml.safe_dump({"output_dir": str(tmp_path / 'pub'),
                                        "n_stocks": 1, "n_snapshots": 25,
                                        "seed": seed, "save_figure": False}),encoding='utf-8')
        env = os.environ.copy()
        env["PYTHONPATH"] = str(root / "src")
        procs.append(subprocess.Popen([sys.executable, '-m', 'marketstream.cli', 'run',
                                       '--config', str(conf), '--format','csv'],
                                      stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                      text=True,cwd=tmp_path,env=env))
    outputs=[]
    for proc in procs:
        out,err=proc.communicate(timeout=30)
        assert proc.returncode == 0,err
        outputs.append(json.loads(out))
    assert outputs[0]['run_id'] != outputs[1]['run_id']
    for item in outputs:
        path=Path(item['current_version'])
        assert path.name == item['artifact_id']
        assert json.loads((path/'run_manifest.json').read_text())['run_id'] == item['run_id']
    assert open_published_artifact(tmp_path/'pub',verify=True).artifact_id in {
        outputs[0]['artifact_id'],outputs[1]['artifact_id']}
