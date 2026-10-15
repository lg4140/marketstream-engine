"""Immutable run artifacts with atomic pointer publication (local POSIX/Windows FS).

Readers must pin CURRENT once and read only that immutable version. This is not
an object-store/distributed transaction protocol. POSIX directory fsync is best-effort.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
import json
import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

from marketstream.exceptions import StorageError


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def _sync_dir(path: Path) -> None:
    """Best-effort POSIX metadata durability; availability is FS/OS dependent."""
    if os.name != "posix":
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        fd = os.open(str(path), flags)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _write_bytes_sync(path: Path, data: bytes) -> None:
    with path.open("wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())


@contextmanager
def _writer_lock(root: Path) -> Iterator[None]:
    """Advisory cross-process lock; all cooperating writers must use this API."""
    lock = root / ".publish.lock"
    with lock.open("a+b") as file:
        if os.name == "nt":
            import msvcrt
            file.seek(0)
            file.write(b"0")
            file.flush()
            file.seek(0)
            msvcrt.locking(file.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                file.seek(0)
                msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def write_frame(df: pd.DataFrame, path: Path, fmt: str) -> None:
    if fmt == "csv":
        # pandas' default repr preserves float64 round trips better than %.10g.
        # Currency still needs venue-specific integer minor units or Decimal.
        df.to_csv(path, index=False)
    elif fmt == "parquet":
        try:
            df.to_parquet(path, index=False, engine="pyarrow", compression="zstd")
        except ImportError as exc:
            raise StorageError("Parquet requires pyarrow; install with `pip install -e .`.") from exc
    else:
        raise StorageError("format must be csv or parquet")


_SAFE_DATASET = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_HEX20 = re.compile(r"^[0-9a-f]{20}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class PublishedArtifact:
    """Pinned, verified version: no further CURRENT resolution required."""
    artifact_id: str
    path: Path
    manifest: dict[str, Any]
    files: tuple[str, ...]
    reused: bool = False

    def product_path(self, name: str) -> Path:
        if name not in self.files or name == "run_manifest.json":
            raise StorageError(f"Product not included in pinned artifact: {name}")
        return self.path / name


def _validate_name(label: str) -> str:
    if not isinstance(label, str) or not _SAFE_DATASET.fullmatch(label):
        raise StorageError("Unsafe dataset label: expected ASCII letter then letters/digits/underscore")
    if label == "run_manifest" or label == "liquidity_chart":
        raise StorageError("Dataset label collides with a reserved artifact name")
    return label


def _read_artifact(version: Path, verify: bool = True) -> PublishedArtifact:
    """Validate manifest and optionally verify *real disk bytes* of every product."""
    if not version.is_dir() or version.is_symlink():
        raise StorageError("Missing or unsafe artifact directory")
    mf = version / "run_manifest.json"
    if not mf.is_file() or mf.is_symlink():
        raise StorageError("Missing or unsafe artifact manifest")
    try:
        manifest = json.loads(mf.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise StorageError(f"Unreadable artifact manifest: {exc}") from exc
    if manifest.get("artifact_id") != version.name or not _HEX20.fullmatch(version.name):
        raise StorageError("Artifact ID and manifest identity differ")
    # v1.3 commit seals are separate, write-once records; a stored manifest
    # cannot be changed and "blessed" by merely replaying the same outputs.
    # This protects against accidental modification, not an adversary who can
    # alter the whole output root (including the seal and CURRENT).
    if manifest.get("storage_schema", 0) >= 4:
        seal_file = version.parent.parent / "commits" / f"{version.name}.json"
        if not seal_file.is_file() or seal_file.is_symlink():
            raise StorageError("Missing or unsafe committed manifest seal")
        try:
            seal = json.loads(seal_file.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise StorageError("Malformed committed manifest seal") from exc
        if (seal.get("artifact_id") != version.name
                or seal.get("manifest_sha256") != _sha256(mf)):
            raise StorageError("Committed manifest checksum mismatch")
    products = manifest.get("products")
    hashes = manifest.get("product_sha256")
    if not isinstance(products, list) or not isinstance(hashes, dict):
        raise StorageError("Malformed product manifest")
    if len(products) != len(set(products)) or set(products) != set(hashes):
        raise StorageError("Manifest products and hashes disagree")
    for name in products:
        if not isinstance(name, str) or Path(name).name != name or name in (".", ".."):
            raise StorageError("Unsafe product filename in manifest")
        expected = hashes[name]
        if not isinstance(expected, str) or not _HEX64.fullmatch(expected):
            raise StorageError("Malformed SHA-256 digest in manifest")
        file = version / name
        if not file.is_file() or file.is_symlink():
            raise StorageError(f"Product missing or unsafe: {name}")
        if verify and _sha256(file) != expected:
            raise StorageError(f"Product checksum mismatch: {name}")
    return PublishedArtifact(version.name, version, manifest,
                             tuple(sorted([*products, "run_manifest.json"])))


def open_published_artifact(destination: str | Path, verify: bool = True) -> PublishedArtifact:
    """Pin CURRENT once and return the matching manifest and files as a single unit."""
    root = Path(destination).expanduser().resolve()
    pointer = root / "CURRENT.json"
    try:
        if pointer.is_symlink():
            raise StorageError("Unsafe CURRENT symlink")
        current = json.loads(pointer.read_text(encoding="utf-8"))
        artifact_id = current["artifact_id"]
        checksum = current["manifest_sha256"]
        if (not isinstance(artifact_id, str) or not _HEX20.fullmatch(artifact_id)
                or not isinstance(checksum, str) or not _HEX64.fullmatch(checksum)):
            raise StorageError("Malformed artifact ID or checksum in CURRENT")
        version = root / "runs" / artifact_id
        if _sha256(version / "run_manifest.json") != checksum:
            raise StorageError("CURRENT manifest checksum mismatch")
        return _read_artifact(version, verify=verify)
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise StorageError(f"Cannot read CURRENT: {exc}") from exc


def resolve_current(destination: str | Path, verify: bool = False) -> Path:
    """Compatibility shim; prefer open_published_artifact() for multi-file reads."""
    return open_published_artifact(destination, verify=verify).path


def read_current_manifest(destination: str | Path, verify: bool = False) -> dict[str, Any]:
    """Compatibility shim; do not separately re-resolve CURRENT for other files."""
    return open_published_artifact(destination, verify=verify).manifest


def publish_outputs(
    destination: str | Path,
    datasets: dict[str, pd.DataFrame],
    manifest: dict[str, Any],
    fmt: str = "parquet",
    figure_callback=None,
    figure_key: str | None = None,
) -> PublishedArtifact:
    """Write a complete immutable version before atomically updating CURRENT.

    Commit visibility is atomic for cooperating readers on a single local FS.
    There is no promise of distributed/object-store transactions, exactly-once
    external side effects or universal power-loss durability.
    """
    if fmt not in ("csv", "parquet"):
        raise StorageError("Unknown output format")
    if figure_key is not None and figure_callback is None:
        raise StorageError("figure_key requires a figure_callback")
    if not datasets:
        raise StorageError("At least one dataset is required")
    for label in datasets:
        _validate_name(label)
    root = Path(destination).expanduser().resolve()
    versions = root / "runs"
    versions.mkdir(parents=True, exist_ok=True)
    commits = root / "commits"
    commits.mkdir(parents=True, exist_ok=True)
    # Include format and figure in artifact identity; run_id describes analysis.
    key = json.dumps({"run_id": manifest["run_id"], "format": fmt,
                      "figure": figure_callback is not None,
                      "figure_key": figure_key,
                      "storage_schema": 4}, sort_keys=True)
    artifact_id = hashlib.sha256(key.encode()).hexdigest()[:20]
    staged = Path(tempfile.mkdtemp(prefix=".staging-", dir=versions))
    try:
        products: list[str] = []
        for label, frame in datasets.items():
            filename = f"{label}.{fmt}"
            write_frame(frame, staged / filename, fmt)
            products.append(filename)
        if figure_callback is not None:
            figure_callback(staged / "liquidity_chart.png")
            products.append("liquidity_chart.png")
        hashes = {name: _sha256(staged / name) for name in sorted(products)}
        published = {
            **manifest,
            "storage_schema": 4,
            "artifact_id": artifact_id,
            "format": fmt,
            "products": sorted(products),
            "product_sha256": hashes,
            "publish_semantics": "immutable-runs-atomic-CURRENT-pointer",
        }
        manifest_bytes = (json.dumps(published, indent=2, sort_keys=True,
                                     ensure_ascii=False) + "\n").encode("utf-8")
        _write_bytes_sync(staged / "run_manifest.json", manifest_bytes)
        products.append("run_manifest.json")
        for file in staged.iterdir():
            if file.name != "run_manifest.json":
                with file.open("rb") as handle:
                    os.fsync(handle.fileno())
        _sync_dir(staged)
        current_bytes = (json.dumps({"artifact_id": artifact_id,
                                     "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                                     "schema": 1}, sort_keys=True) + "\n").encode("utf-8")
        with _writer_lock(root):
            target = versions / artifact_id
            reused = False
            if target.exists():
                # Before reusing, validate the actual on-disk data, not just
                # hashes copied from a possibly stale/corrupt manifest.
                existing_artifact = _read_artifact(target, verify=True)
                if existing_artifact.manifest.get("product_sha256") != hashes:
                    raise StorageError("Same artifact ID already exists with DIFFERENT contents")
                reused = True
                # The original immutable manifest remains the authority.
                existing_bytes = (target / "run_manifest.json").read_bytes()
                current_bytes = (json.dumps({"artifact_id": artifact_id,
                                             "manifest_sha256": hashlib.sha256(existing_bytes).hexdigest(),
                                             "schema": 1}, sort_keys=True) + "\n").encode("utf-8")
            else:
                staged.rename(target)
                _sync_dir(versions)
                # Write independent commit seal once, before CURRENT becomes
                # visible. If interrupted, the orphaned version is NOT reused
                # automatically; explicit operator intervention is required.
                seal_file = commits / f"{artifact_id}.json"
                seal_bytes = (json.dumps({"artifact_id": artifact_id,
                                          "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
                                          "schema": 1}, sort_keys=True) + "\n").encode("utf-8")
                with seal_file.open("xb") as seal_handle:
                    seal_handle.write(seal_bytes)
                    seal_handle.flush()
                    os.fsync(seal_handle.fileno())
                _sync_dir(commits)
            pointer_tmp = root / f".CURRENT.{os.getpid()}.{time.time_ns()}.tmp"
            try:
                _write_bytes_sync(pointer_tmp, current_bytes)
                os.replace(pointer_tmp, root / "CURRENT.json")
                _sync_dir(root)
            finally:
                pointer_tmp.unlink(missing_ok=True)
        result = _read_artifact(target, verify=True)
        return PublishedArtifact(result.artifact_id, result.path,
                                 result.manifest, result.files, reused=reused)
    except Exception as exc:
        if isinstance(exc, StorageError):
            raise
        raise StorageError(f"Could not publish outputs: {exc}") from exc
    finally:
        if staged.exists():
            shutil.rmtree(staged, ignore_errors=True)


def write_execution_receipt(destination: str | Path, receipt: dict[str, Any]) -> Path:
    """Persist an execution-specific audit record independently of cached artifacts.

    This happens *after* artifact publication. A receipt failure does not roll
    back the already committed artifact; callers must log it separately.
    """
    root = Path(destination).expanduser().resolve()
    run_id = receipt.get("execution_id")
    if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise StorageError("Invalid execution ID")
    directory = root / "executions"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run_id}.json"
    tmp = directory / f".{run_id}.{os.getpid()}.tmp"
    blob = (json.dumps(receipt, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    with _writer_lock(root):
        if path.exists():
            raise StorageError("Execution receipt already exists")
        try:
            _write_bytes_sync(tmp, blob)
            os.replace(tmp, path)
            _sync_dir(directory)
        finally:
            tmp.unlink(missing_ok=True)
    return path
