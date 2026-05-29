# JARVIS
# Distributed Local-First AI Operating System
## Full Architecture & Implementation Specification

Version: 1.0
Target Environment: Ubuntu Homelab Server
Primary Hardware:

* RTX 2080 Super (8GB VRAM)
* 32GB RAM
* Docker-based infrastructure

> This is the original architecture spec and long-term rationale. For the rules that must
> never bend see `CLAUDE.md`; for build order see `docs/PLAN.md`; for why specific choices
> were made (and where this spec was deliberately scoped down) see `docs/DECISIONS.md`.

---

# 1. PROJECT OVERVIEW

Jarvis is a distributed AI-native orchestration system designed to act as:

* personal operational assistant
* infrastructure intelligence layer
* contextual memory system
* AI orchestration platform
* homelab observability layer
* workflow coordinator

Jarvis is NOT:

* a single chatbot
* unrestricted AGI
* fully autonomous infrastructure controller
* emotional roleplay assistant

Jarvis SHOULD:

* reason about systems
* coordinate specialized agents
* maintain contextual memory
* understand operational state
* summarize complex events
* assist with development workflows
* provide intelligent observability
* operate locally-first

Core philosophy:

> AI-native operational intelligence built around events, state, memory, and deterministic execution.

---

# 2. PRIMARY DESIGN PRINCIPLES

## 2.1 LOCAL-FIRST

All critical infrastructure must operate locally. Cloud APIs are optional, replaceable, and
abstracted behind interfaces. Core functions must continue offline: orchestration, memory,
observability, agent execution, voice pipeline, local inference.

## 2.2 EVENT-DRIVEN ARCHITECTURE

The entire system revolves around events, state transitions, telemetry, and workflows — NOT
giant prompt histories, infinite conversational loops, or autonomous recursive agents. Every
significant action produces events.

```json
{ "event": "container_restarted", "service": "postgres", "node": "homelab-01", "timestamp": "2026-05-29T13:00:00Z" }
```

## 2.3 STATE-CENTRIC REASONING

Jarvis reasons primarily about system state, operational history, topology, workflows, and
dependencies — not only conversations. It maintains current state, historical state, state
transitions, and inferred causal relationships.

## 2.4 DETERMINISTIC EXECUTION

LLMs must NEVER directly manipulate infrastructure. LLMs reason, classify, prioritize,
summarize, plan, infer. Deterministic software executes actions, validates permissions,
enforces schemas, performs automation.

```text
LLM → Structured Intent → Execution Layer        (NOT: LLM → Raw Shell Access)
```

## 2.5 CAPABILITY-BASED SECURITY

Every component operates within scoped permissions. Agents never receive unrestricted
filesystem, shell, network, or secrets access. All tools expose capability declarations,
schemas, validation, and approval requirements.

## 2.6 MODULARITY

Jarvis is a distributed system. Components are independently replaceable, containerized,
versioned, and observable. No monolithic architecture.

---

# 3. HIGH-LEVEL SYSTEM TOPOLOGY

```text
CLIENTS (Web / Desktop / Mobile / Voice / Terminal)
        │
        ▼
API GATEWAY (auth, sessions, streaming, device registration)
        │
        ▼
JARVIS CORE (intent routing, context assembly, planning, agent coordination,
             state reasoning, memory retrieval)
        │
   ┌────┴────────────┬───────────────┐
   ▼                 ▼               ▼
 AGENTS           MEMORY          TOOL HUB
   │                                 │
   ▼                                 ▼
EXECUTION NODES (Ubuntu Server / Desktop / Laptop / Mobile)
```

---

# 4. CORE COMPONENTS

## 4.1 API GATEWAY
Authentication, websocket streaming, device sessions, request validation, rate limiting,
permissions, notification routing. Recommended: FastAPI, WebSockets, JWT auth.

## 4.2 JARVIS CORE
The orchestrator: intent parsing, context assembly, planning, task-graph generation, memory
querying, agent routing, event interpretation, operational reasoning. The core NEVER executes
raw commands, stores giant prompt histories, or directly manipulates infrastructure.

## 4.3 EVENT BUS
The nervous system. All services communicate through events. Recommended: Redis Streams
initially, NATS for future scaling. Requirements: durable streams, replay, event versioning,
filtering, subscriptions.

## 4.4 STATE STORE
Persistent operational state: active services, topology, devices, workflows, active tasks,
operational metadata. Recommended: PostgreSQL.

## 4.5 MEMORY SYSTEM
See Section 8.

## 4.6 TOOL HUB
Deterministic execution layer. Every tool is schema-defined, validated, capability-scoped,
and observable. No arbitrary tool execution.

---

# 5. INTERNAL ONTOLOGY

A unified internal object model. Core entity types: Device, Node, Service, Container,
Workflow, Task, Alert, Event, Project, Repository, Conversation, UserIntent, Skill,
Deployment, Notification.

```json
{ "entity": "service", "id": "grafana", "node": "homelab-01", "status": "healthy", "dependencies": ["prometheus", "postgres"] }
```

---

# 6. AGENT ARCHITECTURE

Agents are specialized, deterministic, stateless where possible, and task-oriented — NOT
personalities. They consume structured tasks, constrained context, and explicit goals, and
produce structured outputs, typed results, and confidence scores.

* **6.1 Executive Agent** — intent understanding, planning, orchestration, delegation, summarization.
* **6.2 Planner Agent** — creates task graphs (e.g. investigate latency → gather metrics → inspect deploy history → analyze logs → compare baselines → diagnose).
* **6.3 Coding Agent** — repositories, debugging, architecture analysis, test generation, code summarization; git + CI awareness + repo indexing; no unrestricted shell/sudo.
* **6.4 Infrastructure Agent** — containers, logs, monitoring, diagnostics, deployments; primarily investigate/summarize/recommend, not auto-modify initially.
* **6.5 Memory Agent** — semantic indexing, retrieval, summarization, ranking, context compression.
* **6.6 Research Agent** — browsing, synthesis, extraction, webpage summarization (Playwright, deterministic browser automation).

---

# 7. CONTEXT ASSEMBLY ENGINE

One of the most important subsystems. The system cannot continuously inject entire chat
histories, all memories, and all telemetry. Solution: dynamic context ranking over active
task, recent events, operational state, memory relevance, project relevance, urgency, and
temporal proximity → a compressed contextual package. This is the true intelligence layer.

---

# 8. MEMORY ARCHITECTURE

Memory is structured cognition, not chat history.

* **8.1 Working memory** — current workflow, active tasks, immediate context.
* **8.2 Episodic memory** — deployments, conversations, incidents, investigations. Recommended: Qdrant.
* **8.3 Procedural memory** — deployment playbooks, troubleshooting procedures, coding conventions.
* **8.4 Environmental memory** — topology, dependencies, node layouts, service relationships.
* **8.5 Temporal memory** — state evolution (deployment → increased latency → increased GPU utilization → OOM). Critical for causal reasoning.
* **8.6 Knowledge graph (future)** — entity relationships. Recommended: Neo4j eventually.

---

# 9. OBSERVABILITY SYSTEM

Jarvis acts as an intelligent observability layer, anomaly interpreter, and operational summarizer.

* **9.1 Data sources** — Docker events, Prometheus, Grafana, Loki, GitHub webhooks, CI pipelines, system metrics, logs, email alerts.
* **9.2 Alert correlation** — suppress duplicates, identify root causes, correlate failures, infer dependencies (14 alerts → "Docker daemon failure impacted multiple services").
* **9.3 Operational attention system** — learn which alerts matter, which patterns are normal, which events deserve interruption. Reduce attention fatigue.
* **9.4 Operational journaling** — timeline of changes, deployments, incidents, diagnostics, investigations. Critical for debugging, historical analysis, and operational memory.

---

# 10. TOOL SYSTEM

Every tool must expose a schema, validate inputs, enforce permissions, and return typed outputs.

```text
Bad:  execute_shell(command)
Good: { "tool": "docker.restart_container", "args": { "container": "nginx" } }
```

Categories: browser, filesystem, git, docker, observability, communication, automation tools.

---

# 11. EXECUTION NODES

Each device runs a lightweight node. Capabilities may include browser, notifications,
filesystem, shell, clipboard, local telemetry. Nodes expose capability manifests, health
status, and permissions.

---

# 12. CLIENT ARCHITECTURE

Clients are mostly stateless: authenticate, stream input/output, display state, expose local
capabilities. Clients do NOT contain orchestration logic, maintain global memory, or run
heavy models.

---

# 13. VOICE PIPELINE

Voice is transport: Microphone → STT → Jarvis Core → TTS → Speaker. Recommended:
Whisper.cpp, Piper, OpenWakeWord.

---

# 14. MODEL ORCHESTRATION

Use specialized local models, not one giant model.

| Task | Model Type |
| --- | --- |
| Routing | Tiny fast model |
| Main reasoning | 14B |
| Coding | Code-specialized model |
| Summaries | Lightweight model |
| Voice | Small low-latency model |

A model router dynamically selects the cheapest capable / lowest latency / most specialized
model. Critical on limited hardware.

> NOTE: the build has revised this section against real hardware — see `docs/DECISIONS.md`.
> One LLM resident at a time on an 8GB card; Qwen 3.5 9B is the warm default, Coder 7B swaps
> in for code, routing is a CPU rules+embedding classifier (not an LLM), and the "router" is
> a thin policy layer over Ollama.

---

# 15. SECURITY MODEL

Highest priority concern.

* **15.1 Rules** — never: unrestricted autonomy, shell, secrets exposure, self-modification. Always: approvals, logging, scoped permissions, auditability, reversible actions.
* **15.2 Confidence-based execution** — every proposed action includes confidence, risk, reversibility; high-risk actions require approval.

```json
{ "action": "restart_container", "confidence": 0.91, "risk": "low", "reversible": true }
```

* **15.3 Sandboxing** — Docker isolation, separate Linux users, scoped API tokens, secrets vault, network segmentation.

---

# 16. ANTI-PATTERNS

Avoid: giant monoliths, unrestricted shell agents, prompt spaghetti, fully autonomous agents,
giant memory dumps, infinite recursive planning, token-by-token browser control, uncontrolled
agent conversations.

---

# 17. IMPLEMENTATION ROADMAP

> The build re-scopes Phase 1 into a minimal spine (M0–M4) — see `docs/PLAN.md`.

* **Phase 1 — Foundation:** API gateway, event bus, orchestrator, memory layer, websocket clients, local inference, basic observability.
* **Phase 2 — Operational Intelligence:** infrastructure agent, diagnostics, alert correlation, topology awareness, operational journaling.
* **Phase 3 — Development Intelligence:** coding agent, repository indexing, CI awareness, deployment analysis.
* **Phase 4 — Distributed Execution:** execution nodes, cross-device capabilities, contextual notifications.
* **Phase 5 — Ambient Intelligence:** proactive assistance, predictive observability, adaptive attention, operational playbooks.

---

# 18. LONG-TERM VISION

Jarvis ultimately becomes an operational intelligence layer, a contextual cognitive system,
and an AI-native environment manager. The goal is NOT AGI simulation, emotional roleplay, or
unrestricted autonomy. The goal is:

> reliable contextual operational intelligence with persistent memory and distributed awareness.

Jarvis should feel aware, competent, contextual, operationally intelligent, trustworthy, and
predictable. The "alive" feeling should emerge from continuity, memory, environmental
understanding, intelligent observability, and operational reasoning — NOT from pretending to
be human.
