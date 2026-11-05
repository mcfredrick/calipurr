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

## Working on a part

Run these from the part's project folder. Read the user's input before changing the model, because they may have answered questions or commented since you last looked.

- Ask for a dimension: `calipurr meow KEY --name "..." --ask "where and how to measure it"`
- Read dimensions: `calipurr bowl --json`. Build scripts should read `params.toml`.
- Read comments pinned to models and photos: `calipurr dots --json`. Positions on models are in model coordinates, and positions on photos run from 0 to 1 across and down.
- Check a model: `calipurr purrflight FILE --machine NAME --json`. Warnings mean look closer. They aren't verdicts, so tell the user what they'd need to check in a slicer.
- Offer the visual interface when geometry is hard to discuss in words: ask the user to run `calipurr serve`. It reloads when files change.

## Parts that must fit something real

Before designing a part that mates with a real object, or when a print or fit test comes back wrong, read [the test-fit playbook](references/test-fit.md). Prefer a small test piece that answers one question over reprinting a whole part.

- Make a gauge: `calipurr kitten gauge --from MM --to MM --for KEY --name NAME`. Add `--kind socket` when it goes around the mating part.
- Make a cutout: `calipurr kitten cut FILE --keep-above Z --name NAME`
- Read results: `calipurr kitten list --json`. The user can report in the GUI, or you can record what they tell you with `calipurr kitten report NAME --step LETTER --measured MM`.

## Recording values

- A value the user measured or verified: `calipurr feed NAME KEY VALUE --note "how it was measured"`
- A guess or a spec sheet number: add `--assumed`
- A part dimension: `calipurr treat KEY VALUE --note "how it was measured"`, with `--assumed` for guesses
- A new machine: `calipurr adopt NAME --kind printer|cnc|laser`

Every command has a plain alias if the user prefers it: `adopt`/`add`, `litter`/`list`, `vet`/`show`, `feed`/`set`, `hungry`/`missing`, `meow`/`ask`, `bowl`/`params`, `treat`/`answer`, `dots`/`comments`, `kitten`/`test-piece`, `purrflight`/`check`, `serve`/`gui`.
