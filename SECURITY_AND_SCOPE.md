# Security and Publication Scope

The HARNESS-AI work explores source provenance, PII handling, constrained tool access and explicit approval boundaries.

- The local source-inspection interface restricts paths and is designed as read-only.
- PII detection/masking and security-policy modules were identified in the project.
- Canonical record integrity checking and pre-render validation are distinct parts of the engineering design.

These are **implementation-level observations**, not certification that every possible outbound path is secure or that every workflow has passed integration testing.

This documentation repository deliberately excludes the private project's original source tree, Git history, credentials, data sets, private execution logs and customer/student data. Any subsequent public code or artifacts require specific confidentiality and licensing review.

## Recovery verification update

See [2026-10-11 recovery](ENGINEERING_RECOVERY.md) for verified changes, real execution boundaries, remaining failures and the reviewed source manifest. Earlier observations above remain historical and are not a claim of production acceptance.
