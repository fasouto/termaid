"""Parser for Mermaid timeline diagrams.

Syntax:
    timeline
        title My Project
        section Phase 1
            Design : Wireframes, Mockups
            Review : Stakeholder sign-off
        section Phase 2
            Build : Frontend, Backend
"""
from __future__ import annotations

import re

from ..model.timeline import Timeline, TimelineSection, TimelineEvent


def parse_timeline(text: str) -> Timeline:
    """Parse a mermaid timeline definition."""
    lines = text.strip().splitlines()
    tl = Timeline()

    if not lines:
        return tl

    current_section: TimelineSection | None = None

    for line in lines[1:]:  # skip "timeline" header
        # Strip comments
        comment_idx = line.find("%%")
        if comment_idx >= 0:
            line = line[:comment_idx]

        stripped = line.strip()
        if not stripped:
            continue

        # Title
        if stripped.lower().startswith("title "):
            tl.title = stripped[6:].strip()
            continue

        # Section
        if stripped.lower().startswith("section "):
            current_section = TimelineSection(title=stripped[8:].strip())
            tl.sections.append(current_section)
            continue

        # Event: "Event name : detail1, detail2" or just "Event name"
        if current_section is None:
            # Auto-create a default section
            current_section = TimelineSection(title="")
            tl.sections.append(current_section)

        if " : " in stripped:
            title, details_str = stripped.split(" : ", 1)
            details = [d.strip() for d in details_str.split(",") if d.strip()]
        else:
            title = stripped
            details = []

        current_section.events.append(TimelineEvent(
            title=title.strip(),
            details=details,
        ))

    return tl
