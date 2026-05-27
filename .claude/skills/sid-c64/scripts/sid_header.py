"""Re-export so existing imports keep working when scripts are invoked
directly (without installing the sidconverter package).
"""
import sys
import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[4]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sidconverter.header import (  # noqa: F401,E402
    HEADER_V1_SIZE,
    HEADER_V2PLUS_SIZE,
    SidHeader,
    actual_load_address,
)
