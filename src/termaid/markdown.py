"""Find Mermaid diagrams in Markdown.

Lets the CLI render a whole document, with each ```mermaid block drawn
in place and everything else passed through untouched:

    termaid --markdown README.md
    gh pr view 42 | termaid --markdown
"""
from __future__ import annotations

from dataclasses import dataclass

from .utils import OPEN_FENCE, closes_fence, unfence


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

    Lines are split on ``\n`` only, so a CRLF document keeps its ``\r``
    characters in the text segments and in ``raw``, and rejoining the
    segments with ``\n`` gives back the input exactly. The ``\r`` is
    dropped from the diagram source itself. Files opened in text mode
    arrive with LF endings, but piped stdin keeps CRLF.
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
        match = OPEN_FENCE.match(lines[i])
        fence = match.group("fence") if match else ""
        # Backtick fences cannot have backticks in their info string.
        if not match or (fence[0] == "`" and "`" in match.group("info")):
            pending.append(lines[i])
            i += 1
            continue

        indent = match.group("indent")
        body: list[str] = []
        end = None
        for j in range(i + 1, len(lines)):
            line = unfence(lines[j], indent)
            if line is None:
                break  # the blockquote holding the fence ended first
            if closes_fence(line, fence):
                end = j
                break
            body.append(line.rstrip("\r"))
        words = match.group("info").split()
        is_mermaid = bool(words) and words[0].lower() == "mermaid"

        if end is None or not is_mermaid:
            # Not a diagram: keep the whole block, unsearched, as text.
            stop = i + 1 + len(body) if end is None else end + 1
            pending.extend(lines[i:stop])
            i = stop
            continue

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
