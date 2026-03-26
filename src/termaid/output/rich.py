"""Rich renderable output adapter (optional dependency)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..graph.model import Graph
from ..renderer.canvas import Canvas
from ..renderer.draw import render_graph_canvas
from ..renderer.themes import get_theme

if TYPE_CHECKING:
    from rich.text import Text


def _hex_to_rich_color(hex_color: str) -> str | None:
    """Convert a hex color (#fff or #ffffff) to a Rich color string."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) == 6:
        return f"#{h}"
    return None


def _css_to_rich_style(props: dict[str, str]) -> str | None:
    """Convert CSS-like properties to a Rich style string."""
    parts: list[str] = []

    # fill/background-color → on color
    fill = props.get("fill") or props.get("background-color") or props.get("background")
    if fill:
        color = _hex_to_rich_color(fill)
        if color:
            parts.append(f"on {color}")

    # stroke/color → foreground color
    stroke = props.get("stroke") or props.get("color")
    if stroke:
        color = _hex_to_rich_color(stroke)
        if color:
            parts.append(color)

    # stroke-width → bold if thick
    sw = props.get("stroke-width")
    if sw and sw.replace("px", "").strip() not in ("0", "1", ""):
        parts.append("bold")

    # stroke-dasharray → dim for dashed
    if props.get("stroke-dasharray"):
        parts.append("dim")

    return " ".join(parts) if parts else None


def render_rich(
    graph: Graph,
    use_ascii: bool = False,
    padding_x: int = 4,
    padding_y: int = 2,
    rounded_edges: bool = True,
    theme: str = "default",
) -> Text:
    """Render a graph as a Rich Text object with colors.

    Requires the 'rich' package to be installed.
    """
    try:
        from rich.text import Text
    except ImportError:
        raise ImportError(
            "The 'rich' package is required for colored output. "
            "Install it with: pip install termaid[rich]"
        )

    canvas = render_graph_canvas(graph, use_ascii=use_ascii, padding_x=padding_x, padding_y=padding_y, rounded_edges=rounded_edges)
    if canvas is None:
        return Text("")

    th = get_theme(theme)

    # Map style keys to Rich style strings
    style_map = {
        "node": th.node,
        "edge": th.edge,
        "arrow": th.arrow,
        "subgraph": th.subgraph,
        "label": th.label,
        "edge_label": th.edge_label,
        "subgraph_label": th.subgraph_label,
        "default": th.default,
        "bold_label": f"bold {th.label}",
        "italic_label": f"italic {th.label}",
    }

    # Add class-based styles
    for class_name, props in graph.class_defs.items():
        rich_style = _css_to_rich_style(props)
        if rich_style:
            style_map[f"class:{class_name}"] = rich_style

    # Add per-node inline styles
    for nid, props in graph.node_styles.items():
        rich_style = _css_to_rich_style(props)
        if rich_style:
            style_map[f"nodestyle:{nid}"] = rich_style

    # Add per-edge link styles
    default_link_props = graph.link_styles.get(-1)
    for idx, props in graph.link_styles.items():
        if idx >= 0:
            rich_style = _css_to_rich_style(props)
            if rich_style:
                style_map[f"linkstyle:{idx}"] = rich_style
    # For edges not explicitly styled but with a default linkStyle
    if default_link_props:
        default_link_style = _css_to_rich_style(default_link_props)
        if default_link_style:
            # Map all edge indices that aren't explicitly styled
            for i in range(len(graph.edges)):
                key = f"linkstyle:{i}"
                if key not in style_map:
                    style_map[key] = default_link_style

    styled_pairs = canvas.to_styled_pairs()

    # Build Rich Text from styled pairs
    lines: list[str] = []
    for row in styled_pairs:
        lines.append("".join(ch for ch, _ in row).rstrip())

    # Remove trailing empty lines
    while lines and not lines[-1]:
        lines.pop()

    plain = "\n".join(lines)
    text = Text(plain)

    # For solid themes, apply background to all cells (including spaces)
    is_solid = th.is_solid

    # Apply styles character by character
    pos = 0
    for row_idx, row in enumerate(styled_pairs):
        if row_idx >= len(lines):
            break
        line = lines[row_idx]
        for col_idx, (ch, style_key) in enumerate(row):
            if col_idx >= len(line):
                break
            if is_solid:
                # Solid themes: apply bg to every cell, fg to non-space cells
                bg = ""
                if style_key in ("node", "label", "bold_label", "italic_label") or style_key.startswith("nodestyle:") or style_key.startswith("class:"):
                    bg = th.bg_node
                elif style_key in ("subgraph", "subgraph_label"):
                    bg = th.bg_subgraph
                else:
                    bg = th.bg_default
                fg = style_map.get(style_key, "") if ch != " " else ""
                style_str = f"{fg} {bg}".strip() if fg else bg
                if style_str:
                    text.stylize(style_str, pos + col_idx, pos + col_idx + 1)
            else:
                # Text themes: only style non-space characters
                if style_key in style_map and style_map[style_key]:
                    if ch != " " or style_key.startswith("section:"):
                        text.stylize(style_map[style_key], pos + col_idx, pos + col_idx + 1)
        pos += len(line) + 1  # +1 for newline

    return text


def render_sequence_rich(
    canvas: Canvas,
    theme: str = "default",
) -> Text:
    """Render a pre-built Canvas (e.g. from a sequence diagram) as Rich Text with colors."""
    try:
        from rich.text import Text
    except ImportError:
        raise ImportError(
            "The 'rich' package is required for colored output. "
            "Install it with: pip install termaid[rich]"
        )

    th = get_theme(theme)

    # Section background colors for kanban columns, timeline sections, quadrant regions.
    # Muted dark tones that work as backgrounds with white text on top.
    _SECTION_BG = [
        "on #1B3A4B", "on #3B1B2B", "on #1B3B2B", "on #3B3B1B",
        "on #2B1B3B", "on #1B3B3B", "on #3B2B1B", "on #1B2B3B",
    ]

    style_map = {
        "node": th.node,
        "edge": th.edge,
        "arrow": th.arrow,
        "label": th.label,
        "edge_label": th.edge_label,
        "default": th.default,
    }

    # Add section styles: white text on colored backgrounds
    for i in range(len(_SECTION_BG)):
        style_map[f"section:{i}"] = f"bold white {_SECTION_BG[i % len(_SECTION_BG)]}"

    styled_pairs = canvas.to_styled_pairs()

    # Build lines, preserving trailing spaces on rows that have section
    # backgrounds (so the colored bg fills the full width).
    lines: list[str] = []
    for row in styled_pairs:
        has_section = any(s.startswith("section:") for _, s in row)
        raw = "".join(ch for ch, _ in row)
        lines.append(raw if has_section else raw.rstrip())

    while lines and not lines[-1]:
        lines.pop()

    plain = "\n".join(lines)
    text = Text(plain)

    is_solid = th.is_solid

    pos = 0
    for row_idx, row in enumerate(styled_pairs):
        if row_idx >= len(lines):
            break
        line = lines[row_idx]
        for col_idx, (ch, style_key) in enumerate(row):
            if col_idx >= len(line):
                break
            if is_solid:
                if style_key.startswith("section:"):
                    style_str = style_map.get(style_key, th.bg_default)
                elif style_key in ("node", "label"):
                    bg = th.bg_node
                    fg = style_map.get(style_key, "") if ch != " " else ""
                    style_str = f"{fg} {bg}".strip() if fg else bg
                else:
                    bg = th.bg_default
                    fg = style_map.get(style_key, "") if ch != " " else ""
                    style_str = f"{fg} {bg}".strip() if fg else bg
                if style_str:
                    text.stylize(style_str, pos + col_idx, pos + col_idx + 1)
            else:
                if style_key in style_map and style_map[style_key]:
                    if ch != " " or style_key.startswith("section:"):
                        text.stylize(style_map[style_key], pos + col_idx, pos + col_idx + 1)
        pos += len(line) + 1

    return text
