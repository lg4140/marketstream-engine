# Security and Release Boundary — v1.3

The included path audit checks tracked and addable files in Git (including risky case variants and nested paths). It is not a full secret scanner and cannot remove sensitive information previously committed to Git history. The separate `security.yml` workflow requests Gitleaks over repository history; it is supplied as configuration only, and **has not been validated in a live GitHub repository**. Review action licensing/organization requirements, permission scopes, alerts and the full history before public release. Private/proprietary datasets never belong in this portfolio repository.

The independent commit seal prevents a *manifest-only* alteration from becoming trusted on an ordinary cache hit; it does not defend against a local actor who changes both the seal and the data/pointer. Use a signed external audit service if real adversarial authenticity is a requirement.
