# Performance protocol — reproducible measurements, not marketing metrics

## Modes

- `compute`: synthetic generation, validation, join, features and event detection; **excludes** window bars and publish.
- `e2e`: synthetic generation, validation, alignment, features, bars, CSV serialization and pointer publication; the benchmark disables charts. Each repetition launches a fresh process.
- The benchmark's RSS is a **process high-water mark**, not isolated heap allocation attributable to one operation.

## Commands

```bash
python benchmarks/benchmark_isolated.py --mode compute --rows 10000 --repeats 5 --output outputs/benchmarks/compute.json
python benchmarks/benchmark_isolated.py --mode e2e --rows 10000 --repeats 5 --output outputs/benchmarks/e2e.json
```

## Required methodology for future speedup claims

1. Record CPU, RAM, OS, Python, pandas/NumPy/PyArrow versions, disk type, input sizes and seed.
2. Fix the dataset, result schema and correctness expectations across baseline and optimized implementations.
3. Run independent process repetitions; report median/p95 elapsed, throughput, RSS; include I/O separately.
4. Profile hotspots before modifying algorithms; verify output equality and invariants after each optimization.
5. Do **not** claim a speedup unless a comparable measured baseline exists. Do not extrapolate synthetic metrics to exchange throughput or financial strategy returns.

## Known scope

Current batch engine concatenates source files in memory, runs pandas groupings and has no bounded-memory partition scheduler. Streaming, distributed processing, low latency production service and real exchange feeds are not claimed. The synthetic generator is not an exchange simulator.
