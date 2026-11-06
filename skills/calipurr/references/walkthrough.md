# Walkthrough playbook

A walkthrough is what the user follows at the machine, often with dusty hands and a phone. Write it so they never need the chat open.

## The body file

Write `walkthroughs/NAME.body.html` as an HTML fragment. Calipurr adds the title, step numbers, contents and styling.

```html
<p class="lede">What this makes, how long it takes, and what it proves.</p>

<section class="part">
  <h2>Cut the strips</h2>
  <article class="step">
    <h3>Trace, then cut</h3>
    <p class="meta">About 19 minutes. Router on at the pause.</p>
    <ol><li>Run <code>2_cut_strips.nc</code>.</li></ol>
    <figure>
      <div class="fig"><svg viewBox="0 0 400 140" role="img" aria-label="..."> ... </svg></div>
      <figcaption>To scale, in mm.</figcaption>
    </figure>
  </article>
</section>
```

- Each `<section class="part">` must open with its `h2`, and each `<article class="step">` must open with its `h3`. A part with no steps works for reference material.
- Don't write step numbers, and refer to other steps by name, because numbers change when steps are added.
- Scripts aren't allowed. Images must be project files and need `alt` text. They get packed into the page, relative to the body file, so don't use web addresses.
- Photos can show a user's home, so only include one they took for this guide or that shows nothing but the work.

## Classes

| Class | Use |
|---|---|
| `lede` | The opening paragraph |
| `meta` | A step's time, tool or router state |
| `warn` | `<div class="warn"><strong>Stop</strong> ...</div>` for anything that can hurt someone or break something |
| `note` | `<div class="note"><strong>Why</strong> ...</div>` for a useful reason or tip |
| `fig`, `fig small` | Wrap an `img` or `svg` inside a `figure` |
| `checks` | A `ul` of boxes to tick, such as materials |
| `table` | Wrap a `table` so it scrolls on a phone. Use `td class="n"` for numbers |
| `twocol` | Two blocks side by side on a wide screen |

SVG drawings can use `d-wood`, `d-part`, `d-plate`, `d-spoil`, `d-steel`, `d-void`, `d-line`, `d-thin`, `d-dash`, `d-dye`, `d-dye-dash`, `d-dye-fill`, `d-caution`, `d-caution-line`, `d-text`, `d-label`, `d-mono`, `d-dye-text`, `d-caution-text`, `d-muted`, `d-box` and `d-box-dye`. They follow light and dark mode. Set sizes on these elements with `style`, because classes override presentation attributes.

## What to include

- What the job proves or produces, and the total time.
- Safety first, in plain words. No puns.
- Materials and tools as a checklist, with sizes the user needs to buy or find.
- One action per list item. Name the exact file to run and the exact command to send.
- Drawings of anything hard to describe, such as which way a piece faces. Draw them to scale from the real numbers, and label which values they use.
- Simulated results where you have them, labeled as simulated.
- What a good result looks like at each checkpoint, and what to do when it isn't.
- Which values were assumed or measured, when a wrong one could spoil the job.
- How to report results back to you.

Rebuild whenever a change affects the steps, then open the page and read it as the user would.
