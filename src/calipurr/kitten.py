"""Kittens: small test pieces that each answer one question about a bigger part."""

from __future__ import annotations

import json
import math
import re
from datetime import date
from pathlib import Path

import numpy as np
import trimesh
from manifold3d import CrossSection, Manifold, Mesh

from .errors import Hiss, NeedsConfirmation
from .project import Project, positive_number

# I and O are left out because they read as 1 and 0 on a small print.
LETTERS = "ABCDEFGHJKLM"
MAX_STEPS = len(LETTERS)

# Stroke endpoints on a unit box, with x across and z up.
STROKES = {
    "A": [(0, 0, 0.5, 1), (0.5, 1, 1, 0), (0.2, 0.4, 0.8, 0.4)],
    "B": [(0, 0, 0, 1), (0, 1, 0.8, 1), (0.8, 1, 0.8, 0.55), (0, 0.5, 1, 0.5), (1, 0.5, 1, 0), (0, 0, 1, 0)],
    "C": [(1, 1, 0, 1), (0, 1, 0, 0), (0, 0, 1, 0)],
    "D": [(0, 0, 0, 1), (0, 1, 0.7, 1), (0.7, 1, 1, 0.7), (1, 0.7, 1, 0.3), (1, 0.3, 0.7, 0), (0.7, 0, 0, 0)],
    "E": [(1, 1, 0, 1), (0, 1, 0, 0), (0, 0, 1, 0), (0, 0.5, 0.8, 0.5)],
    "F": [(1, 1, 0, 1), (0, 1, 0, 0), (0, 0.5, 0.8, 0.5)],
    "G": [(1, 1, 0, 1), (0, 1, 0, 0), (0, 0, 1, 0), (1, 0, 1, 0.45), (1, 0.45, 0.5, 0.45)],
    "H": [(0, 0, 0, 1), (1, 0, 1, 1), (0, 0.5, 1, 0.5)],
    "J": [(1, 1, 1, 0), (1, 0, 0, 0), (0, 0, 0, 0.3)],
    "K": [(0, 0, 0, 1), (0, 0.45, 1, 1), (0.3, 0.6, 1, 0)],
    "L": [(0, 1, 0, 0), (0, 0, 1, 0)],
    "M": [(0, 0, 0, 1), (0, 1, 0.5, 0.45), (0.5, 0.45, 1, 1), (1, 1, 1, 0)],
}

LETTER_HEIGHT = 4.4
LETTER_WIDTH = 2.8
STROKE_WIDTH = 0.8
LABEL_DEPTH = 0.5
TOP_CLEARANCE = 1.0
HEAD_HEIGHT = 3.0
HEAD_LIP = 2.5
SOCKET_WALL = 3.0
SEGMENTS = 180


def to_trimesh(solid: Manifold) -> trimesh.Trimesh:
    mesh = solid.to_mesh()
    return trimesh.Trimesh(mesh.vert_properties[:, :3], mesh.tri_verts)


def from_stl(path: Path) -> Manifold:
    loaded = trimesh.load_mesh(path)
    solid = Manifold(Mesh(np.asarray(loaded.vertices, dtype=np.float32), np.asarray(loaded.faces, dtype=np.uint32)))
    if solid.is_empty():
        raise Hiss(f"{path.name} isn't a closed solid, so it can't be cut cleanly")
    return solid


def _letter_cutter(letter: str, radius: float, z_center: float) -> Manifold:
    """Boxes that recess a letter into a cylinder's -Y side, the side the viewer opens on."""
    # Keep the surface recessed at the letter's edges too, where the wall curves away.
    sagitta = radius - math.sqrt(radius**2 - (LETTER_WIDTH / 2) ** 2)
    if sagitta >= LABEL_DEPTH * 0.6:
        raise Hiss(f"A {radius * 2:g} mm diameter curves too sharply for a readable label. Use --no-labels.")
    inner, outer = radius - LABEL_DEPTH, radius + 1.0
    cutter = None
    for x0, z0, x1, z1 in STROKES[letter]:
        # Built on +Y, where x runs backward as seen from outside, then turned to face -Y.
        ax, bx = (0.5 - x0) * LETTER_WIDTH, (0.5 - x1) * LETTER_WIDTH
        az, bz = (z0 - 0.5) * LETTER_HEIGHT, (z1 - 0.5) * LETTER_HEIGHT
        length = math.hypot(bx - ax, bz - az) + STROKE_WIDTH
        angle = math.degrees(math.atan2(bz - az, bx - ax))
        box = (
            Manifold.cube((length, outer - inner, STROKE_WIDTH), center=True)
            .rotate((0, -angle, 0))
            .translate(((ax + bx) / 2, (inner + outer) / 2, z_center + (az + bz) / 2))
        )
        cutter = box if cutter is None else cutter + box
    return cutter.rotate((0, 0, 180))


def _sizes(start: float, stop: float, step: float) -> list[float]:
    if stop <= start:
        raise Hiss("The gauge's --to size must be larger than its --from size")
    count = round((stop - start) / step) + 1
    if not 2 <= count <= MAX_STEPS:
        raise Hiss(f"A gauge has 2 to {MAX_STEPS} steps, and these sizes give {count}. Change the range or step.")
    return [round(start + i * step, 3) for i in range(count)]


def _plug(sizes: list[float], step_height: float, labels: bool) -> tuple[Manifold, list[dict]]:
    """Tip-up stepped plug. A is the smallest, at the tip, so it enters first."""
    head_radius = sizes[-1] / 2 + HEAD_LIP
    profile = [(0.0, 0.0), (head_radius, 0.0), (head_radius, HEAD_HEIGHT)]
    steps = []
    z = HEAD_HEIGHT
    for index, size in enumerate(reversed(sizes)):
        profile += [(size / 2, z), (size / 2, z + step_height)]
        steps.append({"letter": LETTERS[len(sizes) - 1 - index], "size_mm": size, "z0": z, "z1": z + step_height})
        z += step_height
    profile.append((0.0, z))
    solid = Manifold.revolve(CrossSection([profile]), circular_segments=SEGMENTS)
    if labels:
        for step in steps:
            solid = solid - _letter_cutter(step["letter"], step["size_mm"] / 2, (step["z0"] + step["z1"]) / 2)
    return solid, sorted(steps, key=lambda s: s["letter"])


def _socket(sizes: list[float], step_height: float, labels: bool) -> tuple[Manifold, list[dict]]:
    """Mouth-up stepped socket. A is the largest, at the mouth, so it's reached first."""
    outer = sizes[-1] / 2 + SOCKET_WALL
    height = step_height * len(sizes)
    # The bore overshoots both ends so the cut never leaves a skin on the end faces.
    bore = [(0.0, -1.0), (sizes[0] / 2, -1.0)]
    steps = []
    z = 0.0
    for index, size in enumerate(sizes):
        bore += [(size / 2, z), (size / 2, z + step_height)]
        steps.append({"letter": LETTERS[len(sizes) - 1 - index], "size_mm": size, "z0": z, "z1": z + step_height})
        z += step_height
    bore += [(sizes[-1] / 2, z + 1.0), (0.0, z + 1.0)]
    solid = Manifold.cylinder(height, outer, outer, SEGMENTS) - Manifold.revolve(
        CrossSection([bore]), circular_segments=SEGMENTS
    )
    if labels:
        for step in steps:
            solid = solid - _letter_cutter(step["letter"], outer, (step["z0"] + step["z1"]) / 2)
    return solid, sorted(steps, key=lambda s: s["letter"])


def _name(raw: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", raw):
        raise Hiss(f"Kitten names use letters, digits, dots, hyphens and underscores, got {raw!r}")
    return raw


def _export(project: Project, name: str, solid: Manifold, record: dict, force: bool) -> dict:
    stl = project.kittens_dir / f"{name}.stl"
    meta = project.kittens_dir / f"{name}.json"
    if not force and (stl.exists() or meta.exists()):
        raise Hiss(f"A kitten named {name} already exists. Pick another name or pass --force.")
    project.kittens_dir.mkdir(exist_ok=True)
    to_trimesh(solid).export(stl)
    # Checked after the round trip because saving to STL can collapse slivers.
    if not trimesh.load_mesh(stl).is_volume:
        stl.unlink()
        raise Hiss(f"{name} didn't export as a closed solid. Try a larger size or --no-labels.")
    record |= {"name": name, "file": stl.relative_to(project.root).as_posix(), "created": date.today().isoformat()}
    meta.write_text(json.dumps(record, indent=2) + "\n")
    return record


def make_gauge(
    project: Project,
    start: float,
    stop: float,
    step: float,
    kind: str = "plug",
    step_height: float = 6.0,
    labels: bool = True,
    target: str | None = None,
    name: str | None = None,
    force: bool = False,
) -> dict:
    start = positive_number("--from", start)
    stop = positive_number("--to", stop)
    step = positive_number("--step", step)
    step_height = positive_number("--step-height", step_height)
    if target is not None and target not in project.params():
        raise Hiss(f"Nothing has asked for {target}, so a gauge can't be linked to it")
    if labels and step_height < LETTER_HEIGHT + TOP_CLEARANCE:
        raise Hiss(f"Steps must be at least {LETTER_HEIGHT + TOP_CLEARANCE} mm tall to fit a label, or use --no-labels")
    builders = {"plug": _plug, "socket": _socket}
    if kind not in builders:
        raise Hiss(f"Gauge kinds are {', '.join(builders)}, got {kind!r}")
    sizes = _sizes(start, stop, step)
    solid, steps = builders[kind](sizes, step_height, labels)
    record = {
        "type": "gauge",
        "kind": kind,
        "for": target,
        "step_mm": step,
        "labels": labels,
        "steps": steps,
        "report": None,
    }
    return _export(project, _name(name or f"gauge-{target or kind}-{start:g}-{stop:g}"), solid, record, force)


def make_cut(
    project: Project,
    source: str,
    keep_above: float | None = None,
    keep_below: float | None = None,
    name: str | None = None,
    force: bool = False,
) -> dict:
    """Slice one feature out of a real model, so its geometry stays identical."""
    if keep_above is None and keep_below is None:
        raise Hiss("Say what to keep with --keep-above, --keep-below, or both")
    path = project.resolve_file(source)
    solid = from_stl(path)
    x0, y0, z0, x1, y1, z1 = solid.bounding_box()
    if keep_above is not None and keep_below is not None and keep_below <= keep_above:
        raise Hiss("--keep-below must be higher than --keep-above")
    low = z0 - 1 if keep_above is None else keep_above
    high = z1 + 1 if keep_below is None else keep_below
    if low >= z1 or high <= z0:
        raise Hiss(f"Nothing in {source} falls in that range. It spans Z {z0:g} to {z1:g} mm.")
    window = Manifold.cube((x1 - x0 + 2, y1 - y0 + 2, high - low)).translate((x0 - 1, y0 - 1, low))
    piece = solid ^ window
    # Rest the cut face on the bed, so the kitten prints without help.
    piece = piece.translate((0, 0, -piece.bounding_box()[2]))
    record = {"type": "cut", "source": source, "keep_above": keep_above, "keep_below": keep_below}
    return _export(project, _name(name or f"cut-{path.stem}"), piece, record, force)


def kittens(project: Project) -> list[dict]:
    if not project.kittens_dir.is_dir():
        return []
    return [json.loads(p.read_text()) for p in sorted(project.kittens_dir.glob("*.json"))]


def load_kitten(project: Project, name: str) -> dict:
    path = project.kittens_dir / f"{_name(name)}.json"
    if not path.exists():
        raise Hiss(f"No kitten named {name}")
    return json.loads(path.read_text())


def report(
    project: Project,
    name: str,
    letter: str,
    measured: float,
    material: str | None = None,
    machine: str | None = None,
    note: str | None = None,
    confirm: bool = False,
) -> dict:
    """Record which gauge step fit. The linked parameter takes the step's modeled size.

    The model needs the size that printed to fit, so that's the value to reuse.
    The caliper reading records the printer's offset and catches a misread step.
    """
    kitten = load_kitten(project, name)
    if kitten["type"] != "gauge":
        raise Hiss(f"{name} isn't a gauge")
    letter = letter.upper()
    step = next((s for s in kitten["steps"] if s["letter"] == letter), None)
    if step is None:
        raise Hiss(f"{name} has no step {letter}")
    measured = positive_number("The measurement", measured)
    gap = abs(measured - step["size_mm"])
    if gap > kitten["step_mm"] and not confirm:
        raise NeedsConfirmation(
            f"Step {letter} is modeled at {step['size_mm']:g} mm, but you measured {measured:g} mm. "
            "That's more than one step apart, so check you have the right step."
        )
    kitten["report"] = {
        "letter": letter,
        "modeled_mm": step["size_mm"],
        "measured_mm": measured,
        "offset_mm": round(measured - step["size_mm"], 3),
        "material": material,
        "machine": machine,
        "note": note,
        "date": date.today().isoformat(),
    }
    (project.kittens_dir / f"{name}.json").write_text(json.dumps(kitten, indent=2) + "\n")
    if kitten["for"]:
        detail = f"Gauge {name} step {letter} fit, modeled {step['size_mm']:g} mm, printed {measured:g} mm"
        extras = ", ".join(v for v in (material, machine, note) if v)
        project.answer(kitten["for"], step["size_mm"], note=f"{detail} ({extras})" if extras else detail)
    return kitten
