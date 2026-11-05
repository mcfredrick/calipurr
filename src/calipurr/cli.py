from __future__ import annotations

import argparse
import json
import sys

from . import __version__, profiles
from .profiles import ASSUMED, MEASURED, ProfileError


def _interview(name: str, kind: str) -> None:
    print(f"Let's get to know {name}. Press Enter to skip anything you haven't measured yet.")
    try:
        for field in profiles.fields_for(kind):
            hint = f" [{'/'.join(field.choices)}]" if field.choices else ""
            while raw := input(f"{field.ask}{hint}: ").strip():
                try:
                    field.parse(raw)
                except ProfileError as err:
                    print(err)
                    continue
                answer = input("Did you measure or verify that? [Y/n]: ").strip().lower()
                profiles.feed(name, field.key, raw, ASSUMED if answer.startswith("n") else MEASURED)
                break
    except EOFError:
        print()


def _adopt(args: argparse.Namespace) -> int:
    profiles.adopt(args.name, args.kind)
    if sys.stdin.isatty():
        _interview(args.name, args.kind)
    return _report_hungry(args, f"Welcome home, {args.name}.")


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
    return _report_hungry(args, "Nom.")


def _hungry(args: argparse.Namespace) -> int:
    return 1 if _report_hungry(args, f"{args.name} is purring. Nothing needed.") else 0


def _report_hungry(args: argparse.Namespace, content: str) -> int:
    """Print what's still needed and return how many values that is."""
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="calipurr", description="Keep your machines' real specs, measured and fed.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)

    def command(name, alias, handler, help_text):
        p = sub.add_parser(name, aliases=[alias], help=f"{help_text} (alias: {alias})")
        p.add_argument("--json", action="store_true", help="machine-readable output")
        p.set_defaults(handler=handler)
        return p

    p = command("adopt", "add", _adopt, "add a machine profile")
    p.add_argument("name")
    p.add_argument("--kind", required=True, choices=sorted(profiles.KINDS))

    command("litter", "list", _litter, "list your machines")

    p = command("vet", "show", _vet, "show a machine's values and where they came from")
    p.add_argument("name")

    p = command("feed", "set", _feed, "record a value, treated as measured unless --assumed")
    p.add_argument("name")
    p.add_argument("key")
    p.add_argument("value")
    p.add_argument("--assumed", action="store_true", help="the value is a guess or a spec sheet number")
    p.add_argument("--note", help="how you got this value")

    p = command("hungry", "missing", _hungry, "list values still needed; exits 1 if any are")
    p.add_argument("name")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        status = args.handler(args)
    except ProfileError as err:
        print(f"calipurr: {err}", file=sys.stderr)
        return 2
    return status if args.handler is _hungry else 0
