"""Orchestration (Phase 7) — multi-step goals.

Planning is ONE inference → a validated plan DAG of known capabilities (Hard Rule 2). Coordination
is deterministic code (`core/plan_executor.py`), each action step flowing through the existing
Intent→gate→executor. This package owns the plan record (models + repository); the planner and
executor live in `core/` alongside the other deterministic spine code.
"""
