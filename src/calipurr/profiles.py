"""Machine profiles: what each machine really is, and how we know.

Profiles live outside the package so upgrades can't overwrite them. A value is
never defaulted, because a borrowed number can break a bit or start a laser
fire. Anything nobody has supplied stays "needed" until someone feeds it.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import tomli_w

from .errors import Hiss

NEEDED = "needed"
ASSUMED = "assumed"
MEASURED = "measured"


@dataclass(frozen=True)
class Field:
    key: str
    ask: str
    choices: tuple[str, ...] = ()

    def parse(self, raw: str) -> float | str:
        if self.choices:
            if raw not in self.choices:
                raise Hiss(f"{self.key} must be one of: {', '.join(self.choices)}")
            return raw
        try:
            value = float(raw)
        except ValueError:
            raise Hiss(f"{self.key} must be a number, got {raw!r}") from None
        if not 0 < value < float("inf"):
            raise Hiss(f"{self.key} must be greater than zero, got {raw}")
        return value


KINDS: dict[str, tuple[Field, ...]] = {
    "printer": (
        Field("build_x_mm", "Usable build size in X (mm)"),
        Field("build_y_mm", "Usable build size in Y (mm)"),
        Field("build_z_mm", "Usable build size in Z (mm)"),
        Field("nozzle_mm", "Nozzle diameter (mm)"),
        Field("hole_undersize_mm", "How far undersize a printed test hole comes out (mm)"),
    ),
    "cnc": (
        Field("travel_x_mm", "Usable travel in X (mm)"),
        Field("travel_y_mm", "Usable travel in Y (mm)"),
        Field("travel_z_mm", "Usable Z travel with your spindle installed (mm)"),
        Field("max_feed_mm_min", "Fastest cutting feed you trust (mm/min)"),
        Field("max_plunge_mm_min", "Fastest plunge feed you trust (mm/min)"),
        Field("collet_mm", "Collet size you normally run (mm)"),
    ),
    "laser": (
        Field("source", "Laser source", ("diode", "co2", "fiber")),
        Field("bed_x_mm", "Usable bed size in X (mm)"),
        Field("bed_y_mm", "Usable bed size in Y (mm)"),
        Field("power_w", "Rated optical output power (W)"),
        Field("kerf_mm", "Kerf measured on a test cut in your usual material (mm)"),
    ),
}

_NAME = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
_TAG = re.compile(r"[a-z0-9][a-z0-9_]{0,63}")


def home() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "calipurr" / "machines"


def _path(name: str) -> Path:
    if not _NAME.fullmatch(name):
        raise Hiss(f"Machine names use lowercase letters, digits and hyphens, got {name!r}")
    return home() / f"{name}.toml"


def fields_for(kind: str) -> tuple[Field, ...]:
    try:
        return KINDS[kind]
    except KeyError:
        raise Hiss(f"Unknown kind {kind!r}. Choose from: {', '.join(KINDS)}") from None


def adopt(name: str, kind: str) -> dict:
    path = _path(name)
    specs = fields_for(kind)
    if path.exists():
        raise Hiss(f"{name} already lives here: {path}")
    profile = {
        "kind": kind,
        "fields": {f.key: {"status": NEEDED, "ask": f.ask} for f in specs},
    }
    _save(name, profile)
    return profile


def load(name: str) -> dict:
    path = _path(name)
    if not path.exists():
        raise Hiss(f"No machine named {name}. Adopt it first: calipurr adopt {name} --kind cnc")
    return tomllib.loads(path.read_text())


def litter() -> list[str]:
    return sorted(p.stem for p in home().glob("*.toml"))


def feed(name: str, key: str, raw: str, status: str, note: str | None = None) -> dict:
    if status not in (ASSUMED, MEASURED):
        raise Hiss(f"Status must be {ASSUMED} or {MEASURED}, got {status!r}")
    profile = load(name)
    specs = {f.key: f for f in fields_for(profile["kind"])}
    if key not in specs:
        raise Hiss(f"{key} isn't a {profile['kind']} field. Choose from: {', '.join(specs)}")
    entry = {
        "value": specs[key].parse(raw),
        "status": status,
        "date": date.today().isoformat(),
        "ask": specs[key].ask,
    }
    if note:
        entry["note"] = note
    profile["fields"][key] = entry
    _save(name, profile)
    return profile


def tag(name: str, key: str, text: str | None) -> dict:
    """Keep a fact about a machine in words, such as its controller or home corner. Nothing is ever required here."""
    if not _TAG.fullmatch(key):
        raise Hiss(f"Tag names use lowercase letters, digits and underscores, got {key!r}")
    profile = load(name)
    notes = profile.setdefault("notes", {})
    if text is None:
        if key not in notes:
            raise Hiss(f"{name} has no tag named {key}")
        del notes[key]
    else:
        if not text.strip():
            raise Hiss(f"{key} needs some text. To delete it, use --remove")
        notes[key] = {"value": text.strip(), "date": date.today().isoformat()}
    _save(name, profile)
    return profile


def hungry(profile: dict) -> dict[str, str]:
    """Fields nobody has supplied, mapped to the question that fills them."""
    return {k: e["ask"] for k, e in profile["fields"].items() if e["status"] == NEEDED}


def _save(name: str, profile: dict) -> None:
    path = _path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomli_w.dumps(profile))
