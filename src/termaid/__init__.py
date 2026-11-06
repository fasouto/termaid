"""termaid - Render Mermaid diagram syntax as beautiful Unicode art in the terminal."""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, NamedTuple

from .graph.model import Graph
from .parser.flowchart import parse_flowchart
from .parser.statediagram import parse_state_diagram
from .utils import DIRECTIVE

if TYPE_CHECKING:
    from .output.styled import StyledDocument
    from .renderer.canvas import Canvas


__version__ = "0.11.0"

_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_LEADING_DIRECTIVES_RE = re.compile(rf"(?:{DIRECTIVE}|%%[^\n]*|\s+)*")


# C0 and C1 control characters, except tab and newline. In a label they would
# reach the terminal as escape sequences, title changes or cursor moves.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_CARRIAGE_RETURN_RE = re.compile(r"\r\n?")


def _strip_frontmatter(text: str) -> str:
    """Strip YAML frontmatter (---...---) from the beginning of mermaid source."""
    return _FRONTMATTER_RE.sub("", text)


def _prepare_source(source: str) -> str:
    """Normalize line endings, drop control characters, a byte order mark and frontmatter."""
    text = _CONTROL_CHARS_RE.sub("", _CARRIAGE_RETURN_RE.sub("\n", source.lstrip("\ufeff")))
    return _strip_frontmatter(text.strip())


def _skip_directives(text: str) -> str:
    """Drop the %%{...}%% directives and %% comments before the diagram keyword."""
    return text[_LEADING_DIRECTIVES_RE.match(text).end():]


def parse(source: str, *, partial: bool = False) -> Graph:
    """Parse mermaid syntax and return a Graph model.

    Auto-detects diagram type (flowchart or state diagram).

    Args:
        source: Mermaid diagram source text
        partial: The source is the start of a diagram that is still arriving
            (see :func:`render`)

    Returns:
        Parsed Graph model
    """
    if partial:
        from .partial import complete_partial

        source = complete_partial(source)
    text = _skip_directives(_prepare_source(source))
    if text.startswith("stateDiagram"):
        return parse_state_diagram(text)
    return parse_flowchart(text)


class _Rendered(NamedTuple):
    canvas: Canvas | None
    # Set for graph-based diagrams, whose classDef/style/linkStyle colours
    # live on the Graph rather than on the canvas.
    graph: Graph | None = None


def _render_canvas(
    source: str,
    *,
    use_ascii: bool,
    padding_x: int,
    padding_y: int,
    rounded_edges: bool,
    gap: int,
    inline_edge_labels: bool,
    max_label_width: int | None,
    arrow_style: str = "pointer",
    partial: bool = False,
) -> _Rendered:
    """Parse source, pick the renderer for its diagram type, and draw it."""
    # Pass padding_x and gap only when they differ from the flowchart
    # defaults, so each renderer keeps its own defaults otherwise.
    extra: dict[str, int] = {}
    if padding_x != 4:
        extra["padding_x"] = padding_x
    if gap != 4:
        extra["gap"] = gap

    from .renderer.charset import build_charset

    # Every renderer draws with this one character set.
    cs = build_charset(use_ascii, arrow_style)

    if partial:
        from .partial import complete_partial

        source = complete_partial(source)
    prepared = _prepare_source(source)
    text = _skip_directives(prepared)
    if text.startswith("sequenceDiagram"):
        from .parser.sequence import parse_sequence_diagram
        from .renderer.sequence import render_sequence
        return _Rendered(render_sequence(
            parse_sequence_diagram(text), use_ascii=use_ascii, cs=cs,
            max_label_width=max_label_width, **extra,
        ))

    if text.startswith("classDiagram"):
        from .parser.classdiagram import parse_class_diagram
        from .renderer.classdiagram import render_class_diagram
        return _Rendered(render_class_diagram(parse_class_diagram(text), use_ascii=use_ascii, cs=cs, **extra))

    if text.startswith("erDiagram"):
        from .parser.erdiagram import parse_er_diagram
        from .renderer.erdiagram import render_er_diagram
        return _Rendered(render_er_diagram(parse_er_diagram(text), use_ascii=use_ascii, cs=cs, **extra))

    if text.startswith("block"):
        from .parser.blockdiagram import parse_block_diagram
        from .renderer.blockdiagram import render_block_diagram
        return _Rendered(render_block_diagram(parse_block_diagram(text), use_ascii=use_ascii, cs=cs, **extra))

    if text.startswith("gitGraph"):
        from .parser.gitgraph import parse_git_graph
        from .renderer.gitgraph import render_git_graph
        # gitGraph reads mainBranchName from its %%{init}%% directive.
        return _Rendered(render_git_graph(parse_git_graph(prepared), use_ascii=use_ascii, cs=cs))

    if text.startswith("gantt"):
        from .parser.gantt import parse_gantt
        from .renderer.gantt import render_gantt
        return _Rendered(render_gantt(parse_gantt(text), use_ascii=use_ascii))

    if text.startswith("pie"):
        from .parser.piechart import parse_pie_chart
        from .renderer.piechart import render_pie_chart
        return _Rendered(render_pie_chart(parse_pie_chart(text), use_ascii=use_ascii))

    if text.startswith("treemap"):
        from .parser.treemap import parse_treemap
        from .renderer.treemap import render_treemap
        return _Rendered(render_treemap(parse_treemap(text), use_ascii=use_ascii, cs=cs))

    if text.startswith("mindmap"):
        from .parser.mindmap import parse_mindmap
        from .renderer.mindmap import render_mindmap
        return _Rendered(render_mindmap(parse_mindmap(text), use_ascii=use_ascii, rounded=rounded_edges))

    if text.startswith("packet"):
        from .parser.packet import parse_packet
        from .renderer.packet import render_packet
        packet_extra = {"padding_y": padding_y} if padding_y != 2 else {}
        return _Rendered(render_packet(parse_packet(text), use_ascii=use_ascii, rounded=rounded_edges, **packet_extra))

    if text.startswith("xychart"):
        from .parser.xychart import parse_xychart
        from .renderer.xychart import render_xychart
        return _Rendered(render_xychart(parse_xychart(text), use_ascii=use_ascii, rounded=rounded_edges))

    if text.startswith("journey"):
        from .parser.journey import parse_journey
        from .renderer.journey import render_journey
        return _Rendered(render_journey(parse_journey(text), use_ascii=use_ascii, cs=cs, rounded=rounded_edges, **extra))

    if text.startswith("timeline"):
        from .parser.timeline import parse_timeline
        from .renderer.timeline import render_timeline
        return _Rendered(render_timeline(parse_timeline(text), use_ascii=use_ascii, cs=cs))

    if text.startswith("kanban"):
        from .parser.kanban import parse_kanban
        from .renderer.kanban import render_kanban
        return _Rendered(render_kanban(parse_kanban(text), use_ascii=use_ascii, cs=cs, **extra))

    if text.startswith("quadrantChart"):
        from .parser.quadrant import parse_quadrant
        from .renderer.quadrant import render_quadrant
        return _Rendered(render_quadrant(parse_quadrant(text), use_ascii=use_ascii))

    from .renderer import draw
    if text.startswith("architecture"):
        from .parser.architecture import parse_architecture
        graph = parse_architecture(text)
        inline_edge_labels = False
    else:
        graph = parse(text)
    canvas = draw.render_graph_canvas(
        graph,
        cs=cs,
        use_ascii=use_ascii,
        padding_x=padding_x,
        padding_y=padding_y,
        rounded_edges=rounded_edges,
        gap=gap,
        inline_edge_labels=inline_edge_labels,
        max_label_width=max_label_width,
    )
    return _Rendered(canvas, graph)


def render(
    source: str,
    *,
    use_ascii: bool = False,
    padding_x: int = 4,
    padding_y: int = 2,
    rounded_edges: bool = True,
    gap: int = 4,
    inline_edge_labels: bool = False,
    max_label_width: int | None = None,
    arrow_style: str = "pointer",
    partial: bool = False,
) -> str:
    """Render mermaid syntax as Unicode (or ASCII) art.

    Args:
        source: Mermaid diagram source text
        use_ascii: Use ASCII characters instead of Unicode box-drawing
        padding_x: Horizontal padding inside node boxes
        padding_y: Vertical padding inside node boxes
        gap: Space between nodes (default: 4)
        inline_edge_labels: Attach flowchart labels directly to their edges
        max_label_width: Wrap labels wider than this many columns at word
            boundaries. Applies to flowcharts (default 20) and sequence
            diagrams (unwrapped by default); other diagram types ignore it.
        arrow_style: Arrowheads for Unicode output: ``"pointer"`` (default,
            ``► ◄ ▼ ▲``), ``"triangle"`` (``▶ ◀ ▼ ▲``) or ``"outline"``
            (``▷ ◁ ▽ △``). Class diagrams keep solid dependency arrows with
            ``"outline"``, since open triangles mean inheritance there. ASCII
            output ignores it. Raises ``ValueError`` for an unknown style.
        partial: The source is the start of a diagram that is still arriving,
            such as a streamed reply. Its last line, unless it ends with a
            newline, may be unfinished: open brackets and quotes are closed so
            a label shows the text so far, and an edge or message whose target
            hasn't arrived is left out until it has.

    Returns:
        Rendered diagram as a string

    Example:
        >>> from termaid import render
        >>> print(render("graph LR\\n  A --> B --> C"))
    """
    canvas = _render_canvas(
        source,
        use_ascii=use_ascii,
        padding_x=padding_x,
        padding_y=padding_y,
        rounded_edges=rounded_edges,
        gap=gap,
        inline_edge_labels=inline_edge_labels,
        max_label_width=max_label_width,
        arrow_style=arrow_style,
        partial=partial,
    ).canvas
    return canvas.to_string() if canvas is not None else ""


def render_rich(
    source: str,
    *,
    use_ascii: bool = False,
    padding_x: int = 4,
    padding_y: int = 2,
    rounded_edges: bool = True,
    theme: str = "default",
    gap: int = 4,
    inline_edge_labels: bool = False,
    max_label_width: int | None = None,
    arrow_style: str = "pointer",
    partial: bool = False,
):
    """Render mermaid syntax as a Rich Text object with colors.

    Requires: pip install termaid[rich]

    Args:
        source: Mermaid diagram source text
        use_ascii: Use ASCII characters instead of Unicode
        padding_x: Horizontal padding inside node boxes
        padding_y: Vertical padding inside node boxes
        theme: Color theme name (default, terra, neon, mono, amber, phosphor)
        gap: Space between nodes (default: 4)
        inline_edge_labels: Attach flowchart labels directly to their edges
        max_label_width: Wrap labels wider than this many columns at word
            boundaries. Applies to flowcharts (default 20) and sequence
            diagrams (unwrapped by default); other diagram types ignore it.
        arrow_style: Arrowheads for Unicode output: ``"pointer"`` (default,
            ``► ◄ ▼ ▲``), ``"triangle"`` (``▶ ◀ ▼ ▲``) or ``"outline"``
            (``▷ ◁ ▽ △``). Class diagrams keep solid dependency arrows with
            ``"outline"``, since open triangles mean inheritance there. ASCII
            output ignores it. Raises ``ValueError`` for an unknown style.
        partial: The source is the start of a diagram that is still arriving,
            such as a streamed reply. Its last line, unless it ends with a
            newline, may be unfinished: open brackets and quotes are closed so
            a label shows the text so far, and an edge or message whose target
            hasn't arrived is left out until it has.

    Returns:
        rich.text.Text object
    """
    from .output.rich import render_graph_rich, render_sequence_rich

    rendered = _render_canvas(
        source,
        use_ascii=use_ascii,
        padding_x=padding_x,
        padding_y=padding_y,
        rounded_edges=rounded_edges,
        gap=gap,
        inline_edge_labels=inline_edge_labels,
        max_label_width=max_label_width,
        arrow_style=arrow_style,
        partial=partial,
    )
    if rendered.graph is not None:
        return render_graph_rich(rendered.canvas, rendered.graph, theme=theme)
    return render_sequence_rich(rendered.canvas, theme=theme)


def render_styled(
    source: str,
    *,
    use_ascii: bool = False,
    padding_x: int = 4,
    padding_y: int = 2,
    rounded_edges: bool = True,
    gap: int = 4,
    inline_edge_labels: bool = False,
    max_label_width: int | None = None,
    arrow_style: str = "pointer",
    partial: bool = False,
) -> StyledDocument:
    """Render mermaid syntax as theme-independent styled chunks.

    Each line of the result is a list of ``{"text", "style"}`` chunks whose
    joined text equals the matching line of :func:`render`. The style keys
    are listed in :mod:`termaid.output.styled`.

    ``arrow_style`` works as in :func:`render`.
    ``partial`` works as in :func:`render`.

    Returns:
        ``{"version": 1, "lines": [[{"text": ..., "style": ...}, ...], ...]}``
    """
    from .output.styled import serialize_canvas

    return serialize_canvas(_render_canvas(
        source,
        use_ascii=use_ascii,
        padding_x=padding_x,
        padding_y=padding_y,
        rounded_edges=rounded_edges,
        gap=gap,
        inline_edge_labels=inline_edge_labels,
        max_label_width=max_label_width,
        arrow_style=arrow_style,
        partial=partial,
    ).canvas)


# Lazy import for MermaidWidget
def __getattr__(name: str):
    if name == "MermaidWidget":
        from .output.widget import _get_widget_class
        return _get_widget_class()
    raise AttributeError(f"module 'termaid' has no attribute {name!r}")
