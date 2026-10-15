# v1.3 Public Release Gate (must verify, not assume)

- [ ] Review full Git history for proprietary market data, assessment documents, secrets, personnel names and licensing conflicts.
- [ ] Run `python tools/check_public_repo.py` within a real Git clone, and a dedicated secret scanner over full history.
- [ ] Run Python 3.11 and 3.12 CI with pytest, Hypothesis, Parquet, Ruff, Mypy and wheel smoke tests; inspect job output.
- [ ] Execute Docker non-root validation and CSV smoke; inspect `.dockerignore` and build context.
- [ ] Execute malformed Manifest/seal, per-symbol day failure, minor units and external CSV figure tests.
- [ ] Ensure README benchmarks are labeled synthetic, hardware-specific, and **not** claimed as legacy baseline speedups.
- [ ] Test fresh-install demo CLI from outside repository root.
- [ ] Verify no GitHub actual pass badges or production SLA language until substantiated.
