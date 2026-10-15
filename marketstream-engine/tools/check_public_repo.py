"""Pre-publication guard for risky tracked / addable paths (NOT a secret scanner).

Run inside a git repository. It deliberately fails if git metadata is missing;
`git check-ignore` does not protect files already tracked in Git history.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DENIED_SUFFIXES = (".pem", ".key", ".p12", ".pfx")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    test = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                          cwd=root, capture_output=True, text=True, check=False)
    if test.returncode != 0:
        print("ERROR: Git repository is required for a tracked-file audit", file=sys.stderr)
        return 2
    files = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=root, capture_output=True, check=True,
    ).stdout.decode("utf-8", errors="replace").split("\0")
    denied = []
    for name in files:
        if not name:
            continue
        normalized = name.replace("\\", "/")
        segments = normalized.lower().split("/")
        normalized_lower = normalized.casefold()
        denied_path = (any(part in {"data", "private_data", "secrets", "outputs"}
                           for part in segments)
                       or any(segments[i:i+2] == ["sample_data", "generated"]
                              for i in range(len(segments)-1)))
        if (denied_path
                or any(part.startswith(".env") and part != ".env.example" for part in segments)
                or normalized_lower.endswith(DENIED_SUFFIXES)):
            denied.append(name)
    if denied:
        print("Blocked risky Git paths:", *denied, sep="\n- ", file=sys.stderr)
        return 1
    print(f"Path audit OK: {len([x for x in files if x])} addable/tracked files checked")
    print("NOTE: also run a dedicated secret scanner and inspect Git commit history")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
