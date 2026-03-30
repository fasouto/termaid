"""Shared utility functions for termaid."""
from __future__ import annotations

import unicodedata


def _is_wide(ch: str) -> bool:
    """Return True if *ch* occupies 2 terminal columns."""
    if unicodedata.east_asian_width(ch) in ("F", "W"):
        return True
    # Emoji and symbols that render wide despite east_asian_width=N
    cp = ord(ch)
    if (
        0x2600 <= cp <= 0x27BF      # Misc Symbols, Dingbats
        or 0x1F300 <= cp <= 0x1FAFF  # Emoji blocks (Misc Symbols & Pictographs through Symbols Extended-A)
        or 0xFE00 <= cp <= 0xFE0F   # Variation selectors
    ):
        return True
    return False


def display_width(text: str) -> int:
    """Return the terminal display width of *text*.

    East-Asian wide / fullwidth characters and emoji occupy 2 terminal
    columns; everything else occupies 1.
    Uses only the stdlib ``unicodedata`` module.
    """
    w = 0
    for ch in text:
        w += 2 if _is_wide(ch) else 1
    return w
