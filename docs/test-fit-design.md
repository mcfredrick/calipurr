# Test-fit support: design note

Status: proposed. The playbook in `skills/calipurr/references/test-fit.md` works today. The commands and GUI below don't exist yet.

## Where this came from

A real project adapted an MPCNC dust collection part from 1 in tube to 3/4 in EMT. Most of the useful work happened between CAD steps:

- The user supplied measurements, photos and marked-up screenshots in answer to short numbered questions.
- A stepped gauge settled the plug size. The step modeled at 20.9 mm printed at 20.75 mm and fit snugly.
- A cutout of the hose port tested the hose fit without printing the whole part.
- One print spaghettified. The user suggested resting the plugs on the bed, as the original design did, and a later version of the bottom piece printed fine.
- A test print showed the suction ring sat about 10 mm off, which corrected a value in the model.
- The user questioned whether the ring was needed at all, which led to a simpler nozzle.

## Proposed loop

```
assumption -> kitten -> print or cut -> user reports -> value marked measured -> model rebuilds
```

## Proposed CLI

| Command | Job |
|---|---|
| `calipurr kitten gauge --from 20.3 --to 21.1 --step 0.2` | Generate a stepped gauge STL |
| `calipurr kitten cut part.stl --keep-above 139` | Slice one feature out of a model |
| `calipurr purrflight part.stl --machine NAME` | Check the part is a closed solid, fits the machine, and sits on the bed |

Gauges are always labeled. Each step gets a recessed letter, and the command prints a table of letters and modeled sizes. This comes from the same project, where the unlabeled gauge made it hard to say which step worked. Label legibility on small curved steps still needs a real print test, and tally marks are the fallback if letters don't hold up.

Fit results get saved with the project and the machine, including material and settings, so later parts can start from a known offset. The tool would suggest that offset, marked `assumed`, and still recommend a gauge when the fit matters.

## Proposed GUI

- A **kitten** can be attached to any food bowl value: "Not sure? Make a test piece."
- A report card shows the gauge with its lettered steps, asks which letter fit and what it measured, and fills in the value as `measured`.
- A **cardboard box** view shows the kittens tried so far and what each one proved.
- Laser dots work on photos as well as models, so users can mark up a picture of their real machine.
