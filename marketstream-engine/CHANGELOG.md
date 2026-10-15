# Changelog

## 1.3.0 — Integrity, Correctness & Reproducibility

- Separate schema-4 immutable Manifest commit seals, with cache-hit refusal when corrupted/missing.
- Exact-count quality decisions and optional symbol/day quality thresholds; gate before downstream work.
- Real-data figure date decoupled from synthetic dates.
- Optional exact cumulative amount minor-units field, integer overflow and unsafe tick-index guards.
- Canonical `canonical-rows-v1` input hashing; improved Git privacy-path audit.
- New v1.3 tests, refreshed active docs and explicit inherited limitations.

## 1.2.0 — Concurrency and data integrity

Pinned artifacts, verified data reuse, safe dataset labels, execution receipts, CSV reader identifier preservation, optional global quality policy, private Docker context guard.

## 1.1.0 — Correctness and reliability

First coherent-snapshot resampling, strict config handling, timestamp alignment, filesystem pointer publication, quality checks, CLI packaging.
