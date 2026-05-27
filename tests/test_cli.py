"""Integration tests via the unified CLI."""
from __future__ import annotations

import json
import math
import struct
import subprocess
import sys
import wave
from pathlib import Path


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "sidconverter", *args],
        capture_output=True, text=True,
        cwd=Path(__file__).resolve().parents[1],
    )


def _write_tone(path: Path, hz: float, dur_s: float, sr: int = 22050) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        for i in range(int(sr * dur_s)):
            wf.writeframesraw(
                struct.pack("<h", int(20000 * math.sin(2 * math.pi * hz * i / sr)))
            )


def test_help_lists_all_subcommands():
    r = _run("--help")
    assert r.returncode == 0
    for cmd in ("info", "validate", "render", "convert", "from-audio", "gui"):
        assert cmd in r.stdout


def test_from_audio_then_info_then_validate(tmp_path):
    wav = tmp_path / "tone.wav"
    sid = tmp_path / "tone.sid"
    _write_tone(wav, 440.0, 0.3)

    r = _run("from-audio", str(wav), "-o", str(sid))
    assert r.returncode == 0
    assert sid.exists()

    r = _run("info", str(sid), "--json")
    assert r.returncode == 0
    d = json.loads(r.stdout)
    assert d["magic"] == "PSID"
    assert d["flags"]["clock"] == "PAL"

    r = _run("validate", str(sid))
    assert r.returncode == 0
    assert "OK" in r.stdout


def test_convert_to_rsid_blocks_without_force(tmp_path):
    wav = tmp_path / "tone.wav"
    sid = tmp_path / "tone.sid"
    _write_tone(wav, 440.0, 0.3)
    _run("from-audio", str(wav), "-o", str(sid))

    out = tmp_path / "rsid.sid"
    r = _run("convert", str(sid), "-o", str(out), "--to", "RSID")
    assert r.returncode == 2
    assert "play address" in r.stderr


def test_convert_to_rsid_with_force(tmp_path):
    wav = tmp_path / "tone.wav"
    sid = tmp_path / "tone.sid"
    _write_tone(wav, 440.0, 0.3)
    _run("from-audio", str(wav), "-o", str(sid))

    out = tmp_path / "rsid.sid"
    r = _run("convert", str(sid), "-o", str(out), "--to", "RSID", "--force")
    assert r.returncode == 0
    assert out.exists()


def test_validate_rejects_random_bytes(tmp_path):
    bad = tmp_path / "bad.sid"
    bad.write_bytes(b"this is not a sid file")
    r = _run("validate", str(bad))
    assert r.returncode != 0


def test_render_help_exposes_extra_flags():
    r = _run("render", "--help")
    assert r.returncode == 0
    for opt in ("--sample-rate", "--model", "--start"):
        assert opt in r.stdout


def test_from_audio_help_lists_new_flags():
    r = _run("from-audio", "--help")
    assert r.returncode == 0
    for opt in ("--voices", "--waveform", "--adsr", "--clock", "--model"):
        assert opt in r.stdout
