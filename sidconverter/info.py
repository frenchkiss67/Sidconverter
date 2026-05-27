"""sidconverter info — inspect PSID/RSID metadata."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .header import SidHeader, actual_load_address, md5_new, md5_old


def to_dict(h: SidHeader, path: Path, raw: bytes | None = None) -> dict:
    return {
        "path": str(path),
        "magic": h.magic,
        "version": h.version,
        "data_offset": h.data_offset,
        "load_address": f"${actual_load_address(h):04X}",
        "load_address_in_header": h.load_address != 0,
        "init_address": f"${h.init_address:04X}",
        "play_address": f"${h.play_address:04X}",
        "songs": h.songs,
        "start_song": h.start_song,
        "speed": f"${h.speed:08X}",
        "name": h.name,
        "author": h.author,
        "released": h.released,
        "flags": {
            "raw": f"${h.flags:04X}",
            "mus_data": h.is_mus_data,
            "psid_specific": h.psid_specific,
            "clock": h.clock,
            "sid_model": h.sid_model,
            "second_sid_model": h.second_sid_model,
            "third_sid_model": h.third_sid_model,
        },
        "start_page": h.start_page,
        "page_length": h.page_length,
        "second_sid_address": f"${0xD000 | (h.second_sid_address << 4):04X}"
        if h.second_sid_address
        else None,
        "third_sid_address": f"${0xD000 | (h.third_sid_address << 4):04X}"
        if h.third_sid_address
        else None,
        "data_size": len(h.data),
        "md5_old": md5_old(h),
        "md5_new": md5_new(raw) if raw is not None else md5_new(h.to_bytes()),
    }


def format_pretty(d: dict) -> str:
    f = d["flags"]
    lines = [
        f"{d['magic']} v{d['version']}  ({d['data_size']} bytes of 6510 code)",
        f"  file:       {d['path']}",
        f"  name:       {d['name']!r}",
        f"  author:     {d['author']!r}",
        f"  released:   {d['released']!r}",
        f"  load=${d['load_address'][1:]}  init={d['init_address']}  play={d['play_address']}"
        + ("  (load addr in data)" if not d["load_address_in_header"] else ""),
        f"  songs:      {d['songs']}  (start #{d['start_song']})",
        f"  flags:      {f['raw']}  clock={f['clock']}  sid={f['sid_model']}"
        + (f"  +2nd={f['second_sid_model']}" if d["second_sid_address"] else "")
        + (f"  +3rd={f['third_sid_model']}" if d["third_sid_address"] else "")
        + ("  MUS" if f["mus_data"] else ""),
        f"  md5 (old):  {d['md5_old']}",
        f"  md5 (new):  {d['md5_new']}",
    ]
    return "\n".join(lines)


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("info", help="show PSID/RSID metadata")
    p.add_argument("path", type=Path)
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.set_defaults(func=run)
    return p


def run(args: argparse.Namespace) -> int:
    try:
        blob = args.path.read_bytes()
        h = SidHeader.parse(blob)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    d = to_dict(h, args.path, raw=blob)
    print(json.dumps(d, indent=2) if args.json else format_pretty(d))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Inspect a PSID/RSID file")
    p.add_argument("path", type=Path)
    p.add_argument("--json", action="store_true")
    return run(p.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
