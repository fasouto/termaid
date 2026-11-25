"""Parser for Mermaid timeline diagrams.

Syntax:
    timeline
        title My Project
        section Phase 1
            Design : Wireframes : Mockups
                   : Prototype
            Review : Stakeholder sign-off
        section Phase 2
            Build : Frontend, Backend

A period is followed by its events, each after a colon and a space. A line
that starts with a colon adds events to the period above. Commas are text.
"""
from __future__ import annotations

import re

from ..model.timeline import Timeline, TimelineSection, TimelineEvent
from ..utils import is_meta_line, line_breaks

# Mermaid's lexer starts an event at a colon followed by whitespace, so
# "10:30" stays one word.
_EVENT_SEP = re.compile(r"\s*:(?:\s+|$)")


def parse_timeline(text: str) -> Timeline:
    """Parse a mermaid timeline definition."""
    lines = text.strip().splitlines()
    tl = Timeline()

    if not lines:
        return tl

    current_section: TimelineSection | None = None
    in_descr = False

    for line in lines[1:]:  # skip "timeline" header
        # Strip comments
        comment_idx = line.find("%%")
        if comment_idx >= 0:
            line = line[:comment_idx]

        stripped = line.strip()
        if not stripped:
            continue
        if in_descr:
            in_descr = "}" not in stripped
            continue
        if is_meta_line(stripped):
            in_descr = stripped.startswith("accDescr") and stripped[8:].lstrip()[:1] == "{" and "}" not in stripped
            continue

        # Title
        if stripped.lower().startswith("title "):
            tl.title = line_breaks(stripped[6:].strip(), " ")
            continue

        # Section
        if stripped.lower().startswith("section "):
            current_section = TimelineSection(title=line_breaks(stripped[8:].strip(), " "))
            tl.sections.append(current_section)
            continue

        # Event: "Event name : detail1, detail2" or just "Event name"
        if current_section is None:
            # Auto-create a default section
            current_section = TimelineSection(title="")
            tl.sections.append(current_section)

        title, *events = _EVENT_SEP.split(stripped)
        # An event may break over rows; a period's title has one.
        details = [line_breaks(e.strip()) for e in events if e.strip()]
        if not title and current_section.events:
            current_section.events[-1].details.extend(details)
        else:
            current_section.events.append(TimelineEvent(title=line_breaks(title.strip(), " "), details=details))

    return tl
