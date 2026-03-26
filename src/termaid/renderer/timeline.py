"""Renderer for timeline diagrams.

Renders a vertical timeline with sections and events connected by
a central vertical line.
"""
from __future__ import annotations

from ..model.timeline import Timeline
from .canvas import Canvas
from .charset import ASCII, UNICODE, CharSet


def render_timeline(
    diagram: Timeline,
    *,
    use_ascii: bool = False,
) -> Canvas:
    """Render a Timeline model to a Canvas."""
    cs = ASCII if use_ascii else UNICODE

    if not diagram.sections:
        return Canvas(1, 1)

    # Build lines with per-section styles
    styled_lines: list[tuple[str, str]] = []  # (text, style_key)

    # Title
    if diagram.title:
        styled_lines.append((diagram.title, "label"))
        styled_lines.append(("", "default"))

    v = "|" if use_ascii else "│"
    h = "-" if use_ascii else "─"
    bullet = "o" if use_ascii else "●"
    section_marker = "=" if use_ascii else "═"

    for si, section in enumerate(diagram.sections):
        style = f"section:{si}"

        # Section header
        if section.title:
            header = f" {section_marker}{section_marker} {section.title} {section_marker}{section_marker}"
            styled_lines.append((header, style))
            styled_lines.append((f" {v}", style))

        for ei, event in enumerate(section.events):
            is_last_event = ei == len(section.events) - 1
            is_last_section = si == len(diagram.sections) - 1

            styled_lines.append((f" {bullet}{h}{h} {event.title}", style))

            for detail in event.details:
                styled_lines.append((f" {v}   {detail}", "edge_label"))

            if not (is_last_event and is_last_section):
                styled_lines.append((f" {v}", style))

    # Write to canvas
    width = max((len(line) for line, _ in styled_lines), default=1) + 1
    height = len(styled_lines)
    canvas = Canvas(width, height)
    for r, (line, style) in enumerate(styled_lines):
        canvas.put_text(r, 0, line, style=style)

    return canvas
