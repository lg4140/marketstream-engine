# Security and private source-data policy

This repository is a sanitized synthetic-data software portfolio. Never commit proprietary snapshot/trade feeds, assignment materials, personal identifiers, API credentials or company/internal documents.

## Safeguards

- `.gitignore` excludes local private inputs, output artifacts, environment files and keys; `.dockerignore` independently prevents sending those files into Docker build context.
- Dataset product names are allowlisted and cannot contain path separators; manifests check product names and hashes.
- Version directories are not written in place by the publisher and on-disk content is hashed before reuse.
- `tools/check_public_repo.py` checks currently tracked/addable risky paths in a Git working tree, but **does not scan secrets inside content or commit history**.

## Prior to public GitHub publication

1. Check `git status --short`, `git ls-files` and `.gitignore` behavior.
2. Run `python tools/check_public_repo.py` **inside the intended Git repository**.
3. Use an approved secret scanner on current tree and entire Git history.
4. Review notebooks, figures, metadata, dependency files and every ZIP member for embedded source data or secrets.
5. Validate third-party license and original-data redistribution rights.

The engine does not claim a malicious-writer-resistant trust model, OS sandboxing, exchange-grade security or full filesystem crash consistency. Security reports can be filed in the project repository using a private advisory channel if enabled.
