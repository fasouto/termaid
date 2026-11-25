"""Shared utility functions for termaid."""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Iterator

# A %%{...}%% directive, which may span lines. It ends at the next %%{, so an
# unclosed one is not rescanned to the end of the source from every later %%{.
DIRECTIVE = r"%%\{(?s:(?:(?!%%\{).)*?)\}%%"

# An opening Markdown fence: three or more backticks or tildes, then an info
# string. Any indentation is accepted so that diagrams nested in list items
# are found, and so are blockquote markers; :func:`unfence` removes the
# indent from the block's lines.
OPEN_FENCE = re.compile(r"^(?P<indent>(?:[ \t]*>[ \t]?)*[ \t]*)(?P<fence>`{3,}|~{3,})(?P<info>.*)$")
_QUOTE_MARK = re.compile(r"[ \t]*>[ \t]?")


def dedent_line(line: str, width: int) -> str:
    """Remove up to ``width`` leading whitespace characters from a line."""
    n = 0
    while n < width and n < len(line) and line[n] in " \t":
        n += 1
    return line[n:]


def _unquote(line: str, depth: int) -> str | None:
    for _ in range(depth):
        match = _QUOTE_MARK.match(line)
        if match is None:
            return None
        line = line[match.end():]
    return line


def unfence(line: str, indent: str) -> str | None:
    """*line* of a fenced block whose fence had *indent*, with that indent removed.

    None when the line lacks the indent's blockquote markers, which ends
    the quote and so the block.
    """
    depth = indent.count(">")
    rest = _unquote(line, depth)
    if rest is None:
        return None
    return dedent_line(rest, len(_unquote(indent, depth)))


def closes_fence(line: str, fence: str) -> bool:
    """Whether *line*, its indent removed, closes a block opened with *fence*."""
    stripped = line.strip(" \t\r")
    return len(stripped) >= len(fence) and stripped == fence[0] * len(stripped)


_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)


def line_breaks(text: str, sep: str = "\n") -> str:
    """Replace Mermaid's ``<br>``, ``<br/>`` and ``<br />`` (and the spaces around them) with *sep*.

    Mermaid draws them as line breaks in every kind of label. Pass ``" "``
    where a label has a single row.
    """
    parts = _BR.split(text)
    if len(parts) == 1:
        return text
    # The spaces around a tag are stripped here, not matched by the pattern:
    # `\s*<br` rescans a long run of spaces from each of its positions.
    last = len(parts) - 1
    return sep.join(
        part.strip() if 0 < i < last else part.rstrip() if i == 0 else part.lstrip()
        for i, part in enumerate(parts)
    )


_META_LINE = re.compile(r"\s*(?:acc(?:Title|Descr)\s*:|accDescr\s*\{|click\s+[\w-]+\s+(?:href\b|call\b|[\"']))")


def is_meta_line(line: str) -> bool:
    """Whether *line* is an ``accTitle:``, ``accDescr:`` or ``click`` line, which Mermaid never draws."""
    return _META_LINE.match(line) is not None


def without_meta_lines(lines: Iterable[str]) -> Iterator[str]:
    """*lines* without their meta lines, an ``accDescr { … }`` block included."""
    in_block = False
    for line in lines:
        if in_block:
            in_block = "}" not in line
        elif is_meta_line(line):
            in_block = line.lstrip().startswith("accDescr") and "{" in line and "}" not in line
        else:
            yield line


_SOFT_HYPHEN = "­"
_EMOJI_PRESENTATION = "️"
# Hangul jamo vowels and finals, and the line and paragraph separators:
# drawn at zero columns, though no mark category says so.
_ZERO_WIDTH_RANGES = ((0x1160, 0x11FF), (0xD7B0, 0xD7FF), (0x2028, 0x2029))


def _is_zero_width(ch: str) -> bool:
    """Return True if a terminal draws *ch* at zero columns, on top of the
    character before it (a combining mark) or not at all (a format char)."""
    # Category, not combining class: Thai MAI HAN-AKAT and SARA I are Mn
    # with combining class 0.
    category = unicodedata.category(ch)
    if category in ("Mn", "Me"):
        return True
    if category == "Cf":
        return ch != _SOFT_HYPHEN
    cp = ord(ch)
    return any(low <= cp <= high for low, high in _ZERO_WIDTH_RANGES)


def _is_wide(ch: str) -> bool:
    """Return True if *ch* occupies 2 terminal columns."""
    return unicodedata.east_asian_width(ch) in ("F", "W")


def _cluster_width(cluster: str) -> int:
    if _is_wide(cluster[0]) or _EMOJI_PRESENTATION in cluster:
        return 2
    return 1


def iter_cells(text: str) -> Iterator[tuple[str, int]]:
    """Yield the terminal cells of *text* as ``(cluster, width)`` pairs.

    A zero-width code point shares the cell of the code point before it,
    so a Thai tone mark stays with its letter. Width is 1 or 2.
    """
    cluster = ""
    for ch in text:
        if cluster and _is_zero_width(ch):
            cluster += ch
            continue
        if cluster:
            yield cluster, _cluster_width(cluster)
        cluster = ch
    if cluster:
        yield cluster, _cluster_width(cluster)


def display_width(text: str) -> int:
    """Return the terminal display width of *text*.

    East-Asian wide / fullwidth characters and emoji presentation occupy 2
    terminal columns, combining marks 0, everything else 1.
    Uses only the stdlib ``unicodedata`` module.
    """
    if text.isascii():
        return len(text)
    return sum(width for _, width in iter_cells(text))


def max_line_width(text: str) -> int:
    """Return the display width of the widest line in *text*."""
    lines = text.split("\n")
    # Without wide or zero-width characters a line's width is its length.
    # Fitting measures every candidate drawing, and checking each character
    # took longer than the renders did.
    if text.isascii() or not any(_is_wide(ch) or _is_zero_width(ch) for ch in set(text)):
        return max(map(len, lines))
    return max(display_width(line) for line in lines)


def fit_to_width(
    render, result, target_width: int, *, gap: int = 4, padding_x: int = 4, plain=str, measure=None,
):
    """Fit a drawing to *target_width* columns, or get as close as it can.

    *render* draws the diagram with keyword overrides (``gap``,
    ``padding_x``, ``max_label_width``) and *result* is its drawing at
    *gap* and *padding_x*. Spacing shrinks one step at a time. If that is
    not enough, labels wrap at word boundaries, at the widest label width
    that fits. When nothing fits, the narrowest drawing tried comes back.
    *plain* gives a drawing's text, for drawings that are not strings.
    *measure*, when given, takes the same overrides and returns a width the
    drawing cannot be narrower than, without drawing it. A candidate it
    already puts over the target is not drawn, and it picks the label width
    to draw. A measure of 0 says nothing about the drawing.
    """
    def fitting(**overrides):
        """The drawing with *overrides* when it fits, else None."""
        if measure is not None and measure(**overrides) > target_width:
            return None
        candidate = render(**overrides)
        return candidate if max_line_width(plain(candidate)) <= target_width else None

    if max_line_width(plain(result)) <= target_width:
        return result

    for step_gap, step_padding in ((min(gap, 2), padding_x), (1, padding_x), (1, 2), (1, 0)):
        if step_gap >= gap and step_padding >= padding_x:
            continue
        candidate = fitting(gap=step_gap, padding_x=step_padding)
        if candidate is not None:
            return candidate

    # Spacing alone was not enough: wrap labels at the widest label width
    # that fits.
    widest = min(target_width, 64)

    def bound(label_width):
        return measure(gap=1, padding_x=0, max_label_width=label_width)

    narrowest = bound(1) if measure is not None else 0
    if narrowest > 0:
        # Search on the measure, which costs no drawing. A drawing can come
        # out a few columns wider than its measure, so the next narrower
        # width is drawn too before searching on drawings below it.
        label_width, low, high = 1, 2, widest
        if narrowest > target_width:
            high = 1
        elif bound(widest) <= target_width:
            label_width, high = widest, 1
        while low <= high:
            middle = (low + high) // 2
            if bound(middle) <= target_width:
                label_width, low = middle, middle + 1
            else:
                high = middle - 1
        for label_width in (label_width, label_width - 1):
            candidate = render(gap=1, padding_x=0, max_label_width=label_width)
            if label_width == 1 or max_line_width(plain(candidate)) <= target_width:
                return candidate
        widest = label_width - 1

    # Width 1 goes first: if it still overflows, nothing will fit, and it
    # comes back.
    result = render(gap=1, padding_x=0, max_label_width=1)
    if max_line_width(plain(result)) <= target_width:
        low, high = 2, widest
        while low <= high:
            label_width = (low + high) // 2
            candidate = fitting(gap=1, padding_x=0, max_label_width=label_width)
            if candidate is not None:
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
        if _is_zero_width(current):
            continue
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
            for cell, cell_width in iter_cells(remaining):
                if used + cell_width > max_width:
                    break
                used += cell_width
                end += len(cell)
                if cell.isspace():
                    last_space = end

            # A width of one cannot contain a wide glyph. Keep the glyph
            # intact and let the caller decide that the constraint is
            # unsatisfiable rather than looping forever or corrupting UTF-8.
            if end == 0:
                end = len(next(iter_cells(remaining))[0])

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
        for cell, cw in iter_cells(s):
            if w + cw > cols:
                break
            out.append(cell)
            w += cw
        return "".join(out)

    ell_w = display_width(ellipsis)
    if width <= ell_w:
        return clip(ellipsis, width)
    return clip(text, width - ell_w) + ellipsis
