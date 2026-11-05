# Test-fit playbook

Use this when a part has to fit something real. Calipurr calls a small test piece a **kitten**: a little version of the big part, made to answer one question.

## Before modeling

1. List what the part touches, and everything nearby that could get in the way.
2. Ask for the measurements you need in one short numbered list. Say where to measure and with what tool. Ask for a photo or marked-up screenshot when words won't settle it.
3. Ask what the part is for, and question requirements that add difficulty. A simpler part may do the same job.
4. Mark each number as measured or assumed, and tell the user which assumptions could ruin the part.

## Choosing a kitten

For each risky assumption, make the smallest piece that can prove it wrong.

| Question | Kitten | How it works |
|---|---|---|
| What size fits snugly? | Stepped gauge | A plug or socket with several diameters in small steps, around the expected size. The user reports which step fits, then measures it |
| Does this feature work? | Feature cutout | Only the risky feature, sliced out of the real model so its geometry stays identical |
| Is this in the right place? | Location check | A thin, fast frame with just enough material to locate against the real machine |
| Will this print? | Print check | The hardest overhang or thinnest section, printed in the planned orientation |

Skip the kitten when it would take about as long as the real part, or when a failure would cost little.

## Designing a stepped gauge

- Use `calipurr kitten gauge`, which handles the labels and the size table. Span the expected size in both directions. Steps of 0.2 mm suit FDM printing as a starting point.
- Print it in the same orientation and material as the final part, because both change the fit.
- Label every step so the user can report a result by name. Counting steps from an end is easy to get wrong.
- Use one letter per step (A, B, C), and give the user a table of each letter's modeled size. Letters stay readable at sizes where a number like 20.9 won't.
- Cut labels into the surface instead of raising them, so they can't change the fit. Keep them on the mating surface only if there's no other place, and make the steps tall enough to read them. About 6 mm is a starting point for FDM.
- Ask for the result by letter, such as "C goes in snugly, D won't enter." If the steps are too small to label, the user can pick the step on the model in the Calipurr GUI. Otherwise, name each step by its position from a clearly different end, and have them measure the step to confirm.

## Closing the loop

1. Ask which step fit, what it feels like, and what the fitting piece measures with calipers. A nominal size and its printed size usually differ.
2. Put the result in the build script as the named value, with a comment saying where it came from.
3. Regenerate every affected file, and tell the user which files changed.
4. Record anything true of the machine with `calipurr feed`. Fit results depend on the material and settings, so include those in `--note`.

Example: a gauge step modeled at 20.9 mm printed at 20.75 mm and fit a tube measured at 20.9 mm inside, so the build script used the 20.9 mm model value.

## Check before sending a print

- Run `calipurr purrflight`, which reloads the saved file to confirm it's a closed solid, because saving can collapse slivers.
- Check the part sits flat on the bed in its intended orientation, with enough contact to stay stuck. Tell the user how it should be oriented.
- Look for overhangs and unsupported starts. A part that begins printing in mid-air will fail.
- Look at how an original design was oriented before changing it. If it rested a feature on the bed, keep that unless there's a reason not to.

## When a test fails

Ask what happened and get a photo. Change one thing, and explain what the next kitten should prove. Treat the user's own observations of the physical part as more reliable than the model.
