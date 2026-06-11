"""Parser for Mermaid kanban diagrams.

Syntax:
    kanban
        Todo
            Design homepage
            Fix login bug
        In Progress
            API integration
        Done
            Database setup
"""
from __future__ import annotations

import re

from ..model.kanban import Kanban, KanbanColumn, KanbanCard


def _clean_title(text: str) -> str:
    """Extract the display title, handling the id[Title] form."""
    m = re.match(r'^[\w-]*\[(.+)\]$', text)
    if m:
        text = m.group(1)
    return text.strip().strip("\"'")


def parse_kanban(text: str) -> Kanban:
    """Parse a mermaid kanban definition."""
    lines = text.strip().splitlines()
    kb = Kanban()

    if not lines:
        return kb

    # Detect indentation levels: columns are at one level, cards at a deeper level
    body_lines: list[tuple[int, str]] = []
    for line in lines[1:]:  # skip "kanban" header
        comment_idx = line.find("%%")
        if comment_idx >= 0:
            line = line[:comment_idx]

        stripped = line.rstrip()
        if not stripped.strip():
            continue

        indent = len(stripped) - len(stripped.lstrip())
        body_lines.append((indent, stripped.strip()))

    if not body_lines:
        return kb

    # Find column indent level (the minimum indent)
    min_indent = min(indent for indent, _ in body_lines)

    current_column: KanbanColumn | None = None

    for indent, text in body_lines:
        if indent <= min_indent:
            # Column header
            current_column = KanbanColumn(title=_clean_title(text))
            kb.columns.append(current_column)
        else:
            # Card
            if current_column is None:
                current_column = KanbanColumn(title="")
                kb.columns.append(current_column)

            # Extract metadata ("card title @tag") before unwrapping id[Title]
            metadata = ""
            if "@" in text:
                parts = text.rsplit("@", 1)
                text = parts[0].strip()
                metadata = "@" + parts[1].strip()

            current_column.cards.append(
                KanbanCard(title=_clean_title(text), metadata=metadata)
            )

    return kb
