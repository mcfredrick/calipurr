# Calipurr contributor notes

Read `docs/brand.md` before naming anything user-facing. To use the tool rather than work on it, follow `skills/calipurr/SKILL.md`.

- Run tests with `uv run pytest`.
- Stay agent-agnostic. The CLI and plain files are the interface, so nothing may require a specific agent or MCP.
- Every pun gets a plain label or alias next to it.
- Safety messages are never puns.
- Never ship a default for a machine value. Missing values stay `needed`.
- No machine-specific assumptions in shared code. They belong in user profiles.
