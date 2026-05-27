#!/usr/bin/env python3
"""Convert a SID file between PSID and RSID magic.

This only rewrites the header magic and adjusts the PSID-specific flag
(bit 1 of the flags word). The 6510 code is left untouched, so a PSID
that relies on the C64 kernal being replaced with PlaySID hooks will
not necessarily run as RSID. The script prints warnings for the cases
the PSID v2NG spec explicitly disallows.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sid_header import SidHeader, actual_load_address


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
    elif target == "PSID":
        # PSID is more permissive; nothing strictly invalid going this way.
        pass
    return warns


def main() -> int:
    p = argparse.ArgumentParser(description="Convert PSID <-> RSID")
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--to", choices=("PSID", "RSID"), required=True)
    p.add_argument(
        "--force", action="store_true", help="convert even if warnings are emitted"
    )
    args = p.parse_args()

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

    h.magic = args.to
    if h.version < 2:
        # bumping to v2 lets us carry flags; safe because the layout is a superset
        h.version = 2
        h.data_offset = 0x7C

    # bit 1 differs: PSID = PlaySID samples, RSID = BASIC. We have no way to
    # know whether the original used either, so we just clear it on conversion
    # to be safe. Caller can re-set explicitly if needed.
    h.flags &= ~0x02

    args.output.write_bytes(h.to_bytes())
    print(f"wrote {args.output} as {args.to} v{h.version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
