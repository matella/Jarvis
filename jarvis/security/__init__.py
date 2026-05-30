"""Security primitives (5.5c) — secrets, egress allowlist, sanitization, untrusted framing.

Library code, no migration. These guardrails are enforced continuously by every later phase
(connectors, search, capture, conversation). The boundary invariant holds: external content can
shape a *proposal*, never bypass the gate.
"""
