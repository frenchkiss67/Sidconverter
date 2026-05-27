"""Unified `sidconverter` CLI.

Subcommands:
    info       Print PSID/RSID metadata
    render     Render a .sid to WAV/MP3 (via sidplayfp)
    convert    Convert between PSID and RSID magic
    from-audio Synthesize a basic .sid from audio
    gui        Launch the Tkinter GUI
"""
from __future__ import annotations

import argparse
import sys

from . import __version__, audio_to_sid, format_convert, info, render, validate


def _gui_subparser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("gui", help="launch the Tkinter GUI")
    p.set_defaults(func=_run_gui)
    return p


def _run_gui(_args: argparse.Namespace) -> int:
    from . import gui  # imported lazily so headless CLI use doesn't need tkinter
    return gui.main()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sidconverter",
        description="Commodore 64 SID file toolkit",
    )
    p.add_argument("--version", action="version", version=f"sidconverter {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)
    info.add_parser(sub)
    validate.add_parser(sub)
    render.add_parser(sub)
    format_convert.add_parser(sub)
    audio_to_sid.add_parser(sub)
    _gui_subparser(sub)
    return p


def main(argv: list[str] | None = None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
