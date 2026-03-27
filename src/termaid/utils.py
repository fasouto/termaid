"""Shared utility functions for termaid."""
from __future__ import annotations

import unicodedata


def display_width(text: str) -> int:
    """Return the terminal display width of *text*.

    East-Asian wide / fullwidth characters (CJK ideographs, fullwidth
    Latin, etc.) occupy 2 terminal columns; everything else occupies 1.
    Uses only the stdlib ``unicodedata`` module – no external dependency.
    """
    w = 0
    for ch in text:
        w += 2 if unicodedata.east_asian_width(ch) in ("F", "W") else 1
    return w
