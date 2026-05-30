"""Eval / replay harness (cross-cutting track B).

Replay is "log the model's I/O, not the model" (Hard Rule 5): we re-run a stored `context_ref`
through the CURRENT model/agent and diff against the originally recorded decision. Inference is
non-deterministic, so we flag *drift* (the decision changed in a way that matters — type/target),
not byte-equality. Run as a regression gate on every model/agent change.
"""
