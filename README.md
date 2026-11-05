<p align="center"><img src="assets/logo.svg" width="220" alt="Emily, a tuxedo cat, holding calipers"></p>

# Calipurr

Measure twice, purr once.

Calipurr helps you and your AI agent agree on real-world geometry for 3D printing, CNC routing and laser cutting. It remembers what your machines can actually do, and it records whether each number was measured or just assumed. It works with any agent that has shell access, and with no agent at all.

**Status:** early and unpublished. The machine profile CLI works. The [GUI mockup](docs/mockup.html) shows where the visual interface is headed, and its controls aren't connected to real models yet.

## Try it

From a clone of this repo:

```
uv run calipurr adopt my-router --kind cnc
uv run calipurr hungry my-router
uv run calipurr feed my-router travel_z_mm 90 --note "measured with router installed"
uv run calipurr vet my-router
```

Profiles are saved in `~/.config/calipurr/machines/`, so they stay on your computer and survive upgrades. Calipurr ships no default machine values, because a borrowed number can break a bit or start a fire. It keeps asking until you supply them.

| Command | Plain alias | Job |
|---|---|---|
| `adopt` | `add` | Add a machine |
| `litter` | `list` | List machines |
| `vet` | `show` | Show a machine's values and where they came from |
| `feed` | `set` | Record a value, with `--assumed` for guesses |
| `hungry` | `missing` | List values still needed (exits 1 if any are) |

Add `--json` to any command for agent-friendly output.

## Use it with your agent

`skills/calipurr/` is an [Agent Skill](https://agentskills.io). Copy it to wherever your agent keeps skills. If your agent doesn't support skills, point it at `skills/calipurr/SKILL.md`.

## Safety

Calipurr doesn't make machines safe. Check its output yourself, and never leave a running laser or router unattended.

## About the mascot

Emily is named for Emily Warren Roebling (1843-1903). When caisson disease left her husband, chief engineer Washington Roebling, bedridden during construction of the Brooklyn Bridge, she relayed information between him and his assistants and reported the progress of the work back to him. Through that work she developed an extensive knowledge of strength of materials, stress analysis and catenary curves.

She later earned a law certificate from New York University and published "A Wife's Disabilities," an essay arguing for women's rights. Emily the cat takes on a small version of her role on the bridge, carrying accurate information between the people who measure things and the tools that design and make them.

## License

[GPL-3.0-or-later](LICENSE)
