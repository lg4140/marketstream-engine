# Test and Benchmark Protocol — v1.3

**Executed local results** are recorded in `local_verification_v13.json` after the final run. Counts are not cumulative claims across environments.

Regression families: old v1.0–v1.2 unit/integration checks; independent Manifest seal modification and missing-seal rejection; high-precision input digest; unrounded and symbol/day quality gates; fail-fast on invalid alignment; external chart date; optional integer monetary minor unit parsing and full pipeline output; int64 overflow; public Git path audit case variants.

Run:

```bash
python -m pytest -q
python -m pytest --cov=marketstream --cov-report=term-missing
ruff check src tests benchmarks tools
mypy src/marketstream --follow-imports=silent
python benchmarks/benchmark_isolated.py --mode compute --rows 10000 --repeats 3
python benchmarks/benchmark_isolated.py --mode e2e --rows 10000 --repeats 3
```

`compute` and `e2e` benchmark modes measure synthetic data, not actual exchange ingestion or financial performance. Do not claim speedup without a same-host same-data v1.2 comparison. Large-scale partitioning and external release CI verification are outside local delivery scope. If PyArrow/Hypothesis/Ruff/Mypy/Docker are unavailable, report precisely which tests are skipped or not run.
