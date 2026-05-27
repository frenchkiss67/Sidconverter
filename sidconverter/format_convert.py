"""sidconverter convert — flip PSID <-> RSID magic with safety warnings."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .header import SidHeader, actual_load_address


def _in_rom(addr: int) -> bool:
    return 0xA000 <= addr <= 0xBFFF or 0xD000 <= addr <= 0xFFFF


def warnings_for(h: SidHeader, target: str) -> list[str]:
    warns: list[str] = []
    if target == "RSID":
        if h.play_address != 0:
            warns.append(
                f"PSID play address ${h.play_address:04X} is non-zero; RSID requires play=0 "
                "and a self-driven player (CIA IRQ)."
            )
        if h.speed != 0:
            warns.append(
                f"speed ${h.speed:08X} is non-zero; RSID requires speed=0 (no per-tune speed)."
            )
        load = actual_load_address(h)
        if load < 0x07E8:
            warns.append(
                f"load address ${load:04X} is below $07E8 — RSID forbids loading into the "
                "zero/stack pages or BASIC pointers."
            )
        if h.init_address and (_in_rom(h.init_address) or h.init_address < 0x07E8):
            warns.append(
                f"init address ${h.init_address:04X} is in ROM or below $07E8 — invalid for RSID."
            )
        if h.psid_specific and h.init_address != 0:
            # bit 1 set means C64 BASIC for RSID; requires init=0.
            warns.append(
                "C64 BASIC flag is set but init address is non-zero; RSID requires init=0 "
                "when the BASIC bit is set."
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


_OPPOSITE = {"PSID": "RSID", "RSID": "PSID"}


def _add_args(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument(
        "--to", choices=("PSID", "RSID"), default=None,
        help="target format (default: opposite of the input's magic)",
    )
    p.add_argument("--force", action="store_true")
    return p


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("convert", help="convert between PSID and RSID")
    _add_args(p)
    p.set_defaults(func=run)
    return p


def run(args: argparse.Namespace) -> int:
    try:
        h = SidHeader.parse(args.input.read_bytes())
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    target = args.to or _OPPOSITE.get(h.magic)
    if target is None:
        print(f"error: cannot infer target from magic {h.magic!r}", file=sys.stderr)
        return 1
    if args.to is None:
        print(f"note: inferred --to {target} (input is {h.magic})")

    if h.magic == target:
        print(f"note: file is already {target}; rewriting bytes unchanged")

    warns = warnings_for(h, target)
    for w in warns:
        print(f"warning: {w}", file=sys.stderr)
    if warns and not args.force:
        print("refusing to convert; pass --force to override.", file=sys.stderr)
        return 2

    h = convert(h, target)
    args.output.write_bytes(h.to_bytes())
    print(f"wrote {args.output} as {target} v{h.version}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return run(_add_args(argparse.ArgumentParser(description="Convert PSID <-> RSID")).parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
