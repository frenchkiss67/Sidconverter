#!/usr/bin/env python3
"""Print metadata of a PSID/RSID file.

Usage:
    python3 sid_info.py path/to/tune.sid [--json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

from sid_header import SidHeader, actual_load_address


def hvsc_songlengths_hash(h: SidHeader) -> str:
    """SHA-1 used by HVSC's Songlengths.md5 (despite the filename).

    The hash covers: load address (little-endian, 2 bytes) + init + play
    + songs + speed (big-endian!) + the binary data after the load
    address bytes. See the PSID v2NG spec, section 6.
    """
    load = actual_load_address(h)
    data = h.data
    if h.load_address == 0 and len(data) >= 2:
        data = data[2:]
    m = hashlib.sha1()
    m.update(struct.pack("<H", load))
    m.update(struct.pack("<H", h.init_address))
    m.update(struct.pack("<H", h.play_address))
    m.update(struct.pack("<H", h.songs))
    for i in range(h.songs):
        # speed bit per song, big-endian byte order of the speed dword
        speed_byte = 60 if (h.speed >> i) & 1 else 0
        m.update(bytes([speed_byte]))
    m.update(data)
    return m.hexdigest()


def to_dict(h: SidHeader, path: Path) -> dict:
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
        "hvsc_sha1": hvsc_songlengths_hash(h),
    }


def print_pretty(d: dict) -> None:
    print(f"{d['magic']} v{d['version']}  ({d['data_size']} bytes of 6510 code)")
    print(f"  file:       {d['path']}")
    print(f"  name:       {d['name']!r}")
    print(f"  author:     {d['author']!r}")
    print(f"  released:   {d['released']!r}")
    print(
        f"  load=${d['load_address'][1:]}  init={d['init_address']}  play={d['play_address']}"
        + ("  (load addr in data)" if not d["load_address_in_header"] else "")
    )
    print(f"  songs:      {d['songs']}  (start #{d['start_song']})")
    f = d["flags"]
    print(
        f"  flags:      {f['raw']}  clock={f['clock']}  sid={f['sid_model']}"
        + (f"  +2nd={f['second_sid_model']}" if d["second_sid_address"] else "")
        + (f"  +3rd={f['third_sid_model']}" if d["third_sid_address"] else "")
        + ("  MUS" if f["mus_data"] else "")
    )
    print(f"  hvsc sha1:  {d['hvsc_sha1']}")


def main() -> int:
    p = argparse.ArgumentParser(description="Inspect a PSID/RSID file")
    p.add_argument("path", type=Path)
    p.add_argument("--json", action="store_true", help="machine-readable output")
    args = p.parse_args()

    try:
        blob = args.path.read_bytes()
        h = SidHeader.parse(blob)
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    d = to_dict(h, args.path)
    if args.json:
        print(json.dumps(d, indent=2))
    else:
        print_pretty(d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
