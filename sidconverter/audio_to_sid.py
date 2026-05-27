"""sidconverter from-audio — synthesize a basic monophonic .sid from audio.

Best-effort: pitch-detect, quantise to MIDI semitones and frame-aligned
durations, emit a PSID v2 with an embedded 6510 player on voice 1
(triangle, 50 Hz PAL frame rate).
"""
from __future__ import annotations

import argparse
import math
import struct
import sys
import wave
from pathlib import Path

from .header import SidHeader


# ---------------------------------------------------------------------------
# Pitch detection
# ---------------------------------------------------------------------------

FRAME_RATE_HZ = 50
WINDOW_MS = 20
MIN_HZ = 65.0
MAX_HZ = 3500.0
SILENCE_RMS = 0.01


def _load_audio(path: Path) -> tuple[list[float], int]:
    try:
        import librosa  # type: ignore
        y, sr = librosa.load(str(path), sr=None, mono=True)
        return y.tolist(), int(sr)
    except ImportError:
        pass

    if path.suffix.lower() != ".wav":
        raise SystemExit(
            f"error: librosa not installed and input is not WAV ({path.suffix}).\n"
            "hint:  pip install librosa  (or convert your file to WAV first)"
        )

    with wave.open(str(path), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sr = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sampwidth != 2:
        raise SystemExit(
            f"error: only 16-bit PCM WAV is supported by the fallback "
            f"(this file is {sampwidth*8}-bit). Install librosa for broader support."
        )

    samples = struct.unpack("<" + "h" * (len(raw) // 2), raw)
    if n_channels > 1:
        mono = [
            sum(samples[i : i + n_channels]) / n_channels
            for i in range(0, len(samples), n_channels)
        ]
    else:
        mono = list(samples)
    scale = 1.0 / 32768.0
    return [s * scale for s in mono], sr


def _autocorr_pitch(window: list[float], sr: int) -> float:
    n = len(window)
    rms = math.sqrt(sum(s * s for s in window) / n) if n else 0.0
    if rms < SILENCE_RMS:
        return 0.0

    min_lag = max(2, int(sr / MAX_HZ))
    max_lag = min(n - 1, int(sr / MIN_HZ))
    if max_lag <= min_lag:
        return 0.0

    best_lag = min_lag
    best_val = -1.0
    for lag in range(min_lag, max_lag + 1):
        acc = 0.0
        for i in range(n - lag):
            acc += window[i] * window[i + lag]
        if acc > best_val:
            best_val = acc
            best_lag = lag

    if best_val <= 0:
        return 0.0
    return sr / best_lag


def _detect_pitches(samples: list[float], sr: int) -> list[float]:
    try:
        import numpy as np  # type: ignore
        import librosa  # type: ignore

        y = np.asarray(samples, dtype=np.float32)
        hop = max(1, int(round(sr * WINDOW_MS / 1000)))
        f0 = librosa.yin(
            y, fmin=MIN_HZ, fmax=MAX_HZ, sr=sr,
            frame_length=max(2048, hop * 4), hop_length=hop,
        )
        rms = librosa.feature.rms(y=y, frame_length=hop * 4, hop_length=hop)[0]
        out: list[float] = []
        for i, p in enumerate(f0):
            r = rms[i] if i < len(rms) else 0.0
            if r < SILENCE_RMS or not math.isfinite(p):
                out.append(0.0)
            else:
                out.append(float(p))
        return out
    except ImportError:
        pass

    hop = max(1, int(round(sr * WINDOW_MS / 1000)))
    out = []
    for start in range(0, len(samples) - hop, hop):
        out.append(_autocorr_pitch(samples[start : start + hop], sr))
    return out


# ---------------------------------------------------------------------------
# Note quantisation
# ---------------------------------------------------------------------------

SID_FREQ_FACTOR_PAL = (1 << 24) / 985248.0


def _hz_to_midi(hz: float) -> int | None:
    if hz <= 0:
        return None
    return int(round(69 + 12 * math.log2(hz / 440.0)))


def _midi_to_sid_reg(midi: int) -> int:
    hz = 440.0 * (2 ** ((midi - 69) / 12.0))
    val = int(round(hz * SID_FREQ_FACTOR_PAL))
    return max(0, min(0xFFFF, val))


def _quantise(pitches: list[float], max_notes: int = 255) -> list[tuple[int, int]]:
    notes: list[tuple[int, int]] = []
    cur_midi: int | None = -1
    cur_len = 0

    def flush():
        nonlocal cur_midi, cur_len
        if cur_len == 0:
            return
        if cur_midi is None:
            notes.append((0, min(cur_len, 255)))
        else:
            notes.append((_midi_to_sid_reg(cur_midi), min(cur_len, 255)))
        cur_len = 0

    for hz in pitches:
        midi = _hz_to_midi(hz)
        if midi != cur_midi or cur_len >= 255:
            flush()
            cur_midi = midi
        cur_len += 1
    flush()

    while notes and notes[0][0] == 0:
        notes.pop(0)
    cleaned: list[tuple[int, int]] = []
    for freq, dur in notes:
        if dur <= 1 and cleaned:
            prev_freq, prev_dur = cleaned[-1]
            cleaned[-1] = (prev_freq, min(prev_dur + dur, 255))
        else:
            cleaned.append((freq, dur))

    if len(cleaned) > max_notes:
        print(
            f"warning: truncating {len(cleaned)} detected notes to {max_notes} "
            "(player table is 256 entries max).",
            file=sys.stderr,
        )
        cleaned = cleaned[:max_notes]
    return cleaned


# ---------------------------------------------------------------------------
# 6510 player — layout documented in the SKILL.md
# ---------------------------------------------------------------------------

INIT_CODE = bytes([
    0xA9, 0x00,             # LDA #$00
    0xA2, 0x18,             # LDX #$18
    0x9D, 0x00, 0xD4,       # STA $D400,X
    0xCA,                   # DEX
    0x10, 0xFA,             # BPL clr_loop
    0xA9, 0x0F,             # LDA #$0F
    0x8D, 0x18, 0xD4,       # STA $D418
    0xA9, 0xF0,             # LDA #$F0
    0x8D, 0x06, 0xD4,       # STA $D406
    0xA9, 0x01,             # LDA #$01
    0x85, 0xFB,             # STA $FB
    0xA9, 0x00,             # LDA #$00
    0x85, 0xFC,             # STA $FC
    0x60,                   # RTS
])
assert len(INIT_CODE) == 29

INIT_ADDR = 0x1000
PLAY_ADDR = INIT_ADDR + len(INIT_CODE)
TABLE_FREQ_LO = 0x1100
TABLE_FREQ_HI = 0x1200
TABLE_DUR     = 0x1300
TABLE_END     = 0x1400


def _build_play(num_notes: int) -> bytes:
    code = bytearray([
        0xC6, 0xFB,                                 # DEC $FB
        0xD0, 0x29,                                 # BNE done
        0xA6, 0xFC,                                 # LDX $FC
        0xBD, 0x00, TABLE_DUR & 0xFF,               # LDA $1300,X
        0x85, 0xFB,                                 # STA $FB
        0xBD, 0x00, TABLE_FREQ_LO & 0xFF,           # LDA $1100,X
        0x8D, 0x00, 0xD4,                           # STA $D400
        0xBD, 0x00, TABLE_FREQ_HI & 0xFF,           # LDA $1200,X
        0x8D, 0x01, 0xD4,                           # STA $D401
        0xA9, 0x10,                                 # LDA #$10
        0x8D, 0x04, 0xD4,                           # STA $D404
        0xA9, 0x11,                                 # LDA #$11
        0x8D, 0x04, 0xD4,                           # STA $D404
        0xE6, 0xFC,                                 # INC $FC
        0xA5, 0xFC,                                 # LDA $FC
        0xC9, num_notes & 0xFF,                     # CMP #n
        0x90, 0x04,                                 # BCC done
        0xA9, 0x00,                                 # LDA #$00
        0x85, 0xFC,                                 # STA $FC
        0x60,                                       # RTS
    ])
    code[8]  = (TABLE_DUR >> 8) & 0xFF
    code[13] = (TABLE_FREQ_LO >> 8) & 0xFF
    code[19] = (TABLE_FREQ_HI >> 8) & 0xFF
    assert len(code) == 46
    return bytes(code)


def _build_payload(notes: list[tuple[int, int]]) -> bytes:
    play_code = _build_play(len(notes))

    image = bytearray(TABLE_END - INIT_ADDR)
    image[0 : len(INIT_CODE)] = INIT_CODE
    off_play = PLAY_ADDR - INIT_ADDR
    image[off_play : off_play + len(play_code)] = play_code

    for i, (freq, dur) in enumerate(notes):
        image[(TABLE_FREQ_LO - INIT_ADDR) + i] = freq & 0xFF
        image[(TABLE_FREQ_HI - INIT_ADDR) + i] = (freq >> 8) & 0xFF
        image[(TABLE_DUR     - INIT_ADDR) + i] = max(1, dur & 0xFF)

    return struct.pack("<H", INIT_ADDR) + bytes(image)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def convert_audio(
    input_path: Path,
    output_path: Path,
    *,
    name: str = "Untitled",
    author: str = "sidconverter",
    released: str = "2026",
    max_notes: int = 255,
) -> tuple[int, float]:
    """Convert input audio to a PSID file at output_path.

    Returns (n_notes, duration_seconds). Raises SystemExit on hard errors.
    """
    samples, sr = _load_audio(input_path)
    if not samples:
        raise SystemExit("error: empty audio")

    pitches = _detect_pitches(samples, sr)
    notes = _quantise(pitches, max_notes=min(255, max(1, max_notes)))
    if not notes:
        raise SystemExit("error: no pitched content detected")

    data = _build_payload(notes)
    h = SidHeader(
        magic="PSID",
        version=2,
        data_offset=0x7C,
        load_address=0,
        init_address=INIT_ADDR,
        play_address=PLAY_ADDR,
        songs=1,
        start_song=1,
        speed=0,
        name=name,
        author=author,
        released=released,
        flags=0x0014,
        data=data,
    )
    output_path.write_bytes(h.to_bytes())
    return len(notes), sum(d for _, d in notes) / FRAME_RATE_HZ


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("from-audio", help="synthesize a basic .sid from audio")
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--name", default="Untitled")
    p.add_argument("--author", default="sidconverter")
    p.add_argument("--released", default="2026")
    p.add_argument("--max-notes", type=int, default=255, dest="max_notes")
    p.set_defaults(func=run)
    return p


def run(args: argparse.Namespace) -> int:
    if not args.input.is_file():
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 1
    n, secs = convert_audio(
        args.input, args.output,
        name=args.name, author=args.author, released=args.released,
        max_notes=args.max_notes,
    )
    print(f"wrote {args.output}  ({n} notes, {secs:.1f}s of music)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Convert audio to a basic .sid")
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--name", default="Untitled")
    p.add_argument("--author", default="sidconverter")
    p.add_argument("--released", default="2026")
    p.add_argument("--max-notes", type=int, default=255, dest="max_notes")
    return run(p.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
