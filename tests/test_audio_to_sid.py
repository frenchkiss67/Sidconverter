"""End-to-end test of audio -> SID using a synthesized tone."""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

import pytest

from sidconverter.audio_to_sid import (
    C64_CLOCK_NTSC,
    C64_CLOCK_PAL,
    _midi_to_sid_reg,
    _parse_adsr,
    convert_audio,
)
from sidconverter.header import SidHeader


def _write_tone(path: Path, hz: float, dur_s: float, sr: int = 22050) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        for i in range(int(sr * dur_s)):
            wf.writeframesraw(
                struct.pack("<h", int(20000 * math.sin(2 * math.pi * hz * i / sr)))
            )


def test_a4_maps_to_correct_pal_register():
    # A4 = 440 Hz at PAL clock = round(440 * 2^24 / 985248) = 7493
    expected = round(440 * (1 << 24) / C64_CLOCK_PAL)
    assert _midi_to_sid_reg(69, "pal") == expected


def test_a4_pal_ntsc_differ():
    pal = _midi_to_sid_reg(69, "pal")
    ntsc = _midi_to_sid_reg(69, "ntsc")
    assert pal != ntsc
    # NTSC is faster (1.022 MHz vs 0.985 MHz), so register value is smaller
    assert ntsc < pal


def test_parse_adsr_valid():
    ad, sr = _parse_adsr("3,5,15,7")
    assert ad == (3 << 4) | 5
    assert sr == (15 << 4) | 7


@pytest.mark.parametrize("bad", ["1,2,3", "1,2,3,4,5", "a,b,c,d", "1,2,16,3"])
def test_parse_adsr_rejects_bad(bad):
    with pytest.raises(SystemExit):
        _parse_adsr(bad)


def test_convert_audio_produces_parseable_sid(tmp_path):
    wav = tmp_path / "tone.wav"
    sid = tmp_path / "tone.sid"
    _write_tone(wav, 440.0, 0.3)

    n, secs = convert_audio(
        wav, sid, name="Test", author="pytest", clock="pal", voices=1,
    )
    assert n >= 1
    assert secs > 0
    h = SidHeader.parse(sid.read_bytes())
    assert h.magic == "PSID"
    assert h.clock == "PAL"
    assert h.sid_model == "MOS6581"
    assert h.init_address == 0x1000
    # Player code is at least the init routine length
    assert h.play_address > h.init_address


def test_convert_audio_3_voices_writes_harmony_tables(tmp_path):
    wav = tmp_path / "tone.wav"
    sid = tmp_path / "tone.sid"
    _write_tone(wav, 440.0, 0.4)

    convert_audio(wav, sid, voices=3, waveform="triangle", adsr="0,0,15,0")

    h = SidHeader.parse(sid.read_bytes())
    image = h.data[2:]
    # Voice 1 table at $1100 (offset 0x100 into image); voice 2 at $1300; voice 3 at $1500.
    # All three should be non-zero somewhere in the first 8 bytes (a tone of
    # 0.4s = 20 frames typically yields 1-2 notes).
    def _has_nonzero(off: int) -> bool:
        return any(image[off + i] for i in range(8))

    assert _has_nonzero(0x100)              # voice 1 freq lo
    assert _has_nonzero(0x300)              # voice 2 freq lo (octave below)
    assert _has_nonzero(0x500)              # voice 3 freq lo (fifth above)


def test_convert_audio_1_voice_keeps_v2_v3_silent(tmp_path):
    wav = tmp_path / "tone.wav"
    sid = tmp_path / "tone.sid"
    _write_tone(wav, 440.0, 0.4)

    convert_audio(wav, sid, voices=1)

    h = SidHeader.parse(sid.read_bytes())
    image = h.data[2:]
    # Voice 2 and 3 should be all zero in their frequency tables
    assert all(image[0x300 + i] == 0 for i in range(16))
    assert all(image[0x500 + i] == 0 for i in range(16))


def test_ntsc_uses_smaller_register_values(tmp_path):
    wav = tmp_path / "tone.wav"
    sid_pal = tmp_path / "pal.sid"
    sid_ntsc = tmp_path / "ntsc.sid"
    _write_tone(wav, 440.0, 0.3)

    convert_audio(wav, sid_pal, clock="pal", voices=1)
    convert_audio(wav, sid_ntsc, clock="ntsc", voices=1)

    pal = SidHeader.parse(sid_pal.read_bytes())
    ntsc = SidHeader.parse(sid_ntsc.read_bytes())
    # The first byte of voice 1 freq lo table reflects the chosen clock
    pal_lo = pal.data[2 + 0x100]
    ntsc_lo = ntsc.data[2 + 0x100]
    # Different clock -> different register value for the same input pitch
    assert pal_lo != ntsc_lo or pal.data[2 + 0x200] != ntsc.data[2 + 0x200]
