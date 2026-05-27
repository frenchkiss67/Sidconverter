#!/usr/bin/env python3
"""Thin wrapper: python3 sid_format_convert.py FILE -o OUT --to {PSID|RSID} [--force]"""
import sys
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sidconverter.format_convert import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
