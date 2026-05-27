"""Validator (sidconverter validate)."""
from __future__ import annotations

import struct

import pytest

from sidconverter.header import HEADER_V2PLUS_SIZE, SidHeader
from sidconverter.validate import lint


def _ok_psid(**kwargs) -> SidHeader:
    base = dict(
        magic="PSID", version=2, data_offset=HEADER_V2PLUS_SIZE,
        load_address=0, init_address=0x1000, play_address=0x1010,
        songs=1, start_song=1, speed=0,
        name="Test", author="Me", released="2026",
        flags=0x0014,
        data=struct.pack("<H", 0x1000) + b"\x60\x60",
    )
    base.update(kwargs)
    return SidHeader(**base)


def test_clean_psid_passes():
    errs, _ = lint(_ok_psid())
    assert errs == []


def test_bad_version_errors():
    h = _ok_psid(version=99)
    errs, _ = lint(h)
    assert any("version" in e for e in errs)


def test_start_song_out_of_range():
    h = _ok_psid(songs=2, start_song=5)
    errs, _ = lint(h)
    assert any("startSong" in e for e in errs)


def test_rsid_with_nonzero_play_is_error():
    h = _ok_psid(magic="RSID", play_address=0x1010)
    errs, _ = lint(h)
    assert any("play address" in e for e in errs)


def test_rsid_with_zero_everything_passes():
    h = _ok_psid(magic="RSID", play_address=0, speed=0)
    errs, _ = lint(h)
    assert errs == []


def test_second_sid_address_odd_rejected():
    h = _ok_psid(version=3, second_sid_address=0x43)
    errs, _ = lint(h)
    assert any("odd" in e for e in errs)


def test_second_sid_address_in_io2_range_rejected():
    h = _ok_psid(version=3, second_sid_address=0x80)  # $D800 = colour RAM
    errs, _ = lint(h)
    assert any("valid SID address range" in e for e in errs)


def test_third_sid_must_differ_from_second():
    h = _ok_psid(version=4, second_sid_address=0x42, third_sid_address=0x42)
    errs, _ = lint(h)
    assert any("differ" in e for e in errs)


def test_empty_name_emits_warning_not_error():
    h = _ok_psid(name="")
    errs, warns = lint(h)
    assert errs == []
    assert any("name field" in w for w in warns)


def test_mus_flag_emits_warning():
    h = _ok_psid(flags=0x0015)  # MUS bit + PAL + 6581
    _, warns = lint(h)
    assert any("MUS" in w for w in warns)
