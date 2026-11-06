"""Data model for sequence diagrams."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union


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
class ActivateEvent:
    participant: str
    active: bool  # True = activate, False = deactivate


@dataclass
class BlockSection:
    label: str = ""
    events: list = field(default_factory=list)


@dataclass
class Block:
    kind: str  # "loop", "alt", "opt", "par", "critical", "break"
    label: str = ""
    events: list = field(default_factory=list)
    sections: list[BlockSection] = field(default_factory=list)


@dataclass
class DestroyEvent:
    participant: str


# Union type for all event types
Event = Union[Message, Note, ActivateEvent, Block, DestroyEvent]


@dataclass
class SequenceDiagram:
    participants: list[Participant] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    autonumber: bool = False
    warnings: list[str] = field(default_factory=list)
