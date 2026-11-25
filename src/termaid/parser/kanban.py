"""Parser for Mermaid kanban diagrams.

Syntax:
    kanban
        Todo
            Design homepage
            id2[Fix login bug]@{ assigned: 'ana', priority: 'High', ticket: MC-12 }
        In Progress
            API integration
        Done
            Database setup
"""
from __future__ import annotations

import re

from ..model.kanban import Kanban, KanbanColumn, KanbanCard
from ..utils import line_breaks, without_meta_lines

# Shape data counts only at the end of a card, as in Mermaid.
_SHAPE_DATA = re.compile(r"@\{(.*)\}\s*$")
_FIELD = re.compile(r"""(\w+)\s*:\s*("[^"]*"|'[^']*'|[^,]*)""")


def _clean_title(text: str) -> str:
    """Extract the display title, handling the id[Title] form and text after it."""
    m = re.match(r'^[\w-]*\[(.+)\]((?:\s.*)?)$', text)
    if m:
        text = m.group(1) + m.group(2)
    return line_breaks(text.strip().strip("\"'"), " ")


def _card(text: str) -> KanbanCard:
    fields: dict[str, str] = {}
    m = _SHAPE_DATA.search(text)
    if m:
        text = text[:m.start()].rstrip()
        for key, value in _FIELD.findall(m.group(1)):
            fields[key] = value.strip().strip("\"'")
    return KanbanCard(
        title=_clean_title(text),
        assigned=fields.get("assigned", ""),
        ticket=fields.get("ticket", ""),
        priority=fields.get("priority", ""),
    )


def parse_kanban(text: str) -> Kanban:
    """Parse a mermaid kanban definition."""
    lines = text.strip().splitlines()
    kb = Kanban()

    if not lines:
        return kb

    # Detect indentation levels: columns are at one level, cards at a deeper level
    body_lines: list[tuple[int, str]] = []
    for line in without_meta_lines(lines[1:]):  # skip "kanban" header
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
            current_column = KanbanColumn(title=_card(text).title)
            kb.columns.append(current_column)
        else:
            if current_column is None:
                current_column = KanbanColumn(title="")
                kb.columns.append(current_column)
            current_column.cards.append(_card(text))

    return kb
