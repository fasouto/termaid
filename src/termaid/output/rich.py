"""Rich renderable output adapter (optional dependency)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterator

from ..graph.model import Graph
from ..renderer.canvas import Canvas
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


def _css_to_rich_text_style(props: dict[str, str]) -> str | None:
    """Rich style for a node's label text: Mermaid's `color` property."""
    color = props.get("color")
    return _hex_to_rich_color(color) if color else None


def _cell_spans(row: list[tuple[str, str]], line_length: int) -> Iterator[tuple[int, int, str, str]]:
    """Yield ``(start, end, cell, style_key)`` string offsets for a canvas row.

    A cell holds a letter with its marks (several code points) or a wide
    character's shadow (none), so offsets follow the cell text, not the
    column. Stops at *line_length*, the row's length after rstrip.
    """
    start = 0
    for cell, style_key in row:
        if start >= line_length:
            return
        end = start + len(cell)
        if cell:
            yield start, end, cell, style_key
        start = end


def render_graph_rich(
    canvas: Canvas | None,
    graph: Graph,
    theme: str = "default",
) -> Text:
    """Colour a rendered graph canvas, applying the graph's own classDef,
    style and linkStyle colours on top of the theme.

    Requires the 'rich' package to be installed.
    """
    try:
        from rich.text import Text
    except ImportError:
        raise ImportError(
            "The 'rich' package is required for colored output. "
            "Install it with: pip install termaid[rich]"
        )

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

    # Add class-based styles. Label text uses `color` when set, otherwise
    # the theme's label style.
    for class_name, props in graph.class_defs.items():
        rich_style = _css_to_rich_style(props)
        if rich_style:
            style_map[f"class:{class_name}"] = rich_style
        style_map[f"class:{class_name}:text"] = _css_to_rich_text_style(props) or th.label

    # Add per-node inline styles
    for nid, props in graph.node_styles.items():
        rich_style = _css_to_rich_style(props)
        if rich_style:
            style_map[f"nodestyle:{nid}"] = rich_style
        style_map[f"nodestyle:{nid}:text"] = _css_to_rich_text_style(props) or th.label

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
        for start, end, ch, style_key in _cell_spans(row, len(line)):
            if is_solid:
                # Solid themes: apply bg to every cell, fg to non-space cells.
                # sectionfg: styles are foreground-only (no bg fill).
                if style_key.startswith("sectionfg:"):
                    fg = style_map.get(style_key, "") if ch != " " else ""
                    style_str = fg
                else:
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
                    text.stylize(style_str, pos + start, pos + end)
            else:
                # Text themes: only style non-space characters
                if style_key in style_map and style_map[style_key]:
                    if ch != " " or style_key.startswith("section:"):
                        if style_key in style_map:
                            text.stylize(style_map[style_key], pos + start, pos + end)
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

    # Section background colors from the theme's palette
    _section_colors = th.section_colors

    style_map = {
        "node": th.node,
        "edge": th.edge,
        "arrow": th.arrow,
        "label": th.label,
        "edge_label": th.edge_label,
        "default": th.default,
    }

    # Add section styles: white text on colored backgrounds.
    # "section:N" is the base (column bg), "section:N:deep" is lighter (card bg).
    for i in range(len(_section_colors)):
        base_hex = _section_colors[i % len(_section_colors)]
        style_map[f"section:{i}"] = f"bold white on {base_hex}"
        # Lighten by adding 30 to each RGB component for cards
        r, g, b = int(base_hex[1:3], 16), int(base_hex[3:5], 16), int(base_hex[5:7], 16)
        lr, lg, lb = min(255, r + 30), min(255, g + 30), min(255, b + 30)
        light_hex = f"#{lr:02X}{lg:02X}{lb:02X}"
        style_map[f"section:{i}:deep"] = f"bold white on {light_hex}"
        # Foreground-only variant (for timeline): bright version of the base color
        fr, fg_, fb = min(255, r * 3), min(255, g * 3), min(255, b * 3)
        style_map[f"sectionfg:{i}"] = f"bold #{fr:02X}{fg_:02X}{fb:02X}"

    styled_pairs = canvas.to_styled_pairs()

    # Build lines, preserving trailing spaces on rows that have section
    # backgrounds (so the colored bg fills the full width).
    lines: list[str] = []
    for row in styled_pairs:
        has_section = any(s.startswith("section:") for _, s in row if s != "default")
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
        for start, end, ch, style_key in _cell_spans(row, len(line)):
            if is_solid:
                if style_key.startswith("sectionfg:"):
                    # Foreground-only section (timeline)
                    fg = style_map.get(style_key, "") if ch != " " else ""
                    style_str = fg
                elif style_key.startswith("section:"):
                    # Background-filled section (kanban, quadrant)
                    style_str = style_map.get(style_key, style_map.get(style_key.split(":deep")[0], th.bg_default))
                elif style_key in ("node", "label"):
                    bg = th.bg_node
                    fg = style_map.get(style_key, "") if ch != " " else ""
                    style_str = f"{fg} {bg}".strip() if fg else bg
                else:
                    # Only apply bg to non-space chars; leave spaces transparent
                    fg = style_map.get(style_key, "") if ch != " " else ""
                    style_str = fg
                if style_str:
                    text.stylize(style_str, pos + start, pos + end)
            else:
                if style_key in style_map and style_map[style_key]:
                    if ch != " " or style_key.startswith("section:"):
                        text.stylize(style_map[style_key], pos + start, pos + end)
        pos += len(line) + 1

    return text
