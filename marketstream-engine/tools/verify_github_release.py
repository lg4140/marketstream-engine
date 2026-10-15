"""Check public release files and risky Git-staged paths (not a secret scanner)."""
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = (
    "README.md", "LICENSE", ".gitignore", ".dockerignore",
    ".github/workflows/ci.yml", ".github/workflows/security.yml",
    "src/marketstream/cli.py", "tests/integration/test_pipeline.py",
    "GITHUB_UPLOAD_GUIDE_CN.md",
)
BLOCKED = {"data", "private_data", "secrets", "outputs", "legacy_reference",
           "__pycache__", ".pytest_cache", ".venv", "dist", "build"}


def addable_paths() -> list[str]:
    """Respect .gitignore and audit Git-tracked files, not local ignored outputs."""
    probe = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=ROOT,
                           capture_output=True, text=True, check=False)
    if probe.returncode == 0:
        output = subprocess.check_output(["git", "ls-files", "--cached", "--others",
                                         "--exclude-standard", "-z"], cwd=ROOT)
        return [name for name in output.decode("utf8", errors="replace").split("\0") if name]
    # Before `git init`, ignore well-known generated folders; run the Git-based
    # audit again after initial staging and before publishing.
    result = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part.casefold() in BLOCKED for part in rel.parts):
            continue
        result.append(rel.as_posix())
    return result


def main() -> int:
    issues = [f"Missing {p}" for p in REQUIRED if not (ROOT / p).is_file()]
    for name in addable_paths():
        parts = Path(name.replace("\\", "/")).parts
        if any(part.casefold() in BLOCKED for part in parts):
            issues.append(f"Excluded Git path: {name}")
        if Path(name).suffix.casefold() in {".pem", ".key", ".p12", ".pfx"}:
            issues.append(f"Credential-like file: {name}")
    for issue in issues:
        print("ERROR:", issue, file=sys.stderr)
    print("GitHub release path checks:", "PASS" if not issues else "FAIL")
    print("CAUTION: not a content secret scanner, history audit, or CI success proof")
    return int(bool(issues))

if __name__ == "__main__":
    raise SystemExit(main())
