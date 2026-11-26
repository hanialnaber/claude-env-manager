"""Command line: `claude-env serve | list | check`.

`list` and `check` never print values, only names, sources and lengths.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__, core


def _project(arg: str | None) -> Path | None:
    if arg == "none":
        return None
    if arg is None and getattr(sys, "frozen", False):
        # Desktop app: the working folder is meaningless; pick the project in the UI.
        return None
    p = Path(arg or os.getcwd()).expanduser()
    if not p.is_dir():
        print(f"Project folder not found: {p}", file=sys.stderr)
        raise SystemExit(2)
    return p.resolve()


def cmd_list(args) -> int:
    scopes = core.build_scopes(_project(args.project))
    for s in scopes:
        if s.id == "shell" and not args.shell:
            continue
        where = f"  ({s.path})" if s.path else ""
        print(f"\n{s.label}{where}")
        if s.error:
            print(f"  ! {s.error}")
        if not s.env:
            print("  (nothing set)")
        for n, v in sorted(s.env.items()):
            print(f"  {n:<36} {core.mask(v)}  {len(v)} chars")
    print("\nWhat Claude will see (settings files):")
    for r in core.effective(scopes):
        extra = f", overrides {', '.join(r.shadowed)}" if r.shadowed else ""
        print(f"  {r.name:<36} from {r.source}{extra}")
    return 0


def cmd_check(args) -> int:
    scopes = core.build_scopes(_project(args.project))
    missing = 0
    for name in args.names:
        core.validate_name(name)
        r = core.resolve(scopes, name)
        if r.present:
            extra = f" (overrides {', '.join(r.shadowed)})" if r.shadowed else ""
            print(f"{name}: present, {r.length} characters, from {r.source}{extra}")
        else:
            missing += 1
            print(f"{name}: MISSING")
        for note in core.name_notes(name, r.source):
            print(f"  note: {note}")
    return 1 if missing else 0


def cmd_serve(args) -> int:
    from .server import serve

    serve(_project(args.project), port=args.port, open_browser=not args.no_browser)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="claude-env",
        description="Add, check and manage the environment variables Claude Code uses. Local only.",
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("serve", help="open the web UI (default)")
    p.add_argument("--project", help="project folder (default: current folder; 'none' for user scope only)")
    p.add_argument("--port", type=int, default=0, help="port on 127.0.0.1 (default: a free one)")
    p.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("list", help="list variables per scope, values masked")
    p.add_argument("--project")
    p.add_argument("--shell", action="store_true", help="also list shell variables")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("check", help="is NAME visible? prints source and length, never the value")
    p.add_argument("names", nargs="+")
    p.add_argument("--project")
    p.set_defaults(func=cmd_check)

    args = ap.parse_args(argv)
    if not args.cmd:
        args = ap.parse_args(["serve", *(argv or sys.argv[1:])])
    try:
        return args.func(args)
    except core.SettingsError as exc:
        print(str(exc), file=sys.stderr)
        return 2
