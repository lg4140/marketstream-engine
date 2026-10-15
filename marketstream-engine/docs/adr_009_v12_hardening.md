# ADR-009 — Pin-and-verify immutable artifact publication (v1.2)

**Status:** Implemented in v1.2

## Context

The v1.1 pipeline published a version, then re-read the mutable CURRENT pointer to construct its return value. Concurrent writers could cause the return value to describe another invocation. An artifact cache hit compared incoming hashes only to the old manifest, without verifying the real stored files. Dataset labels were interpolated into paths without an allowlist; CSV had destructive ten-digit float formatting. These are independent correctness/safety bugs.

## Decision

- Return `PublishedArtifact` directly from `publish_outputs`, with a fixed path and validated manifest. Avoid re-resolving CURRENT for the invocation's return.
- Validate actual file content on every cache reuse. On corruption, **fail closed**; no invisible repair.
- Validate dataset labels (`^[A-Za-z][A-Za-z0-9_]{0,63}$`) and disallow reserved file stem collisions.
- Remove `float_format="%.10g"` and regression-test CSV float64 round-tripping. Future accounting uses feed-specific integer/decimal units.
- Store individual execution receipts after commit with UUID4; distinguish a cache hit from an original computation. Receipt failure does not imply a data publication rollback.
- Artifact identity includes figure selection, not merely figure existence.

## Alternatives rejected

- Re-read CURRENT after publishing: non-repeatable cross-writer result.
- Trust manifest checksums without hashing actual files: silently reuses modified bytes.
- Repair cached versions in place: breaks immutable reader contract.
- Replace all floating arithmetic with Decimal immediately: wide-impact change requiring a real feed contract, outside v1.2 scope.

## Consequences

Cache hits incur additional file reads. Storage keeps immutable versions until manually cleaned. Concurrent writers get pinned results but CURRENT is “last commit wins.” We provide no object-store guarantees or automated recovery daemon. Code and tests are in `storage/writers.py`, `processing/pipeline.py` and `tests/integration/test_v12_hardening.py`.
