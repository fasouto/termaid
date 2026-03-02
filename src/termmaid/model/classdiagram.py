"""Data model for class diagrams."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Member:
    name: str                          # display text (e.g., "makeSound()")
    visibility: str = ""               # "+", "-", "#", "~"
    return_type: str = ""              # e.g., "void"
    is_method: bool = False
    classifier: str = ""               # "*" (abstract), "$" (static)


@dataclass
class ClassDef:
    name: str
    annotation: str = ""               # "interface", "abstract", "enumeration", "service"
    members: list[Member] = field(default_factory=list)


@dataclass
class Relationship:
    source: str
    target: str
    source_marker: str = ""            # "<|", "*", "o", "<", ""
    target_marker: str = ""            # "|>", "*", "o", ">", ""
    line_style: str = "solid"          # "solid" or "dashed"
    label: str = ""
    source_card: str = ""              # "1", "0..*", etc.
    target_card: str = ""


@dataclass
class Note:
    text: str                          # display text (may contain literal \n)
    target: str = ""                   # class name for "note for X", empty for floating


@dataclass
class ClassDiagram:
    classes: dict[str, ClassDef] = field(default_factory=dict)
    relationships: list[Relationship] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)
    direction: str = "TB"              # "TB" or "LR"
