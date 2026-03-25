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


def parse_mindmap(text: str) -> Mindmap:
    """Parse a mermaid mindmap definition."""
    lines = text.strip().splitlines()
    mindmap = Mindmap()

    if not lines:
        return mindmap

    # Skip header line (mindmap)
    body_lines: list[tuple[int, str]] = []
    for line in lines[1:]:
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

        # Strip optional shape markers from Mermaid syntax:
        # (Round), [Square], {{Hexagon}}, )Cloud(, etc.
        for pattern, repl in [
            (r"^\((.+)\)$", r"\1"),        # (round)
            (r"^\[(.+)\]$", r"\1"),         # [square]
            (r"^\{\{(.+)\}\}$", r"\1"),     # {{hexagon}}
            (r"^\)(.+)\($", r"\1"),         # )cloud(
        ]:
            m = re.match(pattern, label)
            if m:
                label = m.group(1)
                break

        body_lines.append((indent, label))

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
