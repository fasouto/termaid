"""Shared utility functions for termaid."""
from __future__ import annotations

import re
import unicodedata

# A %%{...}%% directive, which may span lines. It ends at the next %%{, so an
# unclosed one is not rescanned to the end of the source from every later %%{.
DIRECTIVE = r"%%\{(?s:(?:(?!%%\{).)*?)\}%%"

_BR = re.compile(r"\s*<br\s*/?>\s*", re.IGNORECASE)


def line_breaks(text: str, sep: str = "\n") -> str:
    """Replace Mermaid's ``<br>``, ``<br/>`` and ``<br />`` (and the spaces around them) with *sep*.

    Mermaid draws them as line breaks in every kind of label. Pass ``" "``
    where a label has a single row.
    """
    return _BR.sub(lambda _: sep, text)  # sep as given: "\\n" stays a backslash and n


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


def max_line_width(text: str) -> int:
    """Return the display width of the widest line in *text*."""
    lines = text.split("\n")
    # Without wide characters a line's width is its length. Fitting measures
    # every candidate drawing, and checking each character took longer than
    # the renders did.
    if not any(_is_wide(ch) for ch in set(text)):
        return max(map(len, lines))
    return max(display_width(line) for line in lines)


def fit_to_width(render, result, target_width: int, *, gap: int = 4, padding_x: int = 4, plain=str):
    """Fit a drawing to *target_width* columns, or get as close as it can.

    *render* draws the diagram with keyword overrides (``gap``,
    ``padding_x``, ``max_label_width``) and *result* is its drawing at
    *gap* and *padding_x*. Spacing shrinks one step at a time. If that is
    not enough, labels wrap at word boundaries, at the widest label width
    that fits. When nothing fits, the narrowest drawing tried comes back.
    *plain* gives a drawing's text, for drawings that are not strings.
    """
    def width_of(candidate) -> int:
        return max_line_width(plain(candidate))

    if width_of(result) <= target_width:
        return result

    for step_gap, step_padding in ((min(gap, 2), padding_x), (1, padding_x), (1, 2), (1, 0)):
        if step_gap >= gap and step_padding >= padding_x:
            continue
        candidate = render(gap=step_gap, padding_x=step_padding)
        if width_of(candidate) <= target_width:
            return candidate
        result = candidate

    # Spacing alone was not enough: wrap labels and keep the widest label
    # width that fits. Width 1 goes first: if it changes nothing, this diagram
    # type ignores label width; if it still overflows, nothing will fit.
    narrowest = render(gap=1, padding_x=0, max_label_width=1)
    if plain(narrowest) != plain(result):
        result = narrowest
        if width_of(narrowest) <= target_width:
            low, high = 2, min(target_width, 64)
            while low <= high:
                label_width = (low + high) // 2
                candidate = render(gap=1, padding_x=0, max_label_width=label_width)
                if width_of(candidate) <= target_width:
                    result = candidate
                    low = label_width + 1
                else:
                    high = label_width - 1
    return result


def _text_break(text: str, cell_limit_end: int) -> int:
    """Find the last word or identifier boundary inside a display-cell budget.

    Keep member-access punctuation with the following name, separators with
    the preceding segment, and camel-case/acronym components intact when they
    fit. This is a layout heuristic, not a parser or a language tokenizer.
    """
    preferred_end = 0
    for index in range(1, min(cell_limit_end + 1, len(text))):
        previous = text[index - 1]
        current = text[index]
        following = text[index + 1:index + 2]
        member_access = (
            current == "." and not previous.isdigit()
            or current == ":" and following == ":" and previous != ":"
        )
        separator = previous in "_-/,;!?，；！？" and current not in "_-/,;!?，；！？"
        script_boundary = (
            previous.isalpha() and current.isalpha()
            and _is_wide(previous) != _is_wide(current)
        )
        camel_case = current.isupper() and (
            previous.islower() or previous.isdigit()
            or previous.isupper() and following.islower()
        )
        if member_access or separator or camel_case or script_boundary:
            preferred_end = index
    return preferred_end


def wrap_display_text(
    text: str,
    max_width: int,
    *,
    hard_break: bool = True,
) -> list[str]:
    """Wrap text to terminal display cells, hard-breaking long tokens.

    Prefer whitespace, then punctuation, script changes, and identifier
    boundaries (member access, separators, and camel case), before splitting
    a token by display cells. Explicit newlines are preserved. With
    ``hard_break=False`` a token wider than ``max_width`` stays whole.
    """
    if max_width < 1:
        raise ValueError("max_width must be positive")

    wrapped: list[str] = []
    for logical_line in text.split("\n"):
        if not hard_break:
            words = logical_line.split()
            if not words:
                wrapped.append(logical_line)
                continue
            current = words[0]
            for word in words[1:]:
                if display_width(current) + 1 + display_width(word) <= max_width:
                    current += " " + word
                else:
                    wrapped.append(current)
                    current = word
            wrapped.append(current)
            continue

        remaining = logical_line
        if remaining == "":
            wrapped.append("")
            continue

        while display_width(remaining) > max_width:
            used = 0
            end = 0
            last_space = -1
            for index, ch in enumerate(remaining):
                char_width = 2 if _is_wide(ch) else 1
                if used + char_width > max_width:
                    break
                used += char_width
                end = index + 1
                if ch.isspace():
                    last_space = end

            # A width of one cannot contain a wide glyph. Keep the glyph
            # intact and let the caller decide that the constraint is
            # unsatisfiable rather than looping forever or corrupting UTF-8.
            if end == 0:
                end = 1

            # A word ending exactly at the limit fits even if its following
            # space lies outside the scan. Commas may be better boundaries
            # than an earlier space in mixed prose and identifiers.
            word_end = end if remaining[end:end + 1].isspace() else last_space
            phrase_end = max((
                index + 1 for index, character in enumerate(remaining[:end])
                if character in ",;，；!?！？"
            ), default=0)
            prose_end = max(word_end, phrase_end)
            boundary_end = _text_break(remaining, end) if prose_end <= 0 else 0
            split_at = prose_end if prose_end > 0 else boundary_end or end
            # Avoid orphaning a short ending when a preceding clause boundary
            # keeps the following phrase together within the same budget.
            if (
                0 < phrase_end < split_at
                and display_width(remaining[split_at:].strip()) <= max_width // 3
                and display_width(remaining[phrase_end:].strip()) <= max_width
            ):
                split_at = phrase_end
            line = remaining[:split_at].rstrip()
            if not line:
                line = remaining[:end]
                split_at = end
            wrapped.append(line)
            remaining = remaining[split_at:].lstrip()

        wrapped.append(remaining.rstrip())

    return wrapped


def truncate_to_width(text: str, width: int, ellipsis: str = ".") -> str:
    """Truncate *text* so its display width fits in *width* columns.

    Appends *ellipsis* when truncation happens. Never splits a wide
    character: the result's display width is always <= width.
    """
    if display_width(text) <= width:
        return text

    def clip(s: str, cols: int) -> str:
        out: list[str] = []
        w = 0
        for ch in s:
            cw = 2 if _is_wide(ch) else 1
            if w + cw > cols:
                break
            out.append(ch)
            w += cw
        return "".join(out)

    ell_w = display_width(ellipsis)
    if width <= ell_w:
        return clip(ellipsis, width)
    return clip(text, width - ell_w) + ellipsis
