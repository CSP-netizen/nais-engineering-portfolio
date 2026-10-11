# HARNESS-AI | Engineering Work

## The problem

Document automation requires more than text generation: inputs must be understood, source records retrieved, model and tool actions coordinated, and outputs checked before a person approves them. HARNESS-AI explores an explicit workflow across these boundaries.

## Architecture and implementation

- **Inference:** `hybrid_ai/provider.py` includes a local LM Studio-compatible HTTP interface. Earlier Ollama and LangChain code was intentionally retained for possible service-oriented use.
- **Orchestration:** `control_plane/orchestrator.py` contains lease/interruption-handling logic and a task takeover path.
- **Provenance:** `ip_fabric/core.py` includes canonical-revision and digest-verification operations.
- **Retrieval:** `knowledge_ir_v1/retrieval.py` checks evidence status and structured content before downstream use.
- **Pre-render checks:** `academy_pdf_v12/pre_render.py` models quality and approval conditions for a representative document-generation workflow.

These are code-level observations, not a declaration that every integrated end-to-end path has passed.

## A completed integration episode: Qwen local source audit

**Problem:** A local Qwen session could see Academy job tools but could not inspect the project source directly.

**Engineering change:** The LM Studio plugin and Python bridge were extended with bounded read-only source-inspection tools.

**Relevant modules:** `lmstudio-monitor/src/index.ts`, `lmstudio-monitor/src/bridge.ts`, `mcp_gateway/monitor_bridge.py`, `mcp_gateway/audit_fs_tools.py`.

**Observed result:** TypeScript build PASS, Python smoke PASS, and actual model calls to list `mcp_gateway/` and read `mcp_gateway/server.py`. Previously unrelated Academy job calls were excluded from the audit session to prevent task mixing.

**Boundary:** This establishes useful tool integration, not exhaustive security, performance, or correctness under every input.

## Engineering decisions and responsibility

The work emphasizes separating an LLM response from a validated deliverable, keeping original evidence distinct from indexes, retaining alternative inference backends, and recording failure-to-fix verification. Requirements, architecture direction, risk boundaries, integration and review were led by the project owner with AI assistance during coding and analysis.

## Application scope

Educational document generation is one concrete test case for broader knowledge-intensive administrative automation. Further work includes representative end-to-end cases, holdout evaluations, source/license review, and deployment hardening.

## Recovery verification update

See [2026-10-11 recovery](ENGINEERING_RECOVERY.md) for verified changes, real execution boundaries, remaining failures and the reviewed source manifest. Earlier observations above remain historical and are not a claim of production acceptance.
