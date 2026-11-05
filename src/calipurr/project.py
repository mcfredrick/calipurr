"""A project is a plain folder any agent can read and write.

params.toml         questions for the user: needed, then assumed, measured or answered
annotations.json    laser dots: comments pinned to a model or photo
next.txt            what the agent says the user should do next
kittens/            small test pieces and what each one proved
litter/             discarded files, kept until the user cleans them out
.calipurr/lives/    earlier versions of params.toml
"""

from __future__ import annotations

import json
import math
import os
import shutil
import tomllib
from datetime import date, datetime
from pathlib import Path

import tomli_w

from .errors import Hiss
from .profiles import ASSUMED, MEASURED, NEEDED

MODEL_SUFFIXES = {".stl"}
PHOTO_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_LIVES = 9
NUMBER, TEXT, CHOICE = "number", "text", "choice"
ANSWERED = "answered"
QUESTION_FIELDS = ("name", "ask", "unit", "kind", "choices", "why", "required", "show", "at")


def positive_number(key: str, raw: object) -> float:
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise Hiss(f"{key} must be a number, got {raw!r}") from None
    if not 0 < value < math.inf:
        raise Hiss(f"{key} must be greater than zero, got {raw}")
    return value


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(text)
    temp.replace(path)


class Project:
    def __init__(self, root: Path | str = "."):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise Hiss(f"No project folder at {self.root}")
        self.params_path = self.root / "params.toml"
        self.dots_path = self.root / "annotations.json"
        self.next_path = self.root / "next.txt"
        self.kittens_dir = self.root / "kittens"
        self.litter_dir = self.root / "litter"
        self.lives_dir = self.root / ".calipurr" / "lives"

    # Parameters

    def params(self) -> dict:
        if not self.params_path.exists():
            return {}
        return tomllib.loads(self.params_path.read_text()).get("params", {})

    def _save_params(self, params: dict) -> None:
        if self.params_path.exists():
            self._snapshot()
        _write_atomic(self.params_path, tomli_w.dumps({"params": params}))

    def meow(
        self,
        key: str,
        name: str,
        ask: str,
        unit: str = "mm",
        kind: str = NUMBER,
        choices: list[str] | None = None,
        why: str | None = None,
        required: bool = True,
        show: str | None = None,
        at: list[list[float]] | None = None,
    ) -> dict:
        """Ask the user something. Rewording keeps the answer unless it no longer fits the question."""
        if not key or not key.replace("_", "").isalnum():
            raise Hiss(f"Question names use letters, digits and underscores, got {key!r}")
        if kind not in (NUMBER, TEXT, CHOICE):
            raise Hiss(f"Question kinds are {NUMBER}, {TEXT} and {CHOICE}, got {kind!r}")
        if (kind == CHOICE) != bool(choices):
            raise Hiss("Choice questions need choices, and only choice questions can have them")
        if show:
            self.resolve_file(show)
        if at:
            if not show:
                raise Hiss("Marking a spot needs a picture to mark: pass show as well")
            if len(at) > 2:
                raise Hiss("A mark is one point, or two for the ends of a dimension")
            for point in at:
                self._check_position(show, point)
        params = self.params()
        entry = params.get(key, {"status": NEEDED})
        stale = entry.get("kind", NUMBER) != kind or (choices and entry.get("value") not in choices)
        if stale:
            entry = {"status": NEEDED}
        for field in QUESTION_FIELDS:
            entry.pop(field, None)
        entry.update(name=name, ask=ask, unit=unit, kind=kind, required=required)
        entry.update({k: v for k, v in (("choices", choices), ("why", why), ("show", show), ("at", at)) if v})
        params[key] = entry
        self._save_params(params)
        return entry

    def answer(self, key: str, raw: object, status: str = MEASURED, note: str | None = None) -> dict:
        params = self.params()
        if key not in params:
            raise Hiss(f"Nothing has asked for {key}. Add it first: calipurr meow {key} --name ... --ask ...")
        question = params[key]
        kind = question.get("kind", NUMBER)
        if kind == NUMBER:
            if status not in (ASSUMED, MEASURED):
                raise Hiss(f"Status must be {ASSUMED} or {MEASURED}, got {status!r}")
            value: float | str = positive_number(key, raw)
        else:
            value, status = str(raw).strip(), ANSWERED
            if not value:
                raise Hiss(f"{key} needs an answer")
            if kind == CHOICE and value not in question["choices"]:
                raise Hiss(f"{key} must be one of: {', '.join(question['choices'])}")
        entry = {k: question[k] for k in QUESTION_FIELDS if k in question}
        entry.update(value=value, status=status, date=date.today().isoformat())
        if note:
            entry["note"] = note
        params[key] = entry
        self._save_params(params)
        return entry

    def forget(self, key: str) -> dict:
        """Put a value back to needed, keeping its question."""
        params = self.params()
        if key not in params:
            raise Hiss(f"No parameter named {key}")
        entry = {k: params[key][k] for k in QUESTION_FIELDS if k in params[key]}
        entry["status"] = NEEDED
        params[key] = entry
        self._save_params(params)
        return entry

    def hungry(self) -> dict[str, str]:
        """Required questions still waiting on the user. Optional ones never block progress."""
        return {
            k: e.get("ask", "")
            for k, e in self.params().items()
            if e["status"] == NEEDED and e.get("required", True)
        }

    # What the user should do next

    def next_step(self) -> str:
        return self.next_path.read_text().strip() if self.next_path.exists() else ""

    def nudge(self, text: str | None) -> None:
        if text:
            _write_atomic(self.next_path, text.strip() + "\n")
        else:
            self.next_path.unlink(missing_ok=True)

    # Nine lives

    def _snapshot(self) -> None:
        self.lives_dir.mkdir(parents=True, exist_ok=True)
        existing = self._life_paths()
        number = int(existing[-1].stem) + 1 if existing else 1
        shutil.copy2(self.params_path, self.lives_dir / f"{number:06d}.toml")
        for old in self._life_paths()[: -(MAX_LIVES - 1)]:
            old.unlink()

    def _life_paths(self) -> list[Path]:
        return sorted(self.lives_dir.glob("*.toml")) if self.lives_dir.is_dir() else []

    def lives(self) -> list[dict]:
        result = []
        for path in self._life_paths():
            params = tomllib.loads(path.read_text()).get("params", {})
            result.append(
                {
                    "id": path.stem,
                    "saved": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                    "values": {k: e.get("value") for k, e in params.items()},
                }
            )
        return result

    def restore_life(self, life_id: str) -> None:
        path = self.lives_dir / f"{life_id}.toml"
        if not life_id.isdigit() or not path.exists():
            raise Hiss(f"No saved version {life_id}")
        text = path.read_text()
        self._snapshot()
        _write_atomic(self.params_path, text)

    # Laser dots

    def dots(self) -> list[dict]:
        if not self.dots_path.exists():
            return []
        return json.loads(self.dots_path.read_text())["dots"]

    def _save_dots(self, dots: list[dict]) -> None:
        _write_atomic(self.dots_path, json.dumps({"dots": dots}, indent=2) + "\n")

    def _check_position(self, file: str, position: list[float]) -> None:
        on_model = self.resolve_file(file).suffix.lower() in MODEL_SUFFIXES
        size = 3 if on_model else 2
        if len(position) != size or not all(isinstance(v, (int, float)) and math.isfinite(v) for v in position):
            raise Hiss(f"A spot on {file} needs {size} finite coordinates")
        if not on_model and not all(0 <= v <= 1 for v in position):
            raise Hiss(f"Spots on a photo run from 0 to 1 across and down, got {position}")

    def add_dot(self, file: str, position: list[float], text: str = "") -> dict:
        self._check_position(file, position)
        dots = self.dots()
        dot = {"id": max((d["id"] for d in dots), default=0) + 1, "file": file, "position": position, "text": text}
        self._save_dots([*dots, dot])
        return dot

    def edit_dot(self, dot_id: int, text: str) -> None:
        dots = self.dots()
        for dot in dots:
            if dot["id"] == dot_id:
                dot["text"] = text
                self._save_dots(dots)
                return
        raise Hiss(f"No dot numbered {dot_id}")

    def remove_dot(self, dot_id: int) -> None:
        dots = self.dots()
        remaining = [d for d in dots if d["id"] != dot_id]
        if len(remaining) == len(dots):
            raise Hiss(f"No dot numbered {dot_id}")
        self._save_dots(remaining)

    # Files

    def _browsable_dirs(self) -> list[Path]:
        return [self.root, self.kittens_dir, self.root / "photos"]

    def resolve_file(self, name: str) -> Path:
        """Map a client-supplied name to a model or photo inside this project."""
        path = (self.root / name).resolve()
        allowed = path.parent in self._browsable_dirs() or path.parent == self.litter_dir
        if not allowed or path.suffix.lower() not in MODEL_SUFFIXES | PHOTO_SUFFIXES or not path.is_file():
            raise Hiss(f"No model or photo named {name} in this project")
        return path

    def files(self) -> dict[str, list[dict]]:
        result: dict[str, list[dict]] = {"models": [], "photos": []}
        for folder in self._browsable_dirs():
            if not folder.is_dir():
                continue
            for path in sorted(folder.iterdir()):
                suffix = path.suffix.lower()
                kind = "models" if suffix in MODEL_SUFFIXES else "photos" if suffix in PHOTO_SUFFIXES else None
                if kind and path.is_file():
                    result[kind].append(self._describe(path))
        return result

    def _describe(self, path: Path) -> dict:
        return {"name": path.relative_to(self.root).as_posix(), "mtime": path.stat().st_mtime}

    def discarded(self) -> list[dict]:
        if not self.litter_dir.is_dir():
            return []
        return [self._describe(p) for p in sorted(self.litter_dir.iterdir()) if p.is_file()]

    def discard(self, name: str) -> str:
        path = self.resolve_file(name)
        if path.parent == self.litter_dir:
            raise Hiss(f"{name} is already in the litter box")
        self.litter_dir.mkdir(exist_ok=True)
        target = self.litter_dir / path.name
        if target.exists():
            raise Hiss(f"The litter box already has a {path.name}. Clean it out or rename one first.")
        path.replace(target)
        return target.relative_to(self.root).as_posix()

    def rescue(self, name: str) -> str:
        path = self.resolve_file(name)
        if path.parent != self.litter_dir:
            raise Hiss(f"{name} isn't in the litter box")
        target = self.root / path.name
        if target.exists():
            raise Hiss(f"A file named {path.name} is already in the project")
        path.replace(target)
        return target.name
