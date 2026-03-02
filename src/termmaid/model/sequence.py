"""Data model for sequence diagrams."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Participant:
    id: str
    label: str
    kind: str = "participant"
    # "participant" | "actor" | "database" | "queue" | "boundary" | "control" | "entity" | "collections"


@dataclass
class Message:
    source: str
    target: str
    label: str = ""
    line_type: str = "solid"   # "solid" or "dotted"
    arrow_type: str = "arrow"  # "arrow", "cross", "open", "async", "bidirectional"


@dataclass
class Note:
    text: str
    position: str          # "rightof", "leftof", "over"
    participants: list[str] = field(default_factory=list)  # participant ids


@dataclass
class SequenceDiagram:
    participants: list[Participant] = field(default_factory=list)
    events: list[Message | Note] = field(default_factory=list)
    autonumber: bool = False
