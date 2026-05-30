"""Real-time search + visual capture (Phase 9).

Web RAG, local-first: a `SearchProvider` (SearXNG by default) returns results that are **untrusted
data** — sanitized, framed as data-not-instructions, and cited when the agent answers. Visual
capture screenshots a page (egress-allowlisted) into an `image` artifact for "show me X". Results
can shape an answer or a proposal; they can never bypass the gate.
"""
