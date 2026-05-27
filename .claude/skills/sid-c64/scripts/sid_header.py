"""Shared PSID/RSID header parsing and serialization.

Reference: PSID v2NG specification, https://www.hvsc.c64.org/download/C64Music/DOCUMENTS/SID_file_format.txt
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional


HEADER_V1_SIZE = 0x76
HEADER_V2PLUS_SIZE = 0x7C


def _decode_cstr(b: bytes) -> str:
    end = b.find(b"\x00")
    if end >= 0:
        b = b[:end]
    try:
        return b.decode("cp1252")
    except UnicodeDecodeError:
        return b.decode("latin-1", errors="replace")


def _encode_cstr(s: str, length: int) -> bytes:
    raw = s.encode("cp1252", errors="replace")[: length - 1]
    return raw + b"\x00" * (length - len(raw))


@dataclass
class SidHeader:
    magic: str = "PSID"
    version: int = 2
    data_offset: int = HEADER_V2PLUS_SIZE
    load_address: int = 0
    init_address: int = 0
    play_address: int = 0
    songs: int = 1
    start_song: int = 1
    speed: int = 0
    name: str = ""
    author: str = ""
    released: str = ""
    flags: int = 0
    start_page: int = 0
    page_length: int = 0
    second_sid_address: int = 0
    third_sid_address: int = 0
    raw_header: bytes = field(default=b"", repr=False)
    data: bytes = field(default=b"", repr=False)

    @classmethod
    def parse(cls, blob: bytes) -> "SidHeader":
        if len(blob) < HEADER_V1_SIZE:
            raise ValueError(f"file too small ({len(blob)} bytes) to be a SID")
        magic = blob[0:4].decode("ascii", errors="replace")
        if magic not in ("PSID", "RSID"):
            raise ValueError(f"bad magic {magic!r}, expected PSID or RSID")

        version, data_offset, load, init, play, songs, start_song = struct.unpack(
            ">HHHHHHH", blob[4:18]
        )
        speed = struct.unpack(">I", blob[18:22])[0]
        name = _decode_cstr(blob[0x16:0x36])
        author = _decode_cstr(blob[0x36:0x56])
        released = _decode_cstr(blob[0x56:0x76])

        h = cls(
            magic=magic,
            version=version,
            data_offset=data_offset,
            load_address=load,
            init_address=init,
            play_address=play,
            songs=songs,
            start_song=start_song,
            speed=speed,
            name=name,
            author=author,
            released=released,
        )
        if version >= 2 and data_offset >= HEADER_V2PLUS_SIZE:
            h.flags = struct.unpack(">H", blob[0x76:0x78])[0]
            h.start_page = blob[0x78]
            h.page_length = blob[0x79]
            h.second_sid_address = blob[0x7A]
            h.third_sid_address = blob[0x7B]

        h.raw_header = blob[:data_offset]
        h.data = blob[data_offset:]
        return h

    def to_bytes(self) -> bytes:
        size = HEADER_V2PLUS_SIZE if self.version >= 2 else HEADER_V1_SIZE
        buf = bytearray(size)
        buf[0:4] = self.magic.encode("ascii")
        struct.pack_into(
            ">HHHHHHH",
            buf,
            4,
            self.version,
            size,
            self.load_address,
            self.init_address,
            self.play_address,
            self.songs,
            self.start_song,
        )
        struct.pack_into(">I", buf, 18, self.speed)
        buf[0x16:0x36] = _encode_cstr(self.name, 32)
        buf[0x36:0x56] = _encode_cstr(self.author, 32)
        buf[0x56:0x76] = _encode_cstr(self.released, 32)
        if self.version >= 2:
            struct.pack_into(">H", buf, 0x76, self.flags)
            buf[0x78] = self.start_page & 0xFF
            buf[0x79] = self.page_length & 0xFF
            buf[0x7A] = self.second_sid_address & 0xFF
            buf[0x7B] = self.third_sid_address & 0xFF
        return bytes(buf) + self.data

    # --- flag accessors (PSID v2NG) ---

    @property
    def is_mus_data(self) -> bool:
        return bool(self.flags & 0x01)

    @property
    def psid_specific(self) -> bool:
        """Bit 1: PSID=PlaySID samples, RSID=C64 BASIC executable."""
        return bool(self.flags & 0x02)

    @property
    def clock(self) -> str:
        return {0: "unknown", 1: "PAL", 2: "NTSC", 3: "PAL+NTSC"}[(self.flags >> 2) & 0x3]

    @staticmethod
    def _model(bits: int) -> str:
        return {0: "unknown", 1: "MOS6581", 2: "MOS8580", 3: "6581+8580"}[bits & 0x3]

    @property
    def sid_model(self) -> str:
        return self._model(self.flags >> 4)

    @property
    def second_sid_model(self) -> str:
        return self._model(self.flags >> 6)

    @property
    def third_sid_model(self) -> str:
        return self._model(self.flags >> 8)


def actual_load_address(h: SidHeader) -> int:
    """The C64 RAM address where the data is actually loaded."""
    if h.load_address != 0:
        return h.load_address
    if len(h.data) < 2:
        return 0
    return h.data[0] | (h.data[1] << 8)
