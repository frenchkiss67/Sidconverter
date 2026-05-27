# PyInstaller spec for the sidconverter standalone binary.
#
# Build with:
#     pip install pyinstaller
#     pyinstaller sidconverter.spec
#
# The result is a single-file executable in dist/sidconverter that
# bundles both the CLI and the Tkinter GUI. Launch the GUI with:
#     ./dist/sidconverter gui
#
# Note: sidplayfp and ffmpeg are NOT bundled — they must be installed
# on the target machine (they are runtime tools, not Python libraries).
# The same holds for librosa, which is only needed for non-WAV inputs
# to `from-audio`; install it in the build env if you want it included.

# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

hiddenimports = collect_submodules("sidconverter")

a = Analysis(
    ["sidconverter/__main__.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="sidconverter",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # console+GUI; `sidconverter gui` opens the Tk window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
