"""sidconverter convert — flip PSID <-> RSID magic with safety warnings."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .header import SidHeader, actual_load_address


def warnings_for(h: SidHeader, target: str) -> list[str]:
    warns: list[str] = []
    if target == "RSID":
        if h.play_address != 0:
            warns.append(
                f"PSID play address ${h.play_address:04X} is non-zero; RSID requires play=0 "
                "and a self-driven player (CIA IRQ)."
            )
        if actual_load_address(h) < 0x07E8:
            warns.append(
                f"load address ${actual_load_address(h):04X} is below $07E8 — RSID forbids "
                "loading into the zero/stack pages or BASIC pointers."
            )
        if h.is_mus_data:
            warns.append("MUS data flag set; MUS is only valid for PSID.")
    return warns


def convert(h: SidHeader, target: str) -> SidHeader:
    h.magic = target
    if h.version < 2:
        h.version = 2
        h.data_offset = 0x7C
    # Bit 1 differs in meaning between PSID and RSID. Clear it on conversion.
    h.flags &= ~0x02
    return h


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("convert", help="convert between PSID and RSID")
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--to", choices=("PSID", "RSID"), required=True)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=run)
    return p


def run(args: argparse.Namespace) -> int:
    try:
        h = SidHeader.parse(args.input.read_bytes())
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if h.magic == args.to:
        print(f"note: file is already {args.to}; rewriting bytes unchanged")

    warns = warnings_for(h, args.to)
    for w in warns:
        print(f"warning: {w}", file=sys.stderr)
    if warns and not args.force:
        print("refusing to convert; pass --force to override.", file=sys.stderr)
        return 2

    h = convert(h, args.to)
    args.output.write_bytes(h.to_bytes())
    print(f"wrote {args.output} as {args.to} v{h.version}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Convert PSID <-> RSID")
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--to", choices=("PSID", "RSID"), required=True)
    p.add_argument("--force", action="store_true")
    return run(p.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
