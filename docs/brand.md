# The cat bible

Emily is a tuxedo cat who carries calipers. Lean into the puns everywhere, with two rules:

1. **Every pun has a plain label beside it.** Someone should understand each control on first sight, including through a screen reader.
2. **Safety messages are never puns.** Anything about fire, spinning bits or machine crashes is stated plainly.

## GUI components

Each cat object does a real job, chosen because cat behavior already resembles that job.

| Cat thing | Plain label | What it does | Why it fits |
|---|---|---|---|
| Cat tree | Project stages | Vertical navigation with a perch per stage (Measure, Model, Check, Make). Emily sits on the current one | Cats climb as things get interesting |
| Laser dot | Point at this | Click the model to pin a comment to a 3D location | Everyone stares at the dot |
| Food bowl | Measurements needed | The list of values still needed. The bowl fills as values come in | The cat tells you when something is missing |
| Yarn ball | Rotate | Drag to rotate the model | Batting a ball around |
| Whiskers | Clearance check | Shows whether parts and machine limits have enough room | Cats use whiskers to judge gaps |
| Cardboard box | Fit check | Shows "If it fits, I sits" when a part fits the machine | Cats and boxes |
| Collar tag | Machine | Shows and switches the active machine profile | Identifies who the cat belongs to |
| Hairball | Problems | Model problems that need attention | Something came up |
| Nine lives | Version history | Earlier versions you can return to | Second chances |
| Litter box | Discarded | Rejected variations, kept until you clean them out | Where the rejects go |

The word "laser" in the laser dot refers only to the comment pointer. Laser cutter screens use their own plain language so the two never get confused.

A **kitten** (plain label: test piece) is a small print or cut that answers one question about a bigger part. A **litter of kittens** is a set of them, like a stepped gauge's sizes.

## CLI vocabulary

| Pun | Plain alias | Job |
|---|---|---|
| `adopt` | `add` | Add a machine |
| `litter` | `list` | List machines |
| `vet` | `show` | Inspect a machine's values |
| `feed` | `set` | Record a value |
| `hungry` | `missing` | List values still needed |

## Pun bank

`purrflight` (pre-flight check), `pawprint` (footprint or bounding box), `scratch` (rough cut), `purr-fect fit` (a passing fit test), `meow` (a question for the user), `cat-alog` (parts library), `hiss` (blocked operation, with the reason in plain words).
