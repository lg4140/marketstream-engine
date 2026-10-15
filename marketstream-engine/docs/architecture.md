# Architecture — v1.3 current contract

The engine is a modular local batch Python application, not a live trade feed. The exact sequence is `ingest → normalize/validate → backward temporal align → early global/group gates → features + bars + candidate gap events → staged output → hash → independent seal → atomic pointer → pinned return → execution receipt`.

| Layer | Module | Responsibility |
|---|---|---|
| Input | `ingestion/readers.py` | Paired CSV/Parquet folders; preservable identifiers and decimal strings |
| Contract | `core/schemas.py`, `processing/validation.py` | 5-level quote constraints, count int64 bounds, optional minor-unit exactness |
| Alignment | `processing/alignment.py` | Strict backward time join, match delay report, symbol/date statistics |
| Analytics | `analytics/*`, `processing/resampling.py` | Market features, latest-known trade categories, snapshot-only candidates |
| Pipeline | `processing/pipeline.py` | Early group quality gates, source-specific chart date, version identity |
| Persistence | `storage/writers.py` | Local writer lock, immutable run directories, schema-4 independent seal, CURRENT pointer, pinned reader |
| Operations | `observability/metrics.py`, `cli.py` | Versioned canonical digest, stage timings, CLI, separated execution receipts |

The canonical digest uses a length-delimited per-cell encoding; this deliberately costs more CPU than pandas' opaque internal hashing, in exchange for a documented format. Benchmarks must include this overhead. Schema-4 receipts and seals are stored separately. The system does not guarantee distributed transactions, hostile-root tamper resistance or crash-proof durability on all filesystems.

All source time values are naive and assumed exchange-local. No timezone normalization, receiver timestamp, order sequencing, feed corrections, or automatic cross-day split is performed. Synthetic values are not real market observations.
