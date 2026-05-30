"""Plugin SDK (backlog #10) — register external capability-scoped tools from manifests.

Formalizes the tool contract into a small, declarative SDK: a YAML manifest defines a capability
(an Intent type) backed by a templated, egress-allowlisted HTTP call — NOT arbitrary shell. So a
plugin can add a real capability (e.g. trigger a Home Assistant scene) without writing Python, and
it still flows through the same validation + mode gate + audit as every built-in tool. An MCP bridge
would map MCP tools onto this same registry path — the boundary is unchanged.
"""
