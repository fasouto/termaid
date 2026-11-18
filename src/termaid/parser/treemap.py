"""Parser for Mermaid treemap diagrams.

Syntax:
    treemap-beta
    "Section 1"
        "Leaf 1.1": 12
        "Section 1.2"
            "Leaf 1.2.1": 12
    "Section 2"
        "Leaf 2.1": 20
"""
from __future__ import annotations

import re

from ..model.treemap import Treemap, TreemapNode

# Drawing recurses once per level, so nodes nested deeper than this are
# left out to stay well inside Python's recursion limit.
_MAX_DEPTH = 100

_NODE_RE = re.compile(r'^(\s*)"([^"]+)"(?:\s*:\s*([0-9]+(?:\.[0-9]*)?))?')


def parse_treemap(text: str) -> Treemap:
    """Parse a mermaid treemap definition."""
    lines = text.strip().splitlines()
    treemap = Treemap()

    if not lines:
        return treemap

    # Skip header line (treemap-beta)
    body_lines: list[tuple[int, str, float]] = []
    for line in lines[1:]:
        # Strip comments
        comment_idx = line.find("%%")
        if comment_idx >= 0:
            line = line[:comment_idx]

        m = _NODE_RE.match(line)
        if not m:
            continue

        indent = len(m.group(1))
        label = m.group(2)
        value = float(m.group(3)) if m.group(3) else 0
        body_lines.append((indent, label, value))

    if not body_lines:
        return treemap

    # Build tree from indentation
    # Stack: (indent_level, node)
    stack: list[tuple[int, TreemapNode]] = []

    too_deep = False
    for indent, label, value in body_lines:
        node = TreemapNode(label=label, value=value)

        # Pop stack until we find a parent with less indentation
        while stack and stack[-1][0] >= indent:
            stack.pop()

        if len(stack) >= _MAX_DEPTH:
            if not too_deep:
                treemap.warnings.append(f"Nodes nested deeper than {_MAX_DEPTH} levels are left out")
                too_deep = True
            continue

        if stack:
            stack[-1][1].children.append(node)
        else:
            treemap.roots.append(node)

        stack.append((indent, node))

    return treemap
