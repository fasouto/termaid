"""Renderer for user journey diagrams.

Renders a horizontal journey with tasks as boxes along a timeline,
grouped by sections, with satisfaction scores shown as emoji faces
and actor indicators.
"""
from __future__ import annotations

from ..model.journey import Journey
from ..utils import display_width
from .canvas import Canvas
from .charset import CharSet, default_charset


_FACE = {
    1: "😞",
    2: "😟",
    3: "😐",
    4: "😊",
    5: "😄",
}

_FACE_ASCII = {
    1: ":((",
    2: ":( ",
    3: ":-|",
    4: ":) ",
    5: ":D ",
}


def render_journey(
    diagram: Journey,
    *,
    use_ascii: bool = False,
    cs: CharSet | None = None,
    padding_x: int = 2,
    gap: int = 1,
    rounded: bool = True,
) -> Canvas:
    """Render a Journey model to a Canvas."""
    if not diagram.sections:
        return Canvas(1, 1)

    faces = _FACE_ASCII if use_ascii else _FACE
    hz = "-" if use_ascii else "─"
    vt = "|" if use_ascii else "│"
    if use_ascii:
        tl, tr, bl, br = "+", "+", "+", "+"
    elif rounded:
        tl, tr, bl, br = "╭", "╮", "╰", "╯"
    else:
        tl, tr, bl, br = "┌", "┐", "└", "┘"
    cs = cs or default_charset(use_ascii)
    arrow = cs.arrow_right
    dot = "o" if use_ascii else "●"

    # Collect all tasks and compute widths
    all_tasks: list[tuple[str, list[dict]]] = []  # (section_title, tasks)
    all_actors: set[str] = set()
    task_width = max(8, padding_x * 4)  # minimum task box width

    for section in diagram.sections:
        tasks_data = []
        for task in section.tasks:
            w = max(task_width, display_width(task.title) + padding_x * 2)
            tasks_data.append({"title": task.title, "score": task.score,
                               "actors": task.actors, "width": w})
            for a in task.actors:
                all_actors.add(a)
        all_tasks.append((section.title, tasks_data))

    # Layout: compute x positions for each task
    task_gap = gap
    section_gap = gap + 2
    x_pos = 2  # starting x

    task_positions: list[tuple[int, int, dict, int]] = []  # (x, w, task_data, section_idx)
    section_spans: list[tuple[int, int, str]] = []  # (x_start, x_end, title)

    for si, (sec_title, tasks) in enumerate(all_tasks):
        if si > 0:
            x_pos += section_gap
        sec_start = x_pos
        for ti, td in enumerate(tasks):
            w = td["width"]
            task_positions.append((x_pos, w, td, si))
            x_pos += w + task_gap
        sec_end = x_pos - task_gap
        section_spans.append((sec_start, sec_end, sec_title))

    total_w = x_pos + 4
    actors_list = sorted(all_actors) if all_actors else []

    # Compute rows
    title_row = 0
    actor_row = 2 if diagram.title else 0
    section_row = actor_row + len(actors_list) + 1
    timeline_row = section_row + 2
    task_row = timeline_row  # task boxes on the timeline
    face_row = task_row + 3
    total_h = face_row + 2

    canvas = Canvas(total_w + 1, total_h + 1)

    # Title
    if diagram.title:
        canvas.put_text(title_row, 2, diagram.title, style="label")

    # Actor legend with distinct symbols
    _actor_symbols = ["●", "◆", "■", "▲", "★", "◉", "◈", "▶"] if not use_ascii else ["*", "+", "#", "^", "@", "o", "x", ">"]

    # Actor legend
    for ai, actor in enumerate(actors_list):
        row = actor_row + ai
        style = f"sectionfg:{ai}"
        sym = _actor_symbols[ai % len(_actor_symbols)]
        canvas.put(row, 2, sym, merge=False, style=style)
        canvas.put_text(row, 4, actor, style=style)

    # Section spans (above task boxes)
    for si, (sx, ex, title) in enumerate(section_spans):
        style = f"section:{si}"
        # Draw section bar
        canvas.put(section_row, sx, tl, merge=False, style=style)
        for c in range(sx + 1, ex):
            canvas.put(section_row, c, hz, merge=False, style=style)
        canvas.put(section_row, ex, tr, merge=False, style=style)
        # Center title in the bar, clearing the border chars underneath
        title_x = sx + (ex - sx - display_width(title)) // 2
        title_x = max(sx + 1, title_x)
        # Clear space for title (overwrite ─ with spaces)
        for c in range(title_x - 1, title_x + display_width(title) + 1):
            if sx < c < ex:
                canvas._grid[section_row][c] = " "
        canvas.put_text(section_row, title_x, title, style=style)

    # Timeline arrow
    for c in range(1, total_w - 1):
        canvas.put(timeline_row + 1, c, hz, merge=False, style="edge")
    canvas.put(timeline_row + 1, total_w - 1, arrow, merge=False, style="edge")

    # Task boxes on the timeline
    for x, w, td, si in task_positions:
        style = f"section:{si}"
        # Box
        canvas.put(task_row, x, tl, merge=False, style=style)
        for c in range(x + 1, x + w - 1):
            canvas.put(task_row, c, hz, merge=False, style=style)
        canvas.put(task_row, x + w - 1, tr, merge=False, style=style)

        canvas.put(task_row + 1, x, vt, merge=False, style=style)
        canvas.put(task_row + 1, x + w - 1, vt, merge=False, style=style)

        canvas.put(task_row + 2, x, bl, merge=False, style=style)
        for c in range(x + 1, x + w - 1):
            canvas.put(task_row + 2, c, hz, merge=False, style=style)
        canvas.put(task_row + 2, x + w - 1, br, merge=False, style=style)

        # Task title centered (clear interior first to remove timeline ─)
        title = td["title"]
        for c in range(x + 1, x + w - 1):
            canvas._grid[task_row + 1][c] = " "
        tx = x + (w - display_width(title)) // 2
        canvas.put_text(task_row + 1, tx, title, style=style)

        # Dot on timeline below the task box
        mid_x = x + w // 2

        # Actor symbols inside the task box (top-left corner)
        actor_x = x + 1
        for ai, actor in enumerate(actors_list):
            if actor in td["actors"]:
                sym = _actor_symbols[ai % len(_actor_symbols)]
                canvas.put(task_row, actor_x, sym, merge=False,
                          style=f"sectionfg:{ai}")
                actor_x += 1

        # Face below task
        score = td["score"]
        face = faces.get(score, faces[3])
        face_x = x + (w - display_width(face)) // 2
        canvas.put_text(face_row, face_x, face, style="edge_label")

    return canvas
