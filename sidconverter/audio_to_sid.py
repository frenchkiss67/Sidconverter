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

FRAME_RATE_HZ_PAL = 50
FRAME_RATE_HZ_NTSC = 60
WINDOW_MS = 20
MIN_HZ = 65.0
MAX_HZ = 3500.0
SILENCE_RMS = 0.01

# C64 system clocks (Hz). SID register = round(f_Hz * 2^24 / clock).
C64_CLOCK_PAL = 985248
C64_CLOCK_NTSC = 1022730

CLOCK_FLAG = {"pal": 0x04, "ntsc": 0x08}
MODEL_FLAG = {"6581": 0x10, "8580": 0x20}


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
        frame = max(2048, hop * 4)
        # pyin returns (f0, voiced_flag, voiced_prob); it suppresses harmonic
        # errors and explicitly flags unvoiced frames, which is what we want
        # for separating notes from silence/noise.
        f0, voiced, _ = librosa.pyin(
            y, fmin=MIN_HZ, fmax=MAX_HZ, sr=sr,
            frame_length=frame, hop_length=hop,
        )
        rms = librosa.feature.rms(y=y, frame_length=frame, hop_length=hop)[0]
        out: list[float] = []
        for i, p in enumerate(f0):
            r = rms[i] if i < len(rms) else 0.0
            v = bool(voiced[i]) if i < len(voiced) else False
            if not v or r < SILENCE_RMS or not math.isfinite(p):
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

def _hz_to_midi(hz: float) -> int | None:
    if hz <= 0:
        return None
    return int(round(69 + 12 * math.log2(hz / 440.0)))


def _midi_to_sid_reg(midi: int, clock: str) -> int:
    factor = (1 << 24) / (C64_CLOCK_PAL if clock == "pal" else C64_CLOCK_NTSC)
    hz = 440.0 * (2 ** ((midi - 69) / 12.0))
    val = int(round(hz * factor))
    return max(0, min(0xFFFF, val))


def _quantise_midi(pitches: list[float], max_notes: int = 255) -> list[tuple[int | None, int]]:
    """Group consecutive same-MIDI frames. Returns (midi_or_None, duration_frames)."""
    notes: list[tuple[int | None, int]] = []
    cur_midi: int | None | object = object()
    cur_len = 0

    def flush() -> None:
        nonlocal cur_len
        if cur_len > 0:
            notes.append((cur_midi if isinstance(cur_midi, (int, type(None))) else None,
                          min(cur_len, 255)))
            cur_len = 0

    for hz in pitches:
        midi = _hz_to_midi(hz)
        if midi != cur_midi or cur_len >= 255:
            flush()
            cur_midi = midi
        cur_len += 1
    flush()

    # Drop leading silence, merge 1-frame glitches into the previous note.
    while notes and notes[0][0] is None:
        notes.pop(0)
    cleaned: list[tuple[int | None, int]] = []
    for midi, dur in notes:
        if dur <= 1 and cleaned:
            pm, pd = cleaned[-1]
            cleaned[-1] = (pm, min(pd + dur, 255))
        else:
            cleaned.append((midi, dur))

    if len(cleaned) > max_notes:
        print(
            f"warning: truncating {len(cleaned)} detected notes to {max_notes} "
            "(player table is 256 entries max).",
            file=sys.stderr,
        )
        cleaned = cleaned[:max_notes]
    return cleaned


def _voice_columns(
    notes_midi: list[tuple[int | None, int]],
    voices: int,
    clock: str,
) -> list[list[int]]:
    """Build (3 voice × N step) frequency register tables.

    voices=1: voice 1 = melody, voices 2/3 silent.
    voices=3: voice 1 = melody, voice 2 = octave below, voice 3 = perfect fifth above.
    """
    melody = [m for m, _ in notes_midi]
    cols: list[list[int]] = [[], [], []]

    if voices == 1:
        offsets = (0, None, None)      # only voice 1 plays
    else:
        offsets = (0, -12, 7)          # melody, octave-down bass, fifth-up sweetener

    for midi in melody:
        for v, off in enumerate(offsets):
            if midi is None or off is None:
                cols[v].append(0)
            else:
                cols[v].append(_midi_to_sid_reg(midi + off, clock))
    return cols


def _parse_adsr(s: str) -> tuple[int, int]:
    """Parse 'A,D,S,R' (each 0..15) into (AD, SR) bytes."""
    parts = [p.strip() for p in s.split(",")]
    if len(parts) != 4:
        raise SystemExit(f"error: --adsr expects 4 comma-separated values, got {s!r}")
    try:
        a, d, sus, r = (int(p, 0) for p in parts)
    except ValueError as e:
        raise SystemExit(f"error: --adsr values must be integers: {e}") from None
    for label, v in (("attack", a), ("decay", d), ("sustain", sus), ("release", r)):
        if not 0 <= v <= 15:
            raise SystemExit(f"error: --adsr {label}={v} out of range 0..15")
    return ((a << 4) | d, (sus << 4) | r)


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
    clock: str = "pal",
    model: str = "6581",
    voices: int = 1,
    waveform: str = "triangle",
    adsr: str = "0,0,15,0",
) -> tuple[int, float]:
    """Convert input audio to a PSID file at output_path.

    Returns (n_notes, duration_seconds). Raises SystemExit on hard errors.
    """
    from . import player as player_mod

    clock = clock.lower()
    model = model.lower()
    if clock not in CLOCK_FLAG:
        raise SystemExit(f"error: clock must be pal or ntsc, got {clock!r}")
    if model not in MODEL_FLAG:
        raise SystemExit(f"error: model must be 6581 or 8580, got {model!r}")
    if voices not in (1, 3):
        raise SystemExit(f"error: voices must be 1 or 3, got {voices}")
    if waveform not in player_mod.WAVEFORMS:
        raise SystemExit(f"error: waveform must be one of {sorted(player_mod.WAVEFORMS)}")

    ad_byte, sr_byte = _parse_adsr(adsr)
    waveform_byte = player_mod.WAVEFORMS[waveform]

    samples, audio_sr = _load_audio(input_path)
    if not samples:
        raise SystemExit("error: empty audio")

    pitches = _detect_pitches(samples, audio_sr)
    notes = _quantise_midi(pitches, max_notes=min(255, max(1, max_notes)))
    if not notes:
        raise SystemExit("error: no pitched content detected")

    cols = _voice_columns(notes, voices, clock)
    durations = [d for _, d in notes]

    data, play_addr = player_mod.build_payload(
        cols, durations,
        waveform=waveform_byte, ad=ad_byte, sr=sr_byte,
    )
    flags = CLOCK_FLAG[clock] | MODEL_FLAG[model]
    h = SidHeader(
        magic="PSID",
        version=2,
        data_offset=0x7C,
        load_address=0,
        init_address=player_mod.INIT_ADDR,
        play_address=play_addr,
        songs=1,
        start_song=1,
        speed=0,
        name=name,
        author=author,
        released=released,
        flags=flags,
        data=data,
    )
    output_path.write_bytes(h.to_bytes())
    frame_rate = FRAME_RATE_HZ_PAL if clock == "pal" else FRAME_RATE_HZ_NTSC
    return len(notes), sum(durations) / frame_rate


def _add_args(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--name", default="Untitled")
    p.add_argument("--author", default="sidconverter")
    p.add_argument("--released", default="2026")
    p.add_argument("--max-notes", type=int, default=255, dest="max_notes")
    p.add_argument("--clock", choices=("pal", "ntsc"), default="pal",
                   help="C64 system clock used for SID frequency tuning")
    p.add_argument("--model", choices=("6581", "8580"), default="6581",
                   help="declare SID model in PSID flags")
    p.add_argument("--voices", type=int, choices=(1, 3), default=3,
                   help="1=monophonic; 3=melody + octave-below bass + fifth-above harmony")
    p.add_argument("--waveform", choices=("triangle", "sawtooth", "pulse", "noise"),
                   default="triangle")
    p.add_argument("--adsr", default="0,0,15,0",
                   help="ADSR envelope as 'A,D,S,R' values 0..15 (default sustained note)")
    return p


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("from-audio", help="synthesize a basic .sid from audio")
    _add_args(p)
    p.set_defaults(func=run)
    return p


def run(args: argparse.Namespace) -> int:
    if not args.input.is_file():
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 1
    n, secs = convert_audio(
        args.input, args.output,
        name=args.name, author=args.author, released=args.released,
        max_notes=args.max_notes, clock=args.clock, model=args.model,
        voices=args.voices, waveform=args.waveform, adsr=args.adsr,
    )
    print(
        f"wrote {args.output}  ({n} notes, {secs:.1f}s, "
        f"{args.voices} voice(s), {args.waveform})"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = _add_args(argparse.ArgumentParser(description="Convert audio to a basic .sid"))
    return run(p.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
