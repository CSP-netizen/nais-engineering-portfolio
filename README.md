# HARNESS-AI

**Local AI Orchestration & Evidence-Grounded Workflow Automation**

Python · Docker · LM Studio · MCP · Knowledge Retrieval · Validation

HARNESS-AI is an engineering project to connect local/hybrid language-model inference with document workflows, source-traceable knowledge, controlled tool execution, and human review. It is designed around a practical question: **how can automated outputs remain inspectable and testable before they are used in real work?**

## Engineering areas

| Focus | Selected implementation |
| --- | --- |
| Local AI and tool integration | LM Studio plugin, Qwen, Python bridge, bounded read-only source inspection |
| Workflow orchestration | Python task control and state/lease-related components; Docker service and worker structure |
| Knowledge and provenance | Versioned records, SHA-256 integrity checks, retrieval and structured evidence |
| Output quality | Pre-render checks and explicit approval states |
| Data handling | PII masking and policy-related modules requiring further integrated security testing |

## Demonstrated integration: model-to-tool source inspection

A locally hosted Qwen session successfully invoked `audit_list_files` and `audit_read_file` through an LM Studio plugin and Python bridge. The model listed `mcp_gateway/` and read `mcp_gateway/server.py`, returning source content consistent with the inspected file. The plugin build and a Python smoke check were also reported as passing.

Two additional source-audit tools, `audit_search_code` and `audit_file_info`, were registered; their presence does not by itself imply independent functional validation of each execution path.

## Selected evaluation observations

- 480 **related synthetic test cases**, organized as 12 types × 40 runs. These were not 480 independent production documents.
- 15 **focused component tests** reportedly passed in a later isolated retest (6 Knowledge IR; 9 workflow).
- No production-ready end-to-end release, generalization accuracy, or measured productivity improvement is claimed.

## Documentation

- [System & implementation](HARNESS_AI.md)
- [Architecture & design rationale](ARCHITECTURE_AND_DECISIONS.md)
- [Evidence & verification scope](EVIDENCE_AND_LIMITATIONS.md)
- [Security & publication scope](SECURITY_AND_SCOPE.md)

## Engineering approach

Requirements definition, architecture trade-offs, integration, debugging, and acceptance criteria were human-directed. AI coding tools assisted with parts of implementation and analysis. Earlier Ollama/LangChain experiments are retained as future architectural options alongside the current LM Studio-oriented development workflow.

The underlying project remains in development. Wider source publication is contingent on a separate review.

<!-- HARNESS-AI-AUTOPUBLISH-START -->

## Selected Source Evidence

The [implementation evidence and SHA-256 inventory](AUDIT_AND_EVIDENCE.md) includes
allowlisted source snapshots and test implementations. Static inspection does not
mean E2E validation or production-readiness.

<!-- HARNESS-AI-AUTOPUBLISH-END -->

## Latest engineering recovery — 2026-10-11

[Recovery, actual call paths and limitations](ENGINEERING_RECOVERY.md): 78 Python tests passed (1 optional skip), TypeScript build and 4 tests passed, real local embedding/vector retrieval and isolated Redis/RQ execution checked. Academy E2E remains blocked by content validation; no production deployment or approved educational PDF is claimed. [Structured results](evidence/recovery_validation_20261011.json).
