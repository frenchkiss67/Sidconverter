#!/usr/bin/env python3
"""Thin wrapper: python3 audio_to_sid.py INPUT -o OUT [--name N] [--author A] [--released R]"""
import sys
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sidconverter.audio_to_sid import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
