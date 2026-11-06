"""Catwalk (plain name: walkthrough): a step-by-step shop guide built from a simple HTML body.

The author writes parts and steps. This adds the step numbers, table of contents
and styling, and packs images in, so the result is one file that works offline.
"""

from __future__ import annotations

import base64
import html
import re
from importlib import resources
from pathlib import Path

from .errors import Hiss
from .project import BODY_SUFFIX, Project, _write_atomic

IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif", ".svg": "image/svg+xml"}
HEADING = re.compile(r'<section class="part">\s*<h2>(?P<part>.*?)</h2>|<article class="step">\s*<h3>(?P<step>.*?)</h3>', re.S)


def _plain(fragment: str) -> str:
    return re.sub(r"<[^>]+>", "", fragment).strip()


def _number(body: str) -> tuple[str, list[dict]]:
    """Give each part and step an id and each step its number, and list them for the contents."""
    for name, tag in (("part", '<section class="part"'), ("step", '<article class="step"')):
        heads = sum(1 for m in HEADING.finditer(body) if m[name] is not None)
        if body.count(tag) != heads:
            raise Hiss(f"Each {name} must open with {tag}> followed straight away by its {'h2' if name == 'part' else 'h3'} heading")
    if body.count("<article") != body.count("</article>"):
        raise Hiss("Each step needs a closing </article>")
    parts: list[dict] = []
    steps = 0

    def replace(match: re.Match) -> str:
        nonlocal steps
        if match["part"] is not None:
            parts.append({"id": f"p{len(parts) + 1}", "title": _plain(match["part"]), "steps": []})
            return f'<section class="part" id="{parts[-1]["id"]}"><h2>{match["part"]}</h2>'
        if not parts:
            raise Hiss("Each step must sit inside a part")
        steps += 1
        parts[-1]["steps"].append({"id": f"s{steps}", "number": steps, "title": _plain(match["step"])})
        return f'<article class="step" id="s{steps}"><div class="num">{steps}</div><div class="step-body"><h3>{match["step"]}</h3>'

    return HEADING.sub(replace, body).replace("</article>", "</div></article>"), parts


def _pack_images(body: str, folder: Path, root: Path) -> str:
    def replace(match: re.Match) -> str:
        tag = match[0]
        if not re.search(r'\salt="', tag):
            raise Hiss(f"This image needs alt text describing it: {tag}")
        src = re.search(r'\ssrc="([^"]*)"', tag)
        if not src:
            raise Hiss(f"This image has no src: {tag}")
        if src[1].startswith("data:"):
            return tag
        if re.match(r"[a-z][a-z0-9+.-]*:|//", src[1], re.I):
            raise Hiss(f"Images must be files in the project, so the walkthrough works offline: {src[1]}")
        path = (folder / src[1]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise Hiss(f"No image at {src[1]}")
        kind = IMAGE_TYPES.get(path.suffix.lower())
        if not kind:
            raise Hiss(f"Images must be one of {', '.join(sorted(IMAGE_TYPES))}: {src[1]}")
        data = base64.b64encode(path.read_bytes()).decode()
        return tag.replace(src[0], f' src="data:{kind};base64,{data}"')

    return re.sub(r"<img\b[^>]*>", replace, body)


def _contents(parts: list[dict]) -> str:
    groups = []
    for part in parts:
        link = f'<h2><a href="#{part["id"]}">{html.escape(part["title"], quote=False)}</a></h2>'
        items = "".join(f'<li><a href="#{s["id"]}"><span>{s["number"]}</span>{html.escape(s["title"], quote=False)}</a></li>' for s in part["steps"])
        groups.append(link + (f"<ol>{items}</ol>" if items else ""))
    return "".join(groups)


def build(project: Project, source: str, title: str, kicker: str | None = None) -> dict:
    path = (project.root / source).resolve()
    if not path.is_file():
        raise Hiss(f"No walkthrough body at {source}")
    if not path.name.endswith(BODY_SUFFIX):
        raise Hiss(f"Walkthrough bodies are named NAME{BODY_SUFFIX}, got {path.name}")
    body = path.read_text()
    if re.search(r"<script\b|\son[a-z]+\s*=", body, re.I):
        raise Hiss("Walkthroughs can't contain scripts, because they open inside Calipurr's own page")
    numbered, parts = _number(body)
    if not parts:
        raise Hiss('A walkthrough needs at least one <section class="part">')
    packed = _pack_images(numbered, path.parent, project.root)
    style = (resources.files("calipurr") / "web" / "walkthrough.css").read_text()
    eyebrow = f'<div class="eyebrow">{html.escape(kicker)}</div>' if kicker else ""
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>
{style}</style>
</head>
<body>
<div class="wrap">
<nav class="toc" aria-label="Contents">{_contents(parts)}</nav>
<main>
<header class="hero">{eyebrow}<h1>{html.escape(title)}</h1></header>
{packed}
<footer class="made">Built with Calipurr.</footer>
</main>
</div>
</body>
</html>
"""
    target = project.walkthroughs_dir / f"{path.name.removesuffix(BODY_SUFFIX)}.html"
    _write_atomic(target, page)
    return {"file": target.relative_to(project.root).as_posix(), "parts": len(parts), "steps": sum(len(p["steps"]) for p in parts)}
