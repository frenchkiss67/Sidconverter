#!/usr/bin/env python3
"""Render a .sid file to WAV (or any ffmpeg-supported audio format).

Wraps sidplayfp. Requires sidplayfp on PATH; if the output is not .wav,
ffmpeg is also required.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


INSTALL_HINTS = {
    "sidplayfp": {
        "linux": "sudo apt install sidplayfp   # or: sudo dnf install sidplayfp",
        "darwin": "brew install sidplayfp",
    },
    "ffmpeg": {
        "linux": "sudo apt install ffmpeg",
        "darwin": "brew install ffmpeg",
    },
}


def _hint(tool: str) -> str:
    key = "darwin" if sys.platform == "darwin" else "linux"
    return INSTALL_HINTS[tool].get(key, f"install {tool} from your package manager")


def render_with_sidplayfp(
    src: Path, wav_out: Path, seconds: int, song: int | None
) -> None:
    cmd = [
        "sidplayfp",
        "-w" + str(wav_out),
        "-t" + str(seconds),
    ]
    if song is not None:
        cmd.append(f"-o{song}")
    cmd.append(str(src))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise RuntimeError(f"sidplayfp exited {proc.returncode}")


def main() -> int:
    p = argparse.ArgumentParser(description="Render a SID file to audio")
    p.add_argument("input", type=Path, help="input .sid file")
    p.add_argument("-o", "--output", type=Path, required=True, help="output audio file")
    p.add_argument(
        "-t",
        "--seconds",
        type=int,
        default=180,
        help="duration in seconds (default 180)",
    )
    p.add_argument("-s", "--song", type=int, default=None, help="subtune number (1-based)")
    args = p.parse_args()

    if not args.input.is_file():
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 1

    if shutil.which("sidplayfp") is None:
        print("error: sidplayfp not found on PATH", file=sys.stderr)
        print("hint:  " + _hint("sidplayfp"), file=sys.stderr)
        return 2

    out = args.output
    want_wav = out.suffix.lower() == ".wav"

    try:
        if want_wav:
            render_with_sidplayfp(args.input, out, args.seconds, args.song)
        else:
            if shutil.which("ffmpeg") is None:
                print(
                    "error: non-WAV output requested but ffmpeg is not on PATH",
                    file=sys.stderr,
                )
                print("hint:  " + _hint("ffmpeg"), file=sys.stderr)
                return 2
            with tempfile.TemporaryDirectory() as td:
                tmp_wav = Path(td) / "out.wav"
                render_with_sidplayfp(args.input, tmp_wav, args.seconds, args.song)
                ff = subprocess.run(
                    ["ffmpeg", "-y", "-i", str(tmp_wav), str(out)],
                    capture_output=True,
                    text=True,
                )
                if ff.returncode != 0:
                    sys.stderr.write(ff.stderr)
                    raise RuntimeError(f"ffmpeg exited {ff.returncode}")
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3

    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
