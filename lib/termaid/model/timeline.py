"""Data model for timeline diagrams."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TimelineEvent:
    title: str
    details: list[str] = field(default_factory=list)


@dataclass
class TimelineSection:
    title: str
    events: list[TimelineEvent] = field(default_factory=list)


@dataclass
class Timeline:
    title: str = ""
    sections: list[TimelineSection] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
