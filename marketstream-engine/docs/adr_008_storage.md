# ADR-008 — Immutable version artifacts and atomic CURRENT pointer

**Status:** Accepted for v1.1 local-batch prototype.

## Problem

Replacing a nonempty output directory in two renames can make the default path temporarily disappear and cannot guarantee a reader observes an internally consistent multi-file snapshot.

## Decision

1. Build data products in a hidden staging directory inside `<output>/runs/`.
2. Compute per-product SHA-256 and create a run manifest.
3. Flush file data and perform best-effort POSIX directory fsync.
4. Obtain an advisory interprocess writer lock on `<output>/.publish.lock`.
5. Create or reuse an immutable `runs/<artifact_id>` version.
6. Write a temporary `CURRENT.json` containing artifact ID and manifest checksum; atomically `os.replace` it with `<output>/CURRENT.json` on the same filesystem.
7. Readers call `resolve_current()` **once** and read multiple products from that one immutable directory. Hash validation can be explicitly requested via `verify=True`.

## Idempotency and identity

`run_id` depends on normalized input digests, engine version and computation configuration (excluding output location/figure flag as originally designed); `artifact_id` additionally includes output format, figure presence and storage schema. A rerun that produces identical products reuses the immutable version; a content conflict for the same `artifact_id` is rejected.

## Crash/failure behavior

Exceptions before pointer swap preserve the old published pointer. Unpublished complete versions can remain after a crash or pointer-swap failure. The program intentionally does not overwrite these versions or delete them behind active readers. Crash-orphan cleanup and retention/GC are not automated.

## Explicit limits

No universal atomic rename semantics across filesystems, no object-store transaction, no distributed consensus, no non-cooperating writer protection, no anti-tamper signatures. `fsync` is best effort; real power-loss durability requires platform-specific testing. Locked/crossed venue states and repair messages require separate domain contracts.
