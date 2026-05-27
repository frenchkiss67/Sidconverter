"""RSID warning rules."""
from __future__ import annotations

import struct

from sidconverter.format_convert import convert, warnings_for
from sidconverter.header import HEADER_V2PLUS_SIZE, SidHeader


def _psid(**kwargs) -> SidHeader:
    base = dict(
        magic="PSID", version=2, data_offset=HEADER_V2PLUS_SIZE,
        load_address=0, init_address=0x1000, play_address=0x1010,
        songs=1, start_song=1, speed=0, name="t", author="t", released="2026",
        flags=0x0014, data=struct.pack("<H", 0x1000) + b"\x60\x60",
    )
    base.update(kwargs)
    return SidHeader(**base)


def test_to_rsid_warns_about_nonzero_play():
    h = _psid(play_address=0x1010)
    warns = warnings_for(h, "RSID")
    assert any("play address" in w for w in warns)


def test_to_rsid_warns_about_nonzero_speed():
    h = _psid(play_address=0, speed=0xDEADBEEF)
    warns = warnings_for(h, "RSID")
    assert any("speed" in w for w in warns)


def test_to_rsid_warns_about_low_load_address():
    h = _psid(load_address=0x0400, play_address=0, data=b"\x60")
    warns = warnings_for(h, "RSID")
    assert any("$07E8" in w for w in warns)


def test_to_rsid_warns_about_init_in_rom():
    h = _psid(init_address=0xA000, play_address=0)
    warns = warnings_for(h, "RSID")
    assert any("ROM" in w for w in warns)


def test_to_rsid_warns_about_init_below_07E8():
    h = _psid(init_address=0x0100, play_address=0)
    warns = warnings_for(h, "RSID")
    assert any("$07E8" in w for w in warns)


def test_to_rsid_warns_about_basic_with_nonzero_init():
    h = _psid(flags=0x0016, play_address=0, init_address=0x1000)  # bit 1 set
    warns = warnings_for(h, "RSID")
    assert any("BASIC" in w for w in warns)


def test_clean_psid_to_rsid_no_warnings():
    h = _psid(play_address=0, speed=0, load_address=0, init_address=0x1000)
    assert warnings_for(h, "RSID") == []


def test_psid_target_has_no_warnings():
    # Converting to PSID is permissive
    h = _psid(play_address=0x1010, speed=1)
    assert warnings_for(h, "PSID") == []


def test_convert_flips_magic_and_clears_psid_specific_bit():
    h = _psid(flags=0x0016)  # bit 1 set
    out = convert(h, "RSID")
    assert out.magic == "RSID"
    assert (out.flags & 0x02) == 0
