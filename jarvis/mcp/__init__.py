"""Jarvis as an MCP server — read-only/advisory tools for external MCP clients.

Exposes Jarvis's knowledge (news, homelab state, events, memory, and one-shot answers) over the
Model Context Protocol so the operator can query Jarvis from Claude Desktop or any MCP client,
reached over Tailscale. Strictly read-only: no Intent execution, no action path — the gated
`LLM → Intent → human-approve → executor` flow stays inside Jarvis (Hard Rule #1 intact).
"""
