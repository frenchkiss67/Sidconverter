"""Tkinter GUI for sidconverter.

Five tabs map to the operations: Info, Validate, Render, Convert, Audio -> SID.
Long-running operations run in a background thread so the UI stays
responsive; status text and errors land in a shared log pane.

Drag-and-drop is enabled when the optional `tkinterdnd2` package is
installed; otherwise the GUI falls back to plain Tk file dialogs.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import threading
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Callable

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import audio_to_sid, format_convert, info, render, validate
from .header import SidHeader

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore
    _DND_AVAILABLE = True
except ImportError:
    _DND_AVAILABLE = False


SID_FILETYPES = [("SID files", "*.sid"), ("All files", "*.*")]
AUDIO_FILETYPES = [
    ("Audio files", "*.wav *.mp3 *.ogg *.flac *.m4a"),
    ("All files", "*.*"),
]


def _browse(entry: tk.Entry, *, save: bool, types, defaultext: str = "") -> None:
    fn = (filedialog.asksaveasfilename if save else filedialog.askopenfilename)(
        filetypes=types, defaultextension=defaultext
    )
    if fn:
        entry.delete(0, tk.END)
        entry.insert(0, fn)


def _enable_dnd(entry: tk.Entry) -> None:
    """Register an Entry as a drop target if tkinterdnd2 is installed."""
    if not _DND_AVAILABLE:
        return
    try:
        entry.drop_target_register(DND_FILES)  # type: ignore[attr-defined]

        def on_drop(event: object) -> None:
            path = getattr(event, "data", "").strip().strip("{}")
            if path:
                entry.delete(0, tk.END)
                entry.insert(0, path)

        entry.dnd_bind("<<Drop>>", on_drop)  # type: ignore[attr-defined]
    except (tk.TclError, AttributeError):
        pass


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Sidconverter")
        root.geometry("720x520")

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self._build_info_tab(nb)
        self._build_validate_tab(nb)
        self._build_render_tab(nb)
        self._build_convert_tab(nb)
        self._build_audio_tab(nb)

        if not _DND_AVAILABLE:
            ttk.Label(
                root,
                text="Tip: `pip install tkinterdnd2` to drag .sid / audio files into the entries.",
                foreground="gray40",
            ).pack(fill="x", padx=8, pady=(0, 4))

        # Log pane
        log_frame = ttk.LabelFrame(root, text="Log")
        log_frame.pack(fill="both", expand=False, padx=8, pady=(0, 8))
        self.log = tk.Text(log_frame, height=8, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True, padx=4, pady=4)

    # ------------------------------------------------------------------
    # Threading helper
    # ------------------------------------------------------------------

    def _run_async(self, label: str, func: Callable[[], None]) -> None:
        self._log(f"-- {label} --")

        def worker() -> None:
            buf_out, buf_err = io.StringIO(), io.StringIO()
            try:
                with redirect_stdout(buf_out), redirect_stderr(buf_err):
                    func()
                ok = True
            except SystemExit as e:
                ok = (e.code in (None, 0))
            except Exception:
                buf_err.write(traceback.format_exc())
                ok = False
            self.root.after(0, lambda: self._finish(label, buf_out, buf_err, ok))

        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, label: str, out: io.StringIO, err: io.StringIO, ok: bool) -> None:
        text = out.getvalue() + err.getvalue()
        if text:
            self._log(text.rstrip())
        self._log(f"-- {label}: {'OK' if ok else 'FAILED'} --\n")
        if not ok and err.getvalue():
            messagebox.showerror(label, err.getvalue().strip() or "Operation failed.")

    def _log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ------------------------------------------------------------------
    # Info tab
    # ------------------------------------------------------------------

    def _build_info_tab(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb)
        nb.add(f, text="Info")
        ttk.Label(f, text="SID file:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.info_path = ttk.Entry(f, width=60)
        self.info_path.grid(row=0, column=1, sticky="we", padx=4)
        _enable_dnd(self.info_path)
        ttk.Button(
            f, text="Browse...",
            command=lambda: _browse(self.info_path, save=False, types=SID_FILETYPES),
        ).grid(row=0, column=2, padx=4)
        ttk.Button(f, text="Inspect", command=self._do_info).grid(
            row=1, column=1, sticky="w", padx=4, pady=4
        )
        f.columnconfigure(1, weight=1)

    def _build_validate_tab(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb)
        nb.add(f, text="Validate")
        ttk.Label(f, text="SID file:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.val_path = ttk.Entry(f, width=60)
        self.val_path.grid(row=0, column=1, sticky="we", padx=4)
        _enable_dnd(self.val_path)
        ttk.Button(
            f, text="Browse...",
            command=lambda: _browse(self.val_path, save=False, types=SID_FILETYPES),
        ).grid(row=0, column=2, padx=4)
        self.val_strict = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            f, text="Strict (treat warnings as failure)", variable=self.val_strict
        ).grid(row=1, column=1, sticky="w", padx=4)
        ttk.Button(f, text="Validate", command=self._do_validate).grid(
            row=2, column=1, sticky="w", padx=4, pady=4
        )
        f.columnconfigure(1, weight=1)

    def _do_validate(self) -> None:
        path = Path(self.val_path.get())
        if not path.is_file():
            messagebox.showerror("Validate", f"File not found: {path}")
            return
        strict = self.val_strict.get()

        def go() -> None:
            h = SidHeader.parse(path.read_bytes())
            errors, warns = validate.lint(h)
            for w in warns:
                print(f"warning: {w}")
            for e in errors:
                print(f"error: {e}")
            if errors:
                raise SystemExit(2)
            if warns and strict:
                raise SystemExit(1)
            print(f"OK  {h.magic} v{h.version}, name={h.name!r}")

        self._run_async("validate", go)

    def _do_info(self) -> None:
        path = Path(self.info_path.get())
        if not path.is_file():
            messagebox.showerror("Info", f"File not found: {path}")
            return

        def go() -> None:
            h = SidHeader.parse(path.read_bytes())
            d = info.to_dict(h, path)
            print(info.format_pretty(d))
            print()
            print(json.dumps(d, indent=2))

        self._run_async("info", go)

    # ------------------------------------------------------------------
    # Render tab
    # ------------------------------------------------------------------

    def _build_render_tab(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb)
        nb.add(f, text="Render to audio")
        ttk.Label(f, text="Input .sid:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.render_in = ttk.Entry(f, width=60)
        self.render_in.grid(row=0, column=1, sticky="we", padx=4)
        _enable_dnd(self.render_in)
        ttk.Button(
            f, text="Browse...",
            command=lambda: _browse(self.render_in, save=False, types=SID_FILETYPES),
        ).grid(row=0, column=2, padx=4)

        ttk.Label(f, text="Output:").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self.render_out = ttk.Entry(f, width=60)
        self.render_out.grid(row=1, column=1, sticky="we", padx=4)
        _enable_dnd(self.render_out)
        ttk.Button(
            f, text="Save as...",
            command=lambda: _browse(
                self.render_out, save=True,
                types=[("WAV", "*.wav"), ("MP3", "*.mp3"), ("OGG", "*.ogg")],
                defaultext=".wav",
            ),
        ).grid(row=1, column=2, padx=4)

        ttk.Label(f, text="Duration (s):").grid(row=2, column=0, sticky="w", padx=4)
        self.render_secs = ttk.Spinbox(f, from_=1, to=3600, width=8)
        self.render_secs.set(180)
        self.render_secs.grid(row=2, column=1, sticky="w", padx=4)

        ttk.Label(f, text="Subtune (blank = default):").grid(row=3, column=0, sticky="w", padx=4)
        self.render_song = ttk.Entry(f, width=8)
        self.render_song.grid(row=3, column=1, sticky="w", padx=4)

        ttk.Button(f, text="Render", command=self._do_render).grid(
            row=4, column=1, sticky="w", padx=4, pady=8
        )
        f.columnconfigure(1, weight=1)

    def _do_render(self) -> None:
        src = Path(self.render_in.get())
        out = Path(self.render_out.get())
        if not src.is_file():
            messagebox.showerror("Render", f"Input not found: {src}")
            return
        if not out.name:
            messagebox.showerror("Render", "Pick an output file.")
            return
        seconds = int(self.render_secs.get() or 180)
        song_text = self.render_song.get().strip()
        song = int(song_text) if song_text else None

        def go() -> None:
            render.render(src, out, seconds=seconds, song=song)
            print(f"wrote {out}")

        self._run_async("render", go)

    # ------------------------------------------------------------------
    # Convert tab
    # ------------------------------------------------------------------

    def _build_convert_tab(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb)
        nb.add(f, text="Convert format")
        ttk.Label(f, text="Input .sid:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.conv_in = ttk.Entry(f, width=60)
        self.conv_in.grid(row=0, column=1, sticky="we", padx=4)
        _enable_dnd(self.conv_in)
        ttk.Button(
            f, text="Browse...",
            command=lambda: _browse(self.conv_in, save=False, types=SID_FILETYPES),
        ).grid(row=0, column=2, padx=4)

        ttk.Label(f, text="Output .sid:").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self.conv_out = ttk.Entry(f, width=60)
        self.conv_out.grid(row=1, column=1, sticky="we", padx=4)
        _enable_dnd(self.conv_out)
        ttk.Button(
            f, text="Save as...",
            command=lambda: _browse(
                self.conv_out, save=True, types=SID_FILETYPES, defaultext=".sid"
            ),
        ).grid(row=1, column=2, padx=4)

        ttk.Label(f, text="Target:").grid(row=2, column=0, sticky="w", padx=4)
        self.conv_to = tk.StringVar(value="RSID")
        ttk.Radiobutton(f, text="PSID", variable=self.conv_to, value="PSID").grid(
            row=2, column=1, sticky="w", padx=4
        )
        ttk.Radiobutton(f, text="RSID", variable=self.conv_to, value="RSID").grid(
            row=2, column=1, padx=64, sticky="w"
        )

        self.conv_force = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            f, text="Force (ignore warnings)", variable=self.conv_force
        ).grid(row=3, column=1, sticky="w", padx=4)

        ttk.Button(f, text="Convert", command=self._do_convert).grid(
            row=4, column=1, sticky="w", padx=4, pady=8
        )
        f.columnconfigure(1, weight=1)

    def _do_convert(self) -> None:
        src = Path(self.conv_in.get())
        out = Path(self.conv_out.get())
        if not src.is_file():
            messagebox.showerror("Convert", f"Input not found: {src}")
            return
        if not out.name:
            messagebox.showerror("Convert", "Pick an output file.")
            return
        target = self.conv_to.get()
        force = self.conv_force.get()

        def go() -> None:
            h = SidHeader.parse(src.read_bytes())
            warns = format_convert.warnings_for(h, target)
            for w in warns:
                print(f"warning: {w}", file=sys.stderr)
            if warns and not force:
                print("refusing to convert; tick 'Force' to override.", file=sys.stderr)
                raise SystemExit(2)
            format_convert.convert(h, target)
            out.write_bytes(h.to_bytes())
            print(f"wrote {out} as {target} v{h.version}")

        self._run_async("convert", go)

    # ------------------------------------------------------------------
    # Audio -> SID tab
    # ------------------------------------------------------------------

    def _build_audio_tab(self, nb: ttk.Notebook) -> None:
        f = ttk.Frame(nb)
        nb.add(f, text="Audio -> SID")
        ttk.Label(f, text="Input audio:").grid(row=0, column=0, sticky="w", padx=4, pady=4)
        self.a2s_in = ttk.Entry(f, width=60)
        self.a2s_in.grid(row=0, column=1, sticky="we", padx=4)
        _enable_dnd(self.a2s_in)
        ttk.Button(
            f, text="Browse...",
            command=lambda: _browse(self.a2s_in, save=False, types=AUDIO_FILETYPES),
        ).grid(row=0, column=2, padx=4)

        ttk.Label(f, text="Output .sid:").grid(row=1, column=0, sticky="w", padx=4, pady=4)
        self.a2s_out = ttk.Entry(f, width=60)
        self.a2s_out.grid(row=1, column=1, sticky="we", padx=4)
        _enable_dnd(self.a2s_out)
        ttk.Button(
            f, text="Save as...",
            command=lambda: _browse(
                self.a2s_out, save=True, types=SID_FILETYPES, defaultext=".sid"
            ),
        ).grid(row=1, column=2, padx=4)

        for i, (label, attr, default) in enumerate(
            [("Name", "a2s_name", "Untitled"),
             ("Author", "a2s_author", "sidconverter"),
             ("Released", "a2s_released", "2026")],
            start=2,
        ):
            ttk.Label(f, text=f"{label}:").grid(row=i, column=0, sticky="w", padx=4)
            entry = ttk.Entry(f, width=40)
            entry.insert(0, default)
            entry.grid(row=i, column=1, sticky="we", padx=4)
            setattr(self, attr, entry)

        ttk.Label(f, text="Voices:").grid(row=5, column=0, sticky="w", padx=4)
        self.a2s_voices = tk.IntVar(value=3)
        ttk.Radiobutton(f, text="1 (mono)", variable=self.a2s_voices, value=1).grid(
            row=5, column=1, sticky="w", padx=4
        )
        ttk.Radiobutton(
            f, text="3 (melody + bass + harmony)", variable=self.a2s_voices, value=3
        ).grid(row=5, column=1, padx=80, sticky="w")

        ttk.Label(f, text="Waveform:").grid(row=6, column=0, sticky="w", padx=4)
        self.a2s_waveform = tk.StringVar(value="triangle")
        ttk.Combobox(
            f, textvariable=self.a2s_waveform,
            values=("triangle", "sawtooth", "pulse", "noise"),
            state="readonly", width=12,
        ).grid(row=6, column=1, sticky="w", padx=4)

        ttk.Label(f, text="ADSR (A,D,S,R 0-15):").grid(row=7, column=0, sticky="w", padx=4)
        self.a2s_adsr = ttk.Entry(f, width=12)
        self.a2s_adsr.insert(0, "0,0,15,0")
        self.a2s_adsr.grid(row=7, column=1, sticky="w", padx=4)

        ttk.Button(f, text="Generate .sid", command=self._do_audio).grid(
            row=8, column=1, sticky="w", padx=4, pady=8
        )
        ttk.Label(
            f,
            text="Note: best-effort. Pitch is detected monophonically; "
                 "3-voice mode synthesises a fixed bass + fifth around the melody.",
            foreground="gray40",
        ).grid(row=9, column=0, columnspan=3, sticky="w", padx=4)
        f.columnconfigure(1, weight=1)

    def _do_audio(self) -> None:
        src = Path(self.a2s_in.get())
        out = Path(self.a2s_out.get())
        if not src.is_file():
            messagebox.showerror("Audio -> SID", f"Input not found: {src}")
            return
        if not out.name:
            messagebox.showerror("Audio -> SID", "Pick an output file.")
            return
        name = self.a2s_name.get() or "Untitled"
        author = self.a2s_author.get() or "sidconverter"
        released = self.a2s_released.get() or "2026"
        voices = self.a2s_voices.get()
        waveform = self.a2s_waveform.get()
        adsr = self.a2s_adsr.get() or "0,0,15,0"

        def go() -> None:
            n, secs = audio_to_sid.convert_audio(
                src, out, name=name, author=author, released=released,
                voices=voices, waveform=waveform, adsr=adsr,
            )
            print(f"wrote {out}  ({n} notes, {secs:.1f}s, {voices} voice(s), {waveform})")

        self._run_async("audio -> sid", go)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sidconverter-gui", description="SID toolkit GUI")
    parser.parse_args(argv)
    try:
        root = TkinterDnD.Tk() if _DND_AVAILABLE else tk.Tk()
    except tk.TclError as e:
        print(f"error: cannot open display ({e}). Use the CLI instead.", file=sys.stderr)
        return 1
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
