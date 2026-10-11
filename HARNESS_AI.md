# HARNESS-AI | Engineering Summary

## Problem and objective

Document-heavy workflows can combine data extraction, search, generation, tool usage, and reporting. A useful automation system must address input format differences, model uncertainty, safe handling of data, and the need for human review.

## Components observed in the project

The private development environment includes documented or code-reported elements for:

- Docker services for main/service/worker functions and Redis queuing.
- LM Studio as a current principal inference endpoint, with earlier Ollama/LangChain-based experiments retained.
- Python orchestration, document parsing/OCR, retrieval and vector-data processing modules.
- PII detection and masking code, plus security policy considerations.
- A custom LM Studio plugin with Python bridge exposing Academy workflow tools and additional **read-only file audit tools**.

**Implementation evidence is scoped:** Source-level inspection supports the existence of relevant modules and tool registrations. It does not establish system-wide production readiness, a complete security boundary, or successful end-to-end execution of every workflow.

## Verified development episode: read-only AI-assisted project inspection

**Issue.** The Qwen session originally had only Academy task submission/status/artifact tools. It could not inspect arbitrary project source files. The initial audit repeatedly selected unrelated Academy tools.

**Changes.** The local development workflow extended the LM Studio plugin's tool registry and the Python adapter with bounded, read-only code navigation and inspection functions.

**Observed validation.** The TypeScript plugin build and a Python smoke test reported PASS. After installation, the Qwen session returned the contents of `mcp_gateway/server.py` using the file-read tool and enumerated the `mcp_gateway` folder with the file-list tool. Reported code matched the inspected source. Other security guarantees remain out of scope.

**Human contribution.** Requirements for a reusable code-auditing capability, integration boundaries, tool selection, staged testing, and reviewing test outputs. AI tools assisted in preparing implementation changes and code analysis.

## Evaluating generated content

Document-generation quality control work included human review of outputs, discussion and revision of error criteria, and candidate changes to parsing, embeddings, tool routing, and prompts. The exact quantitative improvements and confusion-matrix definitions are **not published as verified measurements** in this documentation-only repository.

## Next milestones

- Verify representative end-to-end flows with reproducible test cases.
- Differentiate actual runtime entry points from retained experimental alternatives.
- Assess output quality, failure recovery, provenance, permissions, and secret handling.
- Add independently reviewable evidence only after checking confidentiality and licensing.