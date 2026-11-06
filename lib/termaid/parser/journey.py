"""Parser for Mermaid user journey diagrams.

Syntax:
    journey
        title My working day
        section Go to work
            Make tea: 5: Me
            Go upstairs: 3: Me
            Do work: 1: Me, Cat
        section Go home
            Go downstairs: 5: Me
            Sit down: 5: Me
"""
from __future__ import annotations

from ..model.journey import Journey, JourneySection, JourneyTask


def parse_journey(text: str) -> Journey:
    """Parse a mermaid user journey definition."""
    lines = text.strip().splitlines()
    journey = Journey()

    if not lines:
        return journey

    current_section: JourneySection | None = None

    for line in lines[1:]:  # skip "journey" header
        comment_idx = line.find("%%")
        if comment_idx >= 0:
            line = line[:comment_idx]

        stripped = line.strip()
        if not stripped:
            continue

        lower = stripped.lower()

        if lower.startswith("title "):
            journey.title = stripped[6:].strip()
            continue

        if lower.startswith("section "):
            current_section = JourneySection(title=stripped[8:].strip())
            journey.sections.append(current_section)
            continue

        # Task: "Task name: score: actor1, actor2"
        if ":" in stripped:
            parts = stripped.split(":")
            title = parts[0].strip()
            score = 3
            actors: list[str] = []

            if len(parts) >= 2:
                try:
                    score = int(parts[1].strip())
                    score = max(1, min(5, score))
                except ValueError:
                    pass

            if len(parts) >= 3:
                actors = [a.strip() for a in parts[2].split(",") if a.strip()]

            if current_section is None:
                current_section = JourneySection(title="")
                journey.sections.append(current_section)

            current_section.tasks.append(JourneyTask(
                title=title, score=score, actors=actors,
            ))

    return journey
