---
name: calipurr
description: Look up and record the real specs of a user's 3D printers, CNC routers and laser cutters with the calipurr CLI. Use before designing a part, generating G-code or toolpaths, or preparing laser files, and whenever the user mentions a machine's limits, a part that must fit something real, a failed print, a test-cut or test-print result, or a measurement of a real object.
license: GPL-3.0-or-later
compatibility: Requires the calipurr command (Python 3.11+) and shell access.
---

# Calipurr

The user's machine profiles are the source of truth for machine limits. Every value is marked `needed`, `assumed` or `measured`.

## Before using a machine's limits

1. Run `calipurr litter --json` to see which machines exist.
2. Run `calipurr vet NAME --json` to read the values.
3. Run `calipurr hungry NAME --json`. It exits 1 if values are still needed.

## Rules

- Never invent a machine value, or copy one from another user or a typical machine. If a value you need is `needed`, ask the user for it using its `ask` text.
- Tell the user when a result depends on an `assumed` value.
- Keep safety warnings plain. Puns stop where someone could get hurt.

## Parts that must fit something real

Before designing a part that mates with a real object, or when a print or fit test comes back wrong, read [the test-fit playbook](references/test-fit.md). Prefer a small test piece that answers one question over reprinting a whole part.

## Recording values

- A value the user measured or verified: `calipurr feed NAME KEY VALUE --note "how it was measured"`
- A guess or a spec sheet number: add `--assumed`
- A new machine: `calipurr adopt NAME --kind printer|cnc|laser`

Every command has a plain alias if the user prefers it: `adopt`/`add`, `litter`/`list`, `vet`/`show`, `feed`/`set`, `hungry`/`missing`.
