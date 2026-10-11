# Architecture and Engineering Decisions

## Observed source-audit path

```text
LM Studio GUI / local Qwen
        |
LM Studio plugin (tool registration)
        |
Local Python bridge
        |
Read-only source audit functions
        |
Allowed paths in HARNESS-AI project
```

This is an observed, limited tool-integration path. It is not a claim that every HARNESS-AI workflow is production-ready.

## Design rationale

**Local experimentation and future backend options.** LM Studio supports interactive development and inspecting tool calls. Earlier Ollama and LangChain implementations are retained for possible future application interfaces, rather than discarded.

**Traceable source records.** The IP Fabric component considers original revision/digest integrity separately from derived indexes. Search relevance does not automatically establish factual approval.

**Controllable workflow steps.** Task state, interruption handling and human approval serve different responsibilities. A generation result should not bypass its verification and release criteria.

**Bounded file access.** Path restrictions and read-only tooling reduce risk during model-assisted project inspection. Additional security and information-flow reviews remain necessary before broader use.

## Next engineering steps

Reproducible end-to-end tests, independently labeled evaluation, permission and provenance checks, and review of any files proposed for wider publication.
