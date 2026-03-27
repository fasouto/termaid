"""termaid - Render Mermaid diagram syntax as beautiful Unicode art in the terminal."""
from __future__ import annotations

import re

from .graph.model import Graph
from .parser.flowchart import parse_flowchart
from .parser.statediagram import parse_state_diagram


__version__ = "0.1.0"

_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


def _strip_frontmatter(text: str) -> str:
    """Strip YAML frontmatter (---...---) from the beginning of mermaid source."""
    return _FRONTMATTER_RE.sub("", text)


def parse(source: str) -> Graph:
    """Parse mermaid syntax and return a Graph model.

    Auto-detects diagram type (flowchart or state diagram).

    Args:
        source: Mermaid diagram source text

    Returns:
        Parsed Graph model
    """
    text = _strip_frontmatter(source.strip())
    if text.startswith("stateDiagram"):
        return parse_state_diagram(text)
    return parse_flowchart(text)


def render(
    source: str,
    *,
    use_ascii: bool = False,
    padding_x: int = 4,
    padding_y: int = 2,
    rounded_edges: bool = True,
    gap: int = 4,
) -> str:
    """Render mermaid syntax as Unicode (or ASCII) art.

    Args:
        source: Mermaid diagram source text
        use_ascii: Use ASCII characters instead of Unicode box-drawing
        padding_x: Horizontal padding inside node boxes
        padding_y: Vertical padding inside node boxes
        gap: Space between nodes (default: 4)

    Returns:
        Rendered diagram as a string

    Example:
        >>> from termaid import render
        >>> print(render("graph LR\\n  A --> B --> C"))
    """
    # Build extra kwargs only when values differ from flowchart defaults,
    # so each renderer keeps its own defaults when the user doesn't
    # explicitly override.
    _extra: dict[str, int] = {}
    if padding_x != 4:
        _extra["padding_x"] = padding_x
    if gap != 4:
        _extra["gap"] = gap

    try:
        text = _strip_frontmatter(source.strip())
        if text.startswith("sequenceDiagram"):
            from .parser.sequence import parse_sequence_diagram
            from .renderer.sequence import render_sequence
            diagram = parse_sequence_diagram(text)
            return render_sequence(diagram, use_ascii=use_ascii, **_extra).to_string()

        if text.startswith("classDiagram"):
            from .parser.classdiagram import parse_class_diagram
            from .renderer.classdiagram import render_class_diagram
            diagram = parse_class_diagram(text)
            return render_class_diagram(diagram, use_ascii=use_ascii, **_extra).to_string()

        if text.startswith("erDiagram"):
            from .parser.erdiagram import parse_er_diagram
            from .renderer.erdiagram import render_er_diagram
            diagram = parse_er_diagram(text)
            return render_er_diagram(diagram, use_ascii=use_ascii, **_extra).to_string()

        if text.startswith("block"):
            from .parser.blockdiagram import parse_block_diagram
            from .renderer.blockdiagram import render_block_diagram
            diagram = parse_block_diagram(text)
            return render_block_diagram(diagram, use_ascii=use_ascii, **_extra).to_string()

        if text.startswith("gitGraph") or (text.startswith("%%{init") and "gitGraph" in text):
            from .parser.gitgraph import parse_git_graph
            from .renderer.gitgraph import render_git_graph
            diagram = parse_git_graph(text)
            return render_git_graph(diagram, use_ascii=use_ascii).to_string()

        if text.startswith("pie"):
            from .parser.piechart import parse_pie_chart
            from .renderer.piechart import render_pie_chart
            diagram = parse_pie_chart(text)
            return render_pie_chart(diagram, use_ascii=use_ascii).to_string()

        if text.startswith("treemap"):
            from .parser.treemap import parse_treemap
            from .renderer.treemap import render_treemap
            diagram = parse_treemap(text)
            return render_treemap(diagram, use_ascii=use_ascii).to_string()

        if text.startswith("mindmap"):
            from .parser.mindmap import parse_mindmap
            from .renderer.mindmap import render_mindmap
            diagram = parse_mindmap(text)
            return render_mindmap(diagram, use_ascii=use_ascii, rounded=rounded_edges).to_string()

        if text.startswith("xychart"):
            from .parser.xychart import parse_xychart
            from .renderer.xychart import render_xychart
            diagram = parse_xychart(text)
            return render_xychart(diagram, use_ascii=use_ascii, rounded=rounded_edges).to_string()

        if text.startswith("timeline"):
            from .parser.timeline import parse_timeline
            from .renderer.timeline import render_timeline
            diagram = parse_timeline(text)
            return render_timeline(diagram, use_ascii=use_ascii).to_string()

        if text.startswith("kanban"):
            from .parser.kanban import parse_kanban
            from .renderer.kanban import render_kanban
            diagram = parse_kanban(text)
            return render_kanban(diagram, use_ascii=use_ascii, **_extra).to_string()

        if text.startswith("quadrantChart"):
            from .parser.quadrant import parse_quadrant
            from .renderer.quadrant import render_quadrant
            diagram = parse_quadrant(text)
            return render_quadrant(diagram, use_ascii=use_ascii).to_string()

        graph = parse(text)
        from .output.text import render_text
        return render_text(graph, use_ascii=use_ascii, padding_x=padding_x, padding_y=padding_y, rounded_edges=rounded_edges, gap=gap)
    except Exception as exc:
        return f"[termaid] Failed to render diagram: {exc}"


def render_rich(
    source: str,
    *,
    use_ascii: bool = False,
    padding_x: int = 4,
    padding_y: int = 2,
    rounded_edges: bool = True,
    theme: str = "default",
):
    """Render mermaid syntax as a Rich Text object with colors.

    Requires: pip install termaid[rich]

    Args:
        source: Mermaid diagram source text
        use_ascii: Use ASCII characters instead of Unicode
        padding_x: Horizontal padding inside node boxes
        padding_y: Vertical padding inside node boxes
        theme: Color theme name (default, terra, neon, mono, amber, phosphor)

    Returns:
        rich.text.Text object
    """
    _extra_r: dict[str, int] = {}
    if padding_x != 4:
        _extra_r["padding_x"] = padding_x

    try:
        text = _strip_frontmatter(source.strip())
        if text.startswith("sequenceDiagram"):
            from .parser.sequence import parse_sequence_diagram
            from .renderer.sequence import render_sequence
            from .output.rich import render_sequence_rich
            diagram = parse_sequence_diagram(text)
            canvas = render_sequence(diagram, use_ascii=use_ascii, **_extra_r)
            return render_sequence_rich(canvas, theme=theme)

        if text.startswith("classDiagram"):
            from .parser.classdiagram import parse_class_diagram
            from .renderer.classdiagram import render_class_diagram
            from .output.rich import render_sequence_rich
            diagram = parse_class_diagram(text)
            canvas = render_class_diagram(diagram, use_ascii=use_ascii, **_extra_r)
            return render_sequence_rich(canvas, theme=theme)

        if text.startswith("erDiagram"):
            from .parser.erdiagram import parse_er_diagram
            from .renderer.erdiagram import render_er_diagram
            from .output.rich import render_sequence_rich
            diagram = parse_er_diagram(text)
            canvas = render_er_diagram(diagram, use_ascii=use_ascii, **_extra_r)
            return render_sequence_rich(canvas, theme=theme)

        if text.startswith("block"):
            from .parser.blockdiagram import parse_block_diagram
            from .renderer.blockdiagram import render_block_diagram
            from .output.rich import render_sequence_rich
            diagram = parse_block_diagram(text)
            canvas = render_block_diagram(diagram, use_ascii=use_ascii, **_extra_r)
            return render_sequence_rich(canvas, theme=theme)

        if text.startswith("gitGraph") or (text.startswith("%%{init") and "gitGraph" in text):
            from .parser.gitgraph import parse_git_graph
            from .renderer.gitgraph import render_git_graph
            from .output.rich import render_sequence_rich
            diagram = parse_git_graph(text)
            canvas = render_git_graph(diagram, use_ascii=use_ascii)
            return render_sequence_rich(canvas, theme=theme)

        if text.startswith("pie"):
            from .parser.piechart import parse_pie_chart
            from .renderer.piechart import render_pie_chart
            from .output.rich import render_sequence_rich
            diagram = parse_pie_chart(text)
            canvas = render_pie_chart(diagram, use_ascii=use_ascii)
            return render_sequence_rich(canvas, theme=theme)

        if text.startswith("treemap"):
            from .parser.treemap import parse_treemap
            from .renderer.treemap import render_treemap
            from .output.rich import render_sequence_rich
            diagram = parse_treemap(text)
            canvas = render_treemap(diagram, use_ascii=use_ascii)
            return render_sequence_rich(canvas, theme=theme)

        if text.startswith("mindmap"):
            from .parser.mindmap import parse_mindmap
            from .renderer.mindmap import render_mindmap
            from .output.rich import render_sequence_rich
            diagram = parse_mindmap(text)
            canvas = render_mindmap(diagram, use_ascii=use_ascii)
            return render_sequence_rich(canvas, theme=theme)

        if text.startswith("xychart"):
            from .parser.xychart import parse_xychart
            from .renderer.xychart import render_xychart
            from .output.rich import render_sequence_rich
            diagram = parse_xychart(text)
            canvas = render_xychart(diagram, use_ascii=use_ascii)
            return render_sequence_rich(canvas, theme=theme)

        if text.startswith("timeline"):
            from .parser.timeline import parse_timeline
            from .renderer.timeline import render_timeline
            from .output.rich import render_sequence_rich
            diagram = parse_timeline(text)
            canvas = render_timeline(diagram, use_ascii=use_ascii)
            return render_sequence_rich(canvas, theme=theme)

        if text.startswith("kanban"):
            from .parser.kanban import parse_kanban
            from .renderer.kanban import render_kanban
            from .output.rich import render_sequence_rich
            diagram = parse_kanban(text)
            canvas = render_kanban(diagram, use_ascii=use_ascii, **_extra_r)
            return render_sequence_rich(canvas, theme=theme)

        if text.startswith("quadrantChart"):
            from .parser.quadrant import parse_quadrant
            from .renderer.quadrant import render_quadrant
            from .output.rich import render_sequence_rich
            diagram = parse_quadrant(text)
            canvas = render_quadrant(diagram, use_ascii=use_ascii)
            return render_sequence_rich(canvas, theme=theme)

        graph = parse(text)
        from .output.rich import render_rich as _render_rich
        return _render_rich(graph, use_ascii=use_ascii, padding_x=padding_x, padding_y=padding_y, rounded_edges=rounded_edges, theme=theme)
    except Exception as exc:
        from rich.text import Text
        return Text(f"[termaid] Failed to render diagram: {exc}")


# Lazy import for MermaidWidget
def __getattr__(name: str):
    if name == "MermaidWidget":
        from .output.widget import _get_widget_class
        return _get_widget_class()
    raise AttributeError(f"module 'termaid' has no attribute {name!r}")
