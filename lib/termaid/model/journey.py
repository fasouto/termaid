"""Data model for user journey diagrams."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class JourneyTask:
    title: str
    score: int = 3       # 1-5 satisfaction
    actors: list[str] = field(default_factory=list)


@dataclass
class JourneySection:
    title: str
    tasks: list[JourneyTask] = field(default_factory=list)


@dataclass
class Journey:
    title: str = ""
    sections: list[JourneySection] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
