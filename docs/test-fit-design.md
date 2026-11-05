# Test-fit support: design note

Status: mostly built. The sections below note what is still open.

## Where this came from

A real project adapted an MPCNC dust collection part from 1 in tube to 3/4 in EMT. Most of the useful work happened between CAD steps:

- The user supplied measurements, photos and marked-up screenshots in answer to short numbered questions.
- A stepped gauge settled the plug size. The step modeled at 20.9 mm printed at 20.75 mm and fit snugly.
- A cutout of the hose port tested the hose fit without printing the whole part.
- One print spaghettified. The user suggested resting the plugs on the bed, as the original design did, and a later version of the bottom piece printed fine.
- A test print showed the suction ring sat about 10 mm off, which corrected a value in the model.
- The user questioned whether the ring was needed at all, which led to a simpler nozzle.

## The loop

```
assumption -> kitten -> print or cut -> user reports -> value marked measured -> model rebuilds
```

## Built

- `calipurr kitten gauge`, `kitten cut`, `kitten report` and `purrflight`
- Lettered gauge steps, with step picking on the 3D model as an alternative to reading a label
- A report card that warns when a caliper reading is more than one step from the chosen step
- Test pieces started from any food bowl value
- Laser dots on models and photos

## Still open

- Label legibility on small curved steps needs a real print test. Tally marks are the fallback if letters don't hold up.
- Overhang warnings need tuning against more real prints. In the first comparison, parts that printed fine still got a mid-air warning, with about 870 mm2 of overhang, against about 3090 mm2 on a saved failed orientation.
- Saved fit results don't yet suggest a starting offset for the next part. When they do, the suggestion should be marked `assumed`, and a gauge should still be recommended when the fit matters.
- A cardboard box view of the kittens tried so far and what each one proved.
- Laser cutter output, and 2D files in the viewer.
- Laser dots show through the model when they're on its far side.
