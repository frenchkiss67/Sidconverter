"""sidconverter render — render .sid to WAV/MP3 via sidplayfp (+ffmpeg)."""
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
        "win32": "scoop install sidplayfp   # or download from https://github.com/libsidplayfp",
    },
    "ffmpeg": {
        "linux": "sudo apt install ffmpeg",
        "darwin": "brew install ffmpeg",
        "win32": "winget install ffmpeg",
    },
}


def _hint(tool: str) -> str:
    key = sys.platform if sys.platform in ("darwin", "win32") else "linux"
    return INSTALL_HINTS[tool].get(key, f"install {tool} from your package manager")


def render_with_sidplayfp(
    src: Path,
    wav_out: Path,
    seconds: int,
    song: int | None,
    *,
    sample_rate: int | None = None,
    model: str | None = None,
    start: str | None = None,
) -> None:
    cmd = ["sidplayfp", f"-w{wav_out}", f"-t{seconds}"]
    if song is not None:
        cmd.append(f"-o{song}")
    if sample_rate is not None:
        cmd.append(f"-f{sample_rate}")
    if model:
        cmd.append(f"-m{model}")
    if start is not None:
        cmd.append(f"-b{start}")
    cmd.append(str(src))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout)
        sys.stderr.write(proc.stderr)
        raise RuntimeError(f"sidplayfp exited {proc.returncode}")


def render(
    src: Path,
    out: Path,
    seconds: int = 180,
    song: int | None = None,
    *,
    sample_rate: int | None = None,
    model: str | None = None,
    start: str | None = None,
) -> None:
    """Render src to out. Raises RuntimeError on tool failure, SystemExit on missing tools."""
    if shutil.which("sidplayfp") is None:
        raise SystemExit(f"error: sidplayfp not found on PATH\nhint:  {_hint('sidplayfp')}")

    kwargs = dict(sample_rate=sample_rate, model=model, start=start)
    want_wav = out.suffix.lower() == ".wav"
    if want_wav:
        render_with_sidplayfp(src, out, seconds, song, **kwargs)
        return

    if shutil.which("ffmpeg") is None:
        raise SystemExit(
            f"error: non-WAV output requested but ffmpeg is not on PATH\n"
            f"hint:  {_hint('ffmpeg')}"
        )
    with tempfile.TemporaryDirectory() as td:
        tmp_wav = Path(td) / "out.wav"
        render_with_sidplayfp(src, tmp_wav, seconds, song, **kwargs)
        ff = subprocess.run(
            ["ffmpeg", "-y", "-i", str(tmp_wav), str(out)],
            capture_output=True,
            text=True,
        )
        if ff.returncode != 0:
            sys.stderr.write(ff.stderr)
            raise RuntimeError(f"ffmpeg exited {ff.returncode}")


def _add_args(p: argparse.ArgumentParser) -> argparse.ArgumentParser:
    p.add_argument("input", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("-t", "--seconds", type=int, default=180)
    p.add_argument("-s", "--song", type=int, default=None)
    p.add_argument("-f", "--sample-rate", type=int, default=None,
                   help="output sample rate in Hz (sidplayfp default: 48000)")
    p.add_argument("-m", "--model", choices=("o", "n", "of", "nf"), default=None,
                   help="force SID model: 'o'=6581, 'n'=8580, suffix 'f' = no filter")
    p.add_argument("-b", "--start", default=None,
                   help="skip to this position, format [mins:]secs[.ms]")
    return p


def add_parser(sub: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = sub.add_parser("render", help="render .sid to WAV/MP3 (requires sidplayfp)")
    _add_args(p)
    p.set_defaults(func=run)
    return p


def run(args: argparse.Namespace) -> int:
    if not args.input.is_file():
        print(f"error: input not found: {args.input}", file=sys.stderr)
        return 1
    try:
        render(
            args.input, args.output, args.seconds, args.song,
            sample_rate=args.sample_rate, model=args.model, start=args.start,
        )
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    print(f"wrote {args.output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = _add_args(argparse.ArgumentParser(description="Render a SID file to audio"))
    return run(p.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
