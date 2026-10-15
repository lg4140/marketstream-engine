# Storage Integrity and Reliability — v1.3

## Trust model

Single local filesystem, cooperating writers using the advisory lock, and readers that pin CURRENT once. No security against an actor with write privileges over all runs, commits and pointers. No signed manifests, distributed lock, object-store transaction, or guaranteed power-loss durability across every OS/filesystem.

## Schema-4 write protocol

1. Validate inputs, apply early quality gates; compute outputs.
2. Stage files; calculate actual product hashes; write/fsync Manifest and product bytes.
3. Acquire exclusive cooperative lock. Determine content recipe ID and artifact identity.
4. If a matching run already exists, check its independent commit seal against actual Manifest SHA-256, and verify actual product hashes; reject any damaged/seal-less version. **Never silently bless modified Manifest bytes.**
5. Otherwise rename staging to its immutable run directory and write a separate, write-once `commits/<artifact_id>.json` recording the original Manifest SHA-256. Fsync appropriately where supported.
6. Only after the commit seal exists, atomically replace CURRENT to point at that run. Return a pinned result independent of future changes to CURRENT.
7. Write the execution-specific receipt separately after publication; failure is warned and cannot roll back the existing publication.

## Legacy schema-3 migration

Previously published v1.2 schema-3 versions lack independent seals. Readers may continue to open them under *weaker* verification; schema-4 artifacts have different IDs (`storage_schema=4`). A trusted migration must explicitly reproduce and publish new artifacts. Do not retroactively create seals from modified historic Manifests without external evidence.

## Failure table

| Failure point | Expected visible CURRENT | Recovery |
|---|---|---|
| Crash while staging | Previous committed version | Inspect and remove inactive orphan staging manually |
| Crash after run rename before seal | Previous committed version | Seal-less orphan deliberately refused on retry; manual investigate/restore |
| Crash after seal before pointer | Previous committed version | Valid unreferenced version exists; operator examines orphan |
| Crash after pointer before receipt | Newly committed version | Receipt absent, explicit incomplete audit provenance |
| Product modified after publication | Read/reuse with verify=True fails | Restore from trustworthy source; do not overwrite blindly |
| Manifest modified but data unchanged | Schema-4 independent seal rejects read and reuse | Restore original manifest or rebuild through a controlled new version |
| Concurrent cooperating writers | Last pointer wins | Each caller's returned artifact remains pinned to its own version |

**Important:** schema-4 write-once is a software convention (`open(..., "xb")`) and not cryptographic immutability. A privileged actor can modify the seal and pointer. Crash recovery, orphan GC and safe human repair tools remain future work.
