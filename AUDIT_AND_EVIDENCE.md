# Selected implementation evidence

This snapshot preserves the existing seven selected modules/tests and adds the recovery regression test. Source revisions and separate original/published SHA-256 hashes are in [the manifest](evidence/selection_manifest.json). Files are copied from the reviewed development commit, not an unverified generated replacement.

## What was verified

- Python: **78 passed, 1 optional live test skipped**, across eight focused suites. Earlier failed MCP test runs were retained locally; the final retest used the real current SDK interface.
- TypeScript plugin: build and **4 tests passed**.
- PII: **17 labeled spans in 12 synthetic documents covered**. This is a narrow fixed fixture, not production recall or a privacy guarantee.
- Disposable Redis/RQ: real serialization/execution and success/failure registries verified with a stubbed inference response.
- Host and disposable Docker: real Nomic 768-dimensional embedding, canonical ingestion, vector retrieval, unchanged-document skip and rebuild verified.
- Docker Qwen: bounded text smoke passed. The earlier host request with unbounded output timed out after 90 seconds.
- Academy E2E: **blocked after retrieval and generation by content validation**. No approved PDF or vision-QA completion claimed.

See [engineering recovery](ENGINEERING_RECOVERY.md) and [machine-readable results](evidence/recovery_validation_20261011.json).

## Publication boundary

Selected snippets are evidence, **not a standalone runnable package**. Private configuration, credentials, original corpora and raw runtime logs are excluded. Tests require the complete private project and its dependencies; commands identify the original verification context. Whitespace normalization is AST-equivalent for Python samples. Hashes prove snapshot identity, not correctness.

Credential-pattern and configured-secret scans are limited checks, not security certification. Existing third-party notices are preserved; this repository does not grant blanket rights to dependencies or source datasets.
