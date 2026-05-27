# Sidconverter

Commodore 64 SID file toolkit — inspect, render, convert and (best-effort)
synthesize PSID/RSID music files. Ships with a unified CLI and a Tkinter
GUI; the same code drives a Claude Code skill in `.claude/skills/sid-c64/`.

## Install

```sh
pip install .                  # core (stdlib only)
pip install .[audio]           # + librosa for non-WAV inputs to `from-audio`
pip install .[build]           # + pyinstaller for the standalone binary
```

External runtime tools (not bundled):

- `sidplayfp` — required by `render` (SID → audio).
- `ffmpeg` — required by `render` when the output is not WAV.

## CLI

```sh
sidconverter info tune.sid                      # metadata + HVSC SHA-1
sidconverter info tune.sid --json
sidconverter render tune.sid -o tune.wav -t 180 # render 3 minutes
sidconverter render tune.sid -o tune.mp3        # routed through ffmpeg
sidconverter convert tune.sid -o tune.sid --to RSID
sidconverter from-audio melody.wav -o melody.sid --name "My Tune"
sidconverter gui                                # launch the Tk window
```

Run as a module if not installed: `python -m sidconverter <subcommand>`.

## GUI

`sidconverter gui` opens a Tk window with four tabs (Info, Render, Convert,
Audio → SID). Operations run in a background thread; results land in a
shared log pane.

## Standalone binary

```sh
pip install .[build]
pyinstaller sidconverter.spec
./dist/sidconverter gui
```

Build on each target OS (PyInstaller does not cross-compile).

## Claude Code skill

The skill at `.claude/skills/sid-c64/` is auto-loaded by Claude Code. The
scripts there are thin wrappers around the same `sidconverter.*` modules.
