"""sidconverter validate — check a SID file against PSID/RSID format rules."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .format_convert import warnings_for
from .header import HEADER_V2PLUS_SIZE, SidHeader, actual_load_address


def lint(h: SidHeader) -> tuple[list[str], list[str]]:
    """Return (errors, warnings). Errors are spec violations, warnings are
    style/portability concerns."""
    errors: list[str] = []
    warnings: list[str] = []

    if h.magic not in ("PSID", "RSID"):
        errors.append(f"unknown magic {h.magic!r}")
    if h.version not in (1, 2, 3, 4):
        errors.append(f"version {h.version} is not in spec (1..4)")
    if h.version >= 2 and h.data_offset < HEADER_V2PLUS_SIZE:
        errors.append(
            f"version {h.version} requires dataOffset >= 0x{HEADER_V2PLUS_SIZE:02X}, "
            f"got 0x{h.data_offset:02X}"
        )
    if h.songs < 1 or h.songs > 256:
        errors.append(f"songs={h.songs} out of valid range 1..256")
    if not 1 <= h.start_song <= max(1, h.songs):
        errors.append(f"startSong={h.start_song} not in 1..songs ({h.songs})")
    if h.load_address == 0 and len(h.data) < 2:
        errors.append("loadAddress=0 but data is too short to contain an embedded address")

    if h.magic == "RSID":
        # RSID spec is stricter; reuse the same checks the converter emits as warnings,
        # but promote them to errors here.
        errors.extend(warnings_for(h, "RSID"))

    # secondary/third SID address sanity (v3+ / v4+)
    for label, byte in (
        ("secondSIDAddress", h.second_sid_address),
        ("thirdSIDAddress", h.third_sid_address),
    ):
        if byte == 0:
            continue
        if byte % 2 != 0:
            errors.append(f"{label}=0x{byte:02X} is odd; spec requires even values")
        if byte < 0x42 or byte > 0xFE or 0x80 <= byte <= 0xDF:
            errors.append(
                f"{label}=0x{byte:02X} is outside the valid SID address range"
            )

    if h.second_sid_address and h.third_sid_address \
            and h.second_sid_address == h.third_sid_address:
        errors.append("thirdSIDAddress must differ from secondSIDAddress")

    # Style/portability warnings
    if h.version == 1 and (h.flags or h.start_page or h.page_length):
        warnings.append("v1 header but v2+ fields are set; consumers will ignore them")
    if h.is_mus_data:
        warnings.append(
            "MUS data flag set; this file needs an external Compute!'s Sidplayer player"
        )
    if not h.name.strip():
        warnings.append("name field is empty")
    if not h.author.strip():
        warnings.append("author field is empty")

    return errors, warnings


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("validate", help="check a SID file against the format spec")
    p.add_argument("path", type=Path)
    p.add_argument("--strict", action="store_true",
                   help="exit non-zero if any warning is emitted")
    p.set_defaults(func=run)
    return p


def run(args: argparse.Namespace) -> int:
    try:
        h = SidHeader.parse(args.path.read_bytes())
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    errors, warnings = lint(h)
    for w in warnings:
        print(f"warning: {w}", file=sys.stderr)
    for e in errors:
        print(f"error: {e}", file=sys.stderr)

    if errors:
        print(f"FAIL  {args.path}: {len(errors)} error(s), {len(warnings)} warning(s)")
        return 2
    if warnings and args.strict:
        print(f"WARN  {args.path}: {len(warnings)} warning(s) (--strict)")
        return 1
    print(f"OK    {args.path}: {h.magic} v{h.version}, load=${actual_load_address(h):04X}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Validate a SID file")
    p.add_argument("path", type=Path)
    p.add_argument("--strict", action="store_true")
    return run(p.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
