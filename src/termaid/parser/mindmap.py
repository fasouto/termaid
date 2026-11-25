"""Parser for Mermaid mindmap diagrams.

Syntax (indentation-based):
    mindmap
      Root
        Branch A
          Leaf 1
          Leaf 2
        Branch B
          Leaf 3
"""
from __future__ import annotations

import re

from ..model.mindmap import Mindmap, MindmapNode
from ..utils import line_breaks, without_meta_lines
from .flowchart import _join_open_strings, _parse_markdown_label


# Shape markers, longest first: an id may come before any of them.
_SHAPES = (
    ("((", "))"),    # circle
    ("))", "(("),    # bang
    ("{{", "}}"),    # hexagon
    (")", "("),      # cloud
    ("(", ")"),      # round
    ("[", "]"),      # square
)
_ID = re.compile(r"[\w-]*")


def _label(text: str) -> str:
    """The text of a node written as ``id((text))``, ``[text]`` and so on.

    Line breaks in the text come back as ``\\n``.
    """
    rest = text[_ID.match(text).end():]
    for opener, closer in _SHAPES:
        if rest.startswith(opener) and rest.endswith(closer) and len(rest) > len(opener) + len(closer):
            inner = rest[len(opener):-len(closer)].strip()
            text = inner or text
            break
    markdown = _parse_markdown_label(text)
    if markdown is not None:
        return markdown[0].replace("\\n", "\n")  # the flowchart parser marks breaks as a literal \n
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"`":
        text = text.strip(text[0])
    return line_breaks(text)


def parse_mindmap(text: str) -> Mindmap:
    """Parse a mermaid mindmap definition."""
    lines = text.strip().splitlines()
    mindmap = Mindmap()

    if not lines:
        return mindmap

    # Skip header line (mindmap)
    body_lines: list[tuple[int, str]] = []
    for line in _join_open_strings(list(without_meta_lines(lines[1:]))):
        # Strip comments
        comment_idx = line.find("%%")
        if comment_idx >= 0:
            line = line[:comment_idx]

        stripped = line.rstrip()
        if not stripped.strip():
            continue

        # Measure indentation
        indent = len(stripped) - len(stripped.lstrip())
        label = stripped.strip()

        # `::icon(...)` and `:::class` lines decorate the node above them.
        if label.startswith("::"):
            continue

        body_lines.append((indent, _label(label)))

    if not body_lines:
        return mindmap

    # Build tree from indentation
    stack: list[tuple[int, MindmapNode]] = []

    for indent, label in body_lines:
        node = MindmapNode(label=label)

        # Pop stack until we find a parent with less indentation
        while stack and stack[-1][0] >= indent:
            stack.pop()

        if stack:
            stack[-1][1].children.append(node)
        elif mindmap.root is None:
            mindmap.root = node
        else:
            # Multiple roots: attach to existing root
            mindmap.root.children.append(node)

        stack.append((indent, node))

    return mindmap
