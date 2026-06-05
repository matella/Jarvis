# Wave 2 — Correctness discipline

Make answers trustworthy without new infra or always-on extra inferences.

## Pieces
- **Syntax validation of generated code (#24 + safe subset of #11/#12).** Parse fenced ```python /
  ```json blocks in a coding answer; if any fail to parse, re-ask the coder ONCE with the parse
  error fed back. Pure `ast.parse` / `json.loads` — no execution, no sandbox, zero risk. Bounds
  coding answers to ≤2 inferences, and only when the first was broken.
- **"Say when unsure" clause (#20).** Prompt-level instruction in the coding/plain answer templates:
  state what you're unsure about rather than guessing. Cheap, no extra call.

## Design
- `jarvis/agents/code_validation.py`: `extract_code_blocks(md)` + `validate_blocks(blocks)` (pure).
- `conversation._code_answer`: ask → validate → one corrective re-ask on syntax errors.

## Deferred (later waves)
Answer-grading critic as an extra LLM pass (#18) — gated/optional; not always-on (cost discipline).
Running the code (#11/#13) — Wave 1.2, needs a sandbox + security pass.

## Hard-rule compliance
One-shot (≤2 inferences, no loop>1); deterministic boundary untouched (parse only, no exec).
