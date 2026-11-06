"""Data model for ER (Entity Relationship) diagrams."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Attribute:
    type: str                          # e.g., "string", "int", "varchar(255)"
    name: str                          # e.g., "id", "name"
    keys: list[str] = field(default_factory=list)  # ["PK"], ["FK"], ["PK", "FK"]
    comment: str = ""                  # optional comment text


@dataclass
class Entity:
    name: str
    alias: str = ""                    # display label (from p[Person] syntax)
    attributes: list[Attribute] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        return self.alias or self.name


@dataclass
class Relationship:
    entity1: str
    entity2: str
    card1: str                         # left cardinality: "||", "|o", "}|", "}o"
    card2: str                         # right cardinality: "||", "o|", "|{", "o{"
    line_style: str = "solid"          # "solid" (identifying) or "dashed" (non-identifying)
    label: str = ""


@dataclass
class ERDiagram:
    entities: dict[str, Entity] = field(default_factory=dict)
    relationships: list[Relationship] = field(default_factory=list)
    direction: str = "TB"              # "TB" or "LR"
    warnings: list[str] = field(default_factory=list)
