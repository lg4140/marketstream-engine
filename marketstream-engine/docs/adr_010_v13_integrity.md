# ADR 010 — Independent Manifest Commitment, Scoped Quality Gates and Canonical Input Digests

**Status:** Accepted for v1.3 · **Date:** 2026-10-14

## Context

A v1.2 cache hit verified product bytes against hashes held in a potentially edited Manifest, but could accept a changed Manifest and issue a new pointer checksum. Global match ratios were rounded before quality comparisons. Synthetic dates were reused for external data chart configuration. Pandas internal hashing was not an explicit long-term data identity contract.

## Decision

1. Add an independent per-artifact write-once commit seal before publishing CURRENT. Reject any v1.3 cache hit when that independent digest is missing or inconsistent.
2. Compare full matched and total row counts with Decimal thresholds immediately after as-of join. Support global and symbol/day policies independently.
3. Select external-feed chart dates from real bars when no explicit `figure_date` is supplied.
4. Add optional decimal-string → integer-minor-unit conversion for cumulative amount; explicitly retain float64 compatibility fields and reject unsafe int64/tick casts.
5. Define `canonical-rows-v1` hash with length-delimited tagged scalar representations; hash row/column order and algorithm version intentionally.
6. Make public Git path audit case-insensitive and check path components, not only string prefixes.

## Consequences

- Cached reuse performs additional local I/O checks and seal verification.
- Failed publish after rename but before seal can leave an untrusted orphan requiring manual repair.
- Hashing individual cells may cost more CPU than opaque pandas hashes; measure and document.
- Legacy schema-3 artifacts remain readable but have weaker guarantees.
- The engine still lacks trusted external audit signatures, fully exact price-tick accounting, automatic GC, online event replay, bounded-memory partitioning, and cross-host coordination.
