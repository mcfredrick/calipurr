from __future__ import annotations

import argparse
import json
import sys
import webbrowser

from . import __version__, profiles
from .errors import Hiss, NeedsConfirmation
from .profiles import ASSUMED, MEASURED
from .project import Project


def _interview(name: str, kind: str) -> None:
    print(f"Let's get to know {name}. Press Enter to skip anything you haven't measured yet.")
    try:
        for field in profiles.fields_for(kind):
            hint = f" [{'/'.join(field.choices)}]" if field.choices else ""
            while raw := input(f"{field.ask}{hint}: ").strip():
                try:
                    field.parse(raw)
                except Hiss as err:
                    print(err)
                    continue
                answer = input("Did you measure or verify that? [Y/n]: ").strip().lower()
                profiles.feed(name, field.key, raw, ASSUMED if answer.startswith("n") else MEASURED)
                break
    except EOFError:
        print()


def _report_hungry(args: argparse.Namespace, content: str) -> int:
    """Print what a machine still needs and return how many values that is."""
    needed = profiles.hungry(profiles.load(args.name))
    if args.json:
        print(json.dumps({"machine": args.name, "needed": needed}))
    elif needed:
        print(f"{args.name} still needs:")
        for key, ask in needed.items():
            print(f"  {key}: {ask}")
    else:
        print(content)
    return len(needed)


def _adopt(args: argparse.Namespace) -> int:
    profiles.adopt(args.name, args.kind)
    if sys.stdin.isatty():
        _interview(args.name, args.kind)
    _report_hungry(args, f"Welcome home, {args.name}.")
    return 0


def _litter(args: argparse.Namespace) -> int:
    machines = {n: profiles.load(n) for n in profiles.litter()}
    if args.json:
        print(json.dumps({n: {"kind": p["kind"], "needed": sorted(profiles.hungry(p))} for n, p in machines.items()}))
    elif not machines:
        print("The litter is empty. Adopt a machine: calipurr adopt NAME --kind cnc")
    else:
        for name, profile in machines.items():
            print(f"{name}  ({profile['kind']}, {len(profiles.hungry(profile))} values needed)")
    return 0


def _vet(args: argparse.Namespace) -> int:
    profile = profiles.load(args.name)
    if args.json:
        print(json.dumps(profile))
        return 0
    print(f"{args.name} ({profile['kind']})")
    for key, entry in profile["fields"].items():
        value = entry.get("value", "-")
        dated = f", {entry['date']}" if "date" in entry else ""
        print(f"  {key}: {value}  [{entry['status']}{dated}]")
    return 0


def _feed(args: argparse.Namespace) -> int:
    profiles.feed(args.name, args.key, args.value, ASSUMED if args.assumed else MEASURED, args.note)
    _report_hungry(args, "Nom.")
    return 0


def _hungry(args: argparse.Namespace) -> int:
    return 1 if _report_hungry(args, f"{args.name} is purring. Nothing needed.") else 0


def _point(raw: str) -> list[float]:
    try:
        return [float(part) for part in raw.split(",")]
    except ValueError:
        raise Hiss(f"--at takes comma-separated numbers, got {raw!r}") from None


def _shown(entry: dict) -> str:
    value = entry["value"]
    return value if isinstance(value, str) else f"{value:g} {entry.get('unit', 'mm')}"


def _meow(args: argparse.Namespace) -> int:
    entry = Project(args.project).meow(
        args.key,
        args.name,
        args.ask,
        args.unit,
        kind="choice" if args.choice else args.kind,
        choices=args.choice,
        why=args.why,
        required=not args.optional,
        show=args.show,
        at=[_point(raw) for raw in args.at] if args.at else None,
    )
    if args.json:
        print(json.dumps({args.key: entry}))
    else:
        print(f"Meow. Asked for {args.key}.")
    return 0


def _bowl(args: argparse.Namespace) -> int:
    project = Project(args.project)
    params = project.params()
    if args.json:
        needed = sorted(project.hungry())
        print(json.dumps({"params": params, "needed": needed, "ready": not needed, "next": project.next_step()}))
    elif not params:
        print("Nothing asked yet. Ask for a value: calipurr meow KEY --name NAME --ask QUESTION")
    else:
        for key, entry in params.items():
            value = _shown(entry) if "value" in entry else "-"
            optional = ", optional" if not entry.get("required", True) else ""
            print(f"{key}: {value}  [{entry['status']}{optional}]  {entry.get('name', '')}")
    return 1 if project.hungry() else 0


def _treat(args: argparse.Namespace) -> int:
    entry = Project(args.project).answer(args.key, args.value, ASSUMED if args.assumed else MEASURED, args.note)
    print(json.dumps({args.key: entry}) if args.json else f"Nom. {args.key} is {_shown(entry)}, {entry['status']}.")
    return 0


def _nudge(args: argparse.Namespace) -> int:
    project = Project(args.project)
    if args.clear or args.text:
        project.nudge(None if args.clear else args.text)
    current = project.next_step()
    print(json.dumps({"next": current}) if args.json else current or "No next step set.")
    return 0


def _dots(args: argparse.Namespace) -> int:
    dots = Project(args.project).dots()
    if args.json:
        print(json.dumps({"dots": dots}))
    elif not dots:
        print("No laser dots yet.")
    else:
        for dot in dots:
            where = ", ".join(f"{v:g}" for v in dot["position"])
            print(f"Dot {dot['id']} on {dot['file']} at ({where}): {dot['text'] or '(no comment)'}")
    return 0


def _print_gauge(record: dict) -> None:
    end = "mouth" if record["kind"] == "socket" else "tip"
    print(f"{record['file']}: a {record['kind']} gauge. Step A is at the {end}.")
    for step in record["steps"]:
        print(f"  {step['letter']}  {step['size_mm']:g} mm")
    print("After printing, report the step that fit: calipurr kitten report " f"{record['name']} --step LETTER --measured MM")


def _gauge(args: argparse.Namespace) -> int:
    from . import kitten

    record = kitten.make_gauge(
        Project(args.project),
        args.start,
        args.stop,
        args.step,
        kind=args.kind,
        step_height=args.step_height,
        labels=not args.no_labels,
        target=args.target,
        name=args.kitten_name,
        force=args.force,
    )
    print(json.dumps(record)) if args.json else _print_gauge(record)
    return 0


def _cut(args: argparse.Namespace) -> int:
    from . import kitten

    record = kitten.make_cut(
        Project(args.project), args.file, args.keep_above, args.keep_below, args.kitten_name, args.force
    )
    print(json.dumps(record) if args.json else f"Made {record['file']} from {record['source']}.")
    return 0


def _report(args: argparse.Namespace) -> int:
    from . import kitten

    record = kitten.report(
        Project(args.project),
        args.kitten_name,
        args.step,
        args.measured,
        args.material,
        args.machine,
        args.note,
        args.confirm,
    )
    if args.json:
        print(json.dumps(record))
    else:
        result = record["report"]
        print(f"Nom. Step {result['letter']}: modeled {result['modeled_mm']:g} mm, measured {result['measured_mm']:g} mm.")
        if record["for"]:
            print(f"{record['for']} is now {result['modeled_mm']:g} mm, measured.")
    return 0


def _kittens(args: argparse.Namespace) -> int:
    from . import kitten

    records = kitten.kittens(Project(args.project))
    if args.json:
        print(json.dumps({"kittens": records}))
    elif not records:
        print("No kittens yet.")
    else:
        for record in records:
            result = record.get("report")
            outcome = f", step {result['letter']} fit" if result else ""
            print(f"{record['name']}  ({record['type']}{outcome})")
    return 0


def _purrflight(args: argparse.Namespace) -> int:
    from . import purrflight

    project = Project(args.project)
    profile = profiles.load(args.machine) if args.machine else None
    result = purrflight.run(project.resolve_file(args.file), args.machine, profile)
    if args.json:
        print(json.dumps(result))
    else:
        print(f"{result['file']}: {result['size_mm']} mm")
        for check in result["checks"]:
            print(f"  [{check['status']}] {check['label']}: {check['detail']}")
    return 1 if result["overall"] == "fail" else 0


def _serve(args: argparse.Namespace) -> int:
    from .server import make_server

    server = make_server(Project(args.project), args.port, args.build)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Emily is watching {Project(args.project).root} at {url}", flush=True)
    print("Press Ctrl-C to stop.", flush=True)
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="calipurr", description="Measure twice, purr once.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add(group, name, alias, handler, help_text, project=False):
        aliases = [alias] if alias else []
        suffix = f" (alias: {alias})" if alias else ""
        p = group.add_parser(name, aliases=aliases, help=f"{help_text}{suffix}")
        p.add_argument("--json", action="store_true", help="machine-readable output")
        if project:
            p.add_argument("--project", default=".", help="project folder (default: current folder)")
        p.set_defaults(handler=handler)
        return p

    p = add(sub, "adopt", "add", _adopt, "add a machine profile")
    p.add_argument("name")
    p.add_argument("--kind", required=True, choices=sorted(profiles.KINDS))

    add(sub, "litter", "list", _litter, "list your machines")

    p = add(sub, "vet", "show", _vet, "show a machine's values and where they came from")
    p.add_argument("name")

    p = add(sub, "feed", "set", _feed, "record a machine value, treated as measured unless --assumed")
    p.add_argument("name")
    p.add_argument("key")
    p.add_argument("value")
    p.add_argument("--assumed", action="store_true", help="the value is a guess or a spec sheet number")
    p.add_argument("--note", help="how you got this value")

    p = add(sub, "hungry", "missing", _hungry, "list machine values still needed; exits 1 if any are")
    p.add_argument("name")

    p = add(sub, "meow", "ask", _meow, "ask the user a question in the GUI", project=True)
    p.add_argument("key")
    p.add_argument("--name", required=True, help="a short name for what you're asking")
    p.add_argument("--ask", required=True, help="the question, with how to measure or decide it")
    p.add_argument("--unit", default="mm")
    p.add_argument("--kind", default="number", choices=["number", "text"], help="the type of answer (default: number)")
    p.add_argument("--choice", action="append", help="an allowed answer; repeat for each one")
    p.add_argument("--why", help="why you need this, shown beside the question")
    p.add_argument("--optional", action="store_true", help="useful, but it won't block progress")
    p.add_argument("--show", help="the photo or model that shows it; the GUI opens this when it asks")
    p.add_argument(
        "--at",
        action="append",
        metavar="X,Y[,Z]",
        help="where on --show: once for a spot, twice for a dimension's two ends. "
        "Photos run 0 to 1 across and down; models use model coordinates. Write --at=-1,2,3 for negatives",
    )

    add(sub, "bowl", "params", _bowl, "list questions and answers; exits 1 if required ones are unanswered", project=True)

    p = add(sub, "nudge", "next", _nudge, "tell the user what to do next, shown at the top of the GUI", project=True)
    p.add_argument("text", nargs="?")
    p.add_argument("--clear", action="store_true", help="remove the current next step")

    p = add(sub, "treat", "answer", _treat, "record an answer, treated as measured unless --assumed", project=True)
    p.add_argument("key")
    p.add_argument("value")
    p.add_argument("--assumed", action="store_true", help="the value is a guess")
    p.add_argument("--note", help="how you got this value")

    add(sub, "dots", "comments", _dots, "read the user's laser dot comments", project=True)

    kitten = sub.add_parser("kitten", aliases=["test-piece"], help="make and report small test pieces (alias: test-piece)")
    kitten_sub = kitten.add_subparsers(dest="kitten_command", required=True)

    p = add(kitten_sub, "gauge", None, _gauge, "make a lettered stepped gauge", project=True)
    p.add_argument("--from", dest="start", type=float, required=True, help="smallest size in mm")
    p.add_argument("--to", dest="stop", type=float, required=True, help="largest size in mm")
    p.add_argument("--step", type=float, default=0.2, help="size change per step in mm (default: 0.2)")
    p.add_argument("--kind", default="plug", choices=["plug", "socket"], help="plug goes inside something, socket goes around it")
    p.add_argument("--step-height", type=float, default=6.0, help="height of each step in mm (default: 6)")
    p.add_argument("--no-labels", action="store_true", help="leave off the letters, for steps too small to label")
    p.add_argument("--for", dest="target", help="the part dimension this gauge will settle")
    p.add_argument("--name", dest="kitten_name")
    p.add_argument("--force", action="store_true", help="replace a kitten with the same name")

    p = add(kitten_sub, "cut", None, _cut, "slice a feature out of a model, keeping its geometry", project=True)
    p.add_argument("file")
    p.add_argument("--keep-above", type=float, help="keep what's above this Z height in mm")
    p.add_argument("--keep-below", type=float, help="keep what's below this Z height in mm")
    p.add_argument("--name", dest="kitten_name")
    p.add_argument("--force", action="store_true", help="replace a kitten with the same name")

    p = add(kitten_sub, "report", None, _report, "record which gauge step fit", project=True)
    p.add_argument("kitten_name", metavar="name")
    p.add_argument("--step", required=True, help="the letter of the step that fit")
    p.add_argument("--measured", type=float, required=True, help="what that step measures with calipers, in mm")
    p.add_argument("--material")
    p.add_argument("--machine")
    p.add_argument("--note")
    p.add_argument("--confirm", action="store_true", help="save even if the measurement doesn't match the step")

    add(kitten_sub, "list", None, _kittens, "list test pieces and their results", project=True)

    p = add(sub, "purrflight", "check", _purrflight, "check a model before making it; exits 1 on a failure", project=True)
    p.add_argument("file")
    p.add_argument("--machine", help="also check it fits this machine")

    p = sub.add_parser("serve", aliases=["gui"], help="open the visual interface (alias: gui)")
    p.add_argument("--project", default=".", help="project folder (default: current folder)")
    p.add_argument("--port", type=int, default=0, help="port on this computer (default: any free port)")
    p.add_argument("--build", help="command to rebuild the model after a value changes, run in the project folder")
    p.add_argument("--no-open", action="store_true", help="don't open a browser")
    p.set_defaults(handler=_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return args.handler(args)
    except NeedsConfirmation as err:
        print(f"calipurr: {err} Pass --confirm if it's right.", file=sys.stderr)
        return 2
    except Hiss as err:
        print(f"calipurr: {err}", file=sys.stderr)
        return 2
