"""Round-trip and field-access tests for the PSID/RSID header parser."""
from __future__ import annotations

import hashlib
import struct

import pytest

from sidconverter.header import (
    HEADER_V1_SIZE,
    HEADER_V2PLUS_SIZE,
    SidHeader,
    actual_load_address,
    md5_new,
    md5_old,
)


def _minimal(magic: str = "PSID", version: int = 2) -> SidHeader:
    return SidHeader(
        magic=magic,
        version=version,
        data_offset=HEADER_V2PLUS_SIZE if version >= 2 else HEADER_V1_SIZE,
        load_address=0,
        init_address=0x1000,
        play_address=0x1010,
        songs=1,
        start_song=1,
        speed=0,
        name="Test",
        author="Olivier",
        released="2026",
        flags=0x0014,                         # PAL + MOS6581
        data=struct.pack("<H", 0x1000) + b"\x60\x60\x60",
    )


def test_roundtrip_basic():
    h = _minimal()
    blob = h.to_bytes()
    h2 = SidHeader.parse(blob)
    assert h2.magic == "PSID"
    assert h2.version == 2
    assert h2.init_address == 0x1000
    assert h2.play_address == 0x1010
    assert h2.name == "Test"
    assert h2.author == "Olivier"
    assert h2.released == "2026"
    assert h2.clock == "PAL"
    assert h2.sid_model == "MOS6581"


def test_roundtrip_v1():
    h = _minimal(version=1)
    h.data_offset = HEADER_V1_SIZE
    blob = h.to_bytes()
    assert len(blob) == HEADER_V1_SIZE + len(h.data)
    h2 = SidHeader.parse(blob)
    assert h2.version == 1
    assert h2.flags == 0  # v1 has no flags field


@pytest.mark.parametrize(
    "flags,expected_clock,expected_model",
    [
        (0x0000, "unknown", "unknown"),
        (0x0004, "PAL",     "unknown"),
        (0x0008, "NTSC",    "unknown"),
        (0x000C, "PAL+NTSC", "unknown"),
        (0x0014, "PAL",     "MOS6581"),
        (0x0028, "NTSC",    "MOS8580"),
        (0x0034, "PAL",     "6581+8580"),
    ],
)
def test_flag_decoding(flags, expected_clock, expected_model):
    h = _minimal()
    h.flags = flags
    assert h.clock == expected_clock
    assert h.sid_model == expected_model


def test_actual_load_address_embedded():
    h = _minimal()
    # data starts with $00 $10 -> $1000
    assert actual_load_address(h) == 0x1000


def test_actual_load_address_in_header():
    h = _minimal()
    h.load_address = 0x2000
    h.data = b"\x60\x60"
    assert actual_load_address(h) == 0x2000


def test_bad_magic_rejected():
    blob = b"XXXX" + b"\x00" * (HEADER_V1_SIZE - 4)
    with pytest.raises(ValueError, match="bad magic"):
        SidHeader.parse(blob)


def test_too_small_rejected():
    with pytest.raises(ValueError, match="too small"):
        SidHeader.parse(b"PSID")


def test_md5_new_equals_raw_file_md5():
    h = _minimal()
    blob = h.to_bytes()
    assert md5_new(blob) == hashlib.md5(blob).hexdigest()


def test_md5_old_appends_ntsc_byte_only_for_ntsc():
    pal = _minimal()
    pal.flags = 0x0014  # PAL + 6581
    pal_hash = md5_old(pal)

    ntsc = _minimal()
    ntsc.flags = 0x0028  # NTSC + 8580
    ntsc_hash = md5_old(ntsc)

    both = _minimal()
    both.flags = 0x000C  # PAL+NTSC, model unknown — NTSC byte NOT appended (only pure NTSC)
    both_hash = md5_old(both)

    # NTSC differs from PAL because the 0x02 byte is appended.
    assert pal_hash != ntsc_hash
    # PAL+NTSC shouldn't trigger the NTSC byte, so it matches the no-NTSC-byte hash
    # of the same data+addrs+speed (flags don't otherwise enter md5_old).
    plain = _minimal()
    plain.flags = 0x0000
    assert md5_old(plain) == both_hash


def test_md5_old_canonical_bytes():
    """Reconstruct md5_old by hand and verify."""
    h = _minimal()
    expected = hashlib.md5()
    expected.update(h.data)
    expected.update(struct.pack("<H", h.init_address))
    expected.update(struct.pack("<H", h.play_address))
    expected.update(struct.pack("<H", h.songs))
    # 1 song, VBI (speed bit 0 = 0) -> 0 byte
    expected.update(b"\x00")
    # PAL -> no NTSC byte
    assert md5_old(h) == expected.hexdigest()


def test_name_cp1252_roundtrip():
    h = _minimal()
    h.name = "Müller"  # contains non-ASCII
    blob = h.to_bytes()
    h2 = SidHeader.parse(blob)
    assert h2.name == "Müller"


def test_long_name_truncated_with_null():
    h = _minimal()
    h.name = "x" * 100
    blob = h.to_bytes()
    h2 = SidHeader.parse(blob)
    # 31 chars max + null terminator
    assert len(h2.name) == 31
