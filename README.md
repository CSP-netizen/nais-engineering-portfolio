# AI Systems & Robotics | Engineering Portfolio

Selected, publicly shareable engineering documentation prepared for an application to the National Science AI Center (NAIS).

> **Disclosure:** This repository is a **curated portfolio**, not a mirror of the original development repositories. Original source code, datasets, credentials, deployment configuration, and Git history remain private. A feature mentioned in a design document is not necessarily implemented or validated.

## Projects

### 1. HARNESS-AI â€” Local/Hybrid AI Workflow System

- **Goal:** Integrate document processing, retrieval-augmented generation, inference providers, and automation tooling into a controlled workflow.
- **Architecture:** Python components, containerized runtime, local model tooling, workflow orchestration, retrieval/data processing, and an LM Studio-connected tool interface.
- **Current demonstrated capability:** A locally hosted Qwen model was able to invoke newly added read-only project file listing and reading tools through the LM Studio plugin and Python bridge. This was verified by a user-observed invocation and matching returned source text.
- **Historical technical decisions:** Earlier experiments used Ollama and LangChain. The LM Studio workflow improves interactive development and inspection; the earlier stack is retained for potential future use.
- **Status:** Development and integration in progress. Full end-to-end reliability, security properties, and performance claims are **not** asserted here.

See [HARNESS_AI.md](HARNESS_AI.md).

### 2. Sim2Real â€” Robot Simulation & Control Learning Project

- **Goal:** Develop a reproducible ROS 2 simulation and robotics evaluation pipeline as a foundation for sim-to-real research.
- **Focus:** 7-DoF robot kinematics, Gazebo simulation, controller integration, trajectory generation, evaluation, and recovery-oriented experiments.
- **Status:** Research and incremental implementation ongoing. Roadmap items are *not* represented as completed features.

See [SIM2REAL.md](SIM2REAL.md).

## Engineering methodology

Requirements and system boundaries â†’ architecture trade-offs â†’ integration â†’ execution/test evidence â†’ limitation tracking. AI coding assistants were used for implementation support and option exploration; architecture decisions, integration direction, and acceptance judgments were human-directed.

## Verification & publication boundary

- [Evidence and limitations](EVIDENCE_AND_LIMITATIONS.md)
- [Public information boundary](SECURITY_AND_SCOPE.md)
- [NAIS submission notes](SUBMISSION_GUIDE.md)

**No internal source repository or its history is published here.**