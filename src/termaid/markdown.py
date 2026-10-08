"""Find Mermaid diagrams in Markdown.

Lets the CLI render a whole document, with each ```mermaid block drawn
in place and everything else passed through untouched:

    termaid --markdown README.md
    gh pr view 42 | termaid --markdown
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# An opening fence: three or more backticks or tildes, then an info string.
# Any indentation is accepted so that diagrams nested in list items are
# found; the indent is removed from the diagram's lines.
_OPEN = re.compile(r"^(?P<indent>[ \t]*)(?P<fence>`{3,}|~{3,})(?P<info>.*)$")


@dataclass
class Segment:
    """A run of Markdown text, or one Mermaid diagram.

    For a diagram, ``text`` is the Mermaid source with the fence's
    indentation removed, ``raw`` is the original fenced block (for showing
    it unchanged when it cannot be rendered), and ``indent`` is the
    fence's indentation.
    """

    text: str
    is_mermaid: bool = False
    raw: str = ""
    indent: str = ""
    line: int = 0


def split_markdown(text: str) -> list[Segment]:
    """Split Markdown into text segments and Mermaid diagram segments.

    Only fences whose info string starts with ``mermaid`` become diagrams.
    Other fenced blocks are kept as text and not searched, so a Mermaid
    example quoted inside a longer fence stays as it is. A Mermaid fence
    that is never closed is kept as text too.
    """
    lines = text.split("\n")
    segments: list[Segment] = []
    pending: list[str] = []

    def flush() -> None:
        if pending:
            segments.append(Segment("\n".join(pending)))
            pending.clear()

    i = 0
    while i < len(lines):
        match = _OPEN.match(lines[i])
        fence = match.group("fence") if match else ""
        # Backtick fences cannot have backticks in their info string.
        if not match or (fence[0] == "`" and "`" in match.group("info")):
            pending.append(lines[i])
            i += 1
            continue

        close = re.compile(r"^[ \t]*" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}[ \t]*$")
        end = next((j for j in range(i + 1, len(lines)) if close.match(lines[j])), None)
        words = match.group("info").split()
        is_mermaid = bool(words) and words[0].lower() == "mermaid"

        if end is None or not is_mermaid:
            # Not a diagram: keep the whole block, unsearched, as text.
            stop = len(lines) if end is None else end + 1
            pending.extend(lines[i:stop])
            i = stop
            continue

        indent = match.group("indent")
        body = [_dedent(line, len(indent)) for line in lines[i + 1:end]]
        flush()
        segments.append(Segment(
            "\n".join(body),
            is_mermaid=True,
            raw="\n".join(lines[i:end + 1]),
            indent=indent,
            line=i + 1,
        ))
        i = end + 1

    flush()
    return segments


def _dedent(line: str, width: int) -> str:
    """Remove up to ``width`` leading whitespace characters from a line."""
    n = 0
    while n < width and n < len(line) and line[n] in " \t":
        n += 1
    return line[n:]
