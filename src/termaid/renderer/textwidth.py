"""Unicode-aware text width utilities for terminal rendering.

CJK (Chinese, Japanese, Korean) and other full-width characters occupy
2 terminal columns, while most Latin/ASCII characters occupy 1.
This module provides functions to compute display width correctly,
replacing naive ``len()`` calls throughout the rendering pipeline.

Uses only the standard library (``unicodedata``), keeping termaid's
zero-runtime-dependency guarantee.

CJK mode
--------
In CJK terminals (Korean, Chinese, Japanese locale), certain
"East Asian Ambiguous" characters — geometric shapes like ``◇ ● ▲ ▼``
and block elements like ``█ ▓ ▒`` — render as **2 columns**, while
box-drawing characters (``─ │ ┌ ┐``) remain **1 column**.

When CJK mode is enabled (auto-detected or via ``--cjk`` flag), these
ambiguous geometric / block characters are counted as 2 columns so that
diamond markers, state-diagram circles, and pie-chart bars stay aligned
with surrounding box-drawing borders.
"""
from __future__ import annotations

import os
import sys
import unicodedata

# ---------------------------------------------------------------------------
# CJK-ambiguous characters that render as 2 columns in CJK terminals
# but 1 column in Western terminals.  Box-drawing characters (U+2500–257F)
# are intentionally excluded — they stay 1 column everywhere.
# ---------------------------------------------------------------------------
_CJK_WIDE_AMBIGUOUS: set[str] = set(
    # Geometric Shapes used as border markers (inside box outlines).
    # These MUST be 2-column in CJK mode so borders align with body rows.
    "◇◆●○◯"
    "■□▪▫"
    # Note: ▲▼△▽ (directional arrows / inheritance triangles) are
    # intentionally excluded.  They are standalone markers placed at
    # edge endpoints, and treating them as 2 columns causes adjacent
    # markers (e.g. class diagram inheritance △△) to overlap.
    # Note: Block Elements (█▓▒ etc.) are also excluded — they are
    # bar-chart fill characters that must stay 1-column.
    # Miscellaneous Symbols
    "✖"
)

# Characters that have EAW=N (Narrow) but render as 2 columns in CJK
# terminals due to font choices.  Tracked separately because they are
# NOT flagged by ``unicodedata.east_asian_width``.
_CJK_WIDE_NARROW: set[str] = set("◉")

# Module-level switch — set via ``set_cjk_mode()`` or auto-detected.
_cjk_mode: bool = False


# ---------------------------------------------------------------------------
# Auto-detection
# ---------------------------------------------------------------------------

def _detect_cjk() -> bool:
    """Return True if the terminal is likely a CJK environment."""
    # Explicit opt-in / opt-out via environment variable
    env = os.environ.get("TERMAID_CJK", "").lower()
    if env in ("1", "true", "yes"):
        return True
    if env in ("0", "false", "no"):
        return False

    # Windows: check console output code page
    if sys.platform == "win32":
        try:
            import ctypes
            cp = ctypes.windll.kernel32.GetConsoleOutputCP()
            # 932=Japanese, 936=Simplified Chinese, 949=Korean, 950=Traditional Chinese
            if cp in (932, 936, 949, 950):
                return True
        except Exception:
            pass

    # Unix: check LANG / LC_ALL / LC_CTYPE
    for var in ("LC_ALL", "LC_CTYPE", "LANG"):
        val = os.environ.get(var, "").lower()
        if any(tag in val for tag in ("ja", "ko", "zh")):
            return True

    return False


def set_cjk_mode(enabled: bool) -> None:
    """Enable or disable CJK-ambiguous-width mode globally."""
    global _cjk_mode
    _cjk_mode = enabled


def is_cjk_mode() -> bool:
    """Return the current CJK mode setting."""
    return _cjk_mode


# ---------------------------------------------------------------------------
# Width calculation
# ---------------------------------------------------------------------------

def char_width(ch: str) -> int:
    """Return the display width of a single character in terminal columns.

    Full-width (F) and wide (W) characters always return 2.
    In CJK mode, specific ambiguous geometric/block characters also return 2.
    Everything else returns 1.
    """
    eaw = unicodedata.east_asian_width(ch)
    if eaw in ("W", "F"):
        return 2
    if _cjk_mode:
        if eaw == "A" and ch in _CJK_WIDE_AMBIGUOUS:
            return 2
        if ch in _CJK_WIDE_NARROW:
            return 2
    return 1


def display_width(text: str) -> int:
    """Return the total display width of *text* in terminal columns."""
    return sum(char_width(ch) for ch in text)


def display_rjust(text: str, width: int) -> str:
    """Right-justify *text* to *width* display columns."""
    pad = width - display_width(text)
    return " " * max(0, pad) + text


def display_ljust(text: str, width: int) -> str:
    """Left-justify *text* to *width* display columns."""
    pad = width - display_width(text)
    return text + " " * max(0, pad)


# ---------------------------------------------------------------------------
# Default: OFF.  CJK-ambiguous marker width varies across terminal fonts
# even on CJK systems, so auto-detection is unreliable.  Users who need
# wide markers should opt in via ``--cjk`` or ``TERMAID_CJK=1``.
# ---------------------------------------------------------------------------
_cjk_mode = _detect_cjk() if os.environ.get("TERMAID_CJK") else False
