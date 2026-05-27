# Sidconverter

Commodore 64 SID file toolkit — inspect, render, convert and (best-effort)
synthesize PSID/RSID music files. Ships with a unified CLI and a Tkinter
GUI; the same code drives a Claude Code skill in `.claude/skills/sid-c64/`.

## Install

```sh
pip install .                  # core (stdlib only)
pip install .[audio]           # + librosa for non-WAV inputs to `from-audio`
pip install .[gui]             # + tkinterdnd2 for drag-and-drop in the GUI
pip install .[test]            # + pytest
pip install .[build]           # + pyinstaller for the standalone binary
```

External runtime tools (not bundled):

- `sidplayfp` — required by `render` (SID → audio).
- `ffmpeg` — required by `render` when the output is not WAV.

## CLI

```sh
sidconverter info tune.sid                      # metadata + HVSC MD5 hashes
sidconverter info tune.sid --json
sidconverter validate tune.sid                  # lint against PSID/RSID spec
sidconverter render tune.sid -o tune.wav -t 180 # render 3 minutes
sidconverter render tune.sid -o tune.wav -m n -f 44100   # 8580, 44.1 kHz
sidconverter render tune.sid -o tune.mp3        # routed through ffmpeg
sidconverter convert tune.sid -o tune.sid --to RSID
sidconverter from-audio melody.wav -o melody.sid --voices 3 \
    --waveform sawtooth --adsr 4,8,12,6 --clock pal
sidconverter gui                                # launch the Tk window
```

Run as a module if not installed: `python -m sidconverter <subcommand>`.

## GUI

`sidconverter gui` opens a Tk window with five tabs (Info, Validate,
Render, Convert, Audio → SID). Operations run in a background thread;
results land in a shared log pane. Install the `[gui]` extra to enable
drag-and-drop from the file manager onto the path entries.

## Tests

```sh
pip install .[test]
pytest -q
```

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
