"""Data model for kanban diagrams."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class KanbanCard:
    title: str
    # From the card's ``@{ … }`` shape data, "" when not given
    assigned: str = ""
    ticket: str = ""
    priority: str = ""


@dataclass
class KanbanColumn:
    title: str
    cards: list[KanbanCard] = field(default_factory=list)


@dataclass
class Kanban:
    title: str = ""
    columns: list[KanbanColumn] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
