"""Character sets for Unicode and ASCII rendering."""
from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class CharSet:
    """A set of characters for rendering diagrams."""
    # Box drawing
    top_left: str
    top_right: str
    bottom_left: str
    bottom_right: str
    horizontal: str
    vertical: str

    # Rounded corners
    round_top_left: str
    round_top_right: str
    round_bottom_left: str
    round_bottom_right: str

    # Arrows
    arrow_right: str
    arrow_left: str
    arrow_down: str
    arrow_up: str

    # Class-diagram inheritance markers (open triangles)
    inherit_right: str
    inherit_left: str
    inherit_down: str
    inherit_up: str

    # Class-diagram dependency arrows: the arrowheads, unless those would look
    # like the inheritance markers (see build_charset)
    dependency_right: str
    dependency_left: str
    dependency_down: str
    dependency_up: str

    # Edge line styles
    line_horizontal: str
    line_vertical: str
    line_dotted_h: str
    line_dotted_v: str
    line_thick_h: str
    line_thick_v: str

    # Corners for edge routing
    corner_top_left: str
    corner_top_right: str
    corner_bottom_left: str
    corner_bottom_right: str

    # T-junctions (where edges meet node borders)
    tee_right: str
    tee_left: str
    tee_down: str
    tee_up: str

    # Cross junction
    cross: str

    # Diamond shape
    diamond_top: str
    diamond_bottom: str
    diamond_left: str
    diamond_right: str

    # Front rim of a cylinder's lid, drawn inside its sides
    lid_left: str
    lid_fill: str
    lid_right: str

    # Sides of a stadium too short to draw as a capsule
    stadium_left: str
    stadium_right: str

    # Endpoint types
    circle_endpoint: str
    cross_endpoint: str

    # Subgraph corners (double-line or dashed)
    sg_top_left: str
    sg_top_right: str
    sg_bottom_left: str
    sg_bottom_right: str
    sg_horizontal: str
    sg_vertical: str


UNICODE = CharSet(
    # Box
    top_left="┌", top_right="┐", bottom_left="└", bottom_right="┘",
    horizontal="─", vertical="│",
    # Rounded
    round_top_left="╭", round_top_right="╮",
    round_bottom_left="╰", round_bottom_right="╯",
    # Arrows
    arrow_right="►", arrow_left="◄", arrow_down="▼", arrow_up="▲",
    inherit_right="▷", inherit_left="◁", inherit_down="▽", inherit_up="△",
    dependency_right="►", dependency_left="◄", dependency_down="▼", dependency_up="▲",
    # Edge lines
    line_horizontal="─", line_vertical="│",
    line_dotted_h="┄", line_dotted_v="┆",
    line_thick_h="━", line_thick_v="┃",
    # Edge corners
    corner_top_left="┌", corner_top_right="┐",
    corner_bottom_left="└", corner_bottom_right="┘",
    # T-junctions
    tee_right="├", tee_left="┤", tee_down="┬", tee_up="┴",
    # Cross
    cross="┼",
    # Diamond
    diamond_top="◇", diamond_bottom="◇", diamond_left="◇", diamond_right="◇",
    lid_left="╰", lid_fill="─", lid_right="╯",
    stadium_left="❨", stadium_right="❩",
    # Endpoints
    circle_endpoint="○", cross_endpoint="×",
    # Subgraph
    sg_top_left="┌", sg_top_right="┐",
    sg_bottom_left="└", sg_bottom_right="┘",
    sg_horizontal="─", sg_vertical="│",
)

ASCII = CharSet(
    # Box
    top_left="+", top_right="+", bottom_left="+", bottom_right="+",
    horizontal="-", vertical="|",
    # Rounded
    round_top_left="+", round_top_right="+",
    round_bottom_left="+", round_bottom_right="+",
    # Arrows
    arrow_right=">", arrow_left="<", arrow_down="v", arrow_up="^",
    inherit_right=">", inherit_left="<", inherit_down="v", inherit_up="^",
    dependency_right=">", dependency_left="<", dependency_down="v", dependency_up="^",
    # Edge lines
    line_horizontal="-", line_vertical="|",
    line_dotted_h=".", line_dotted_v=":",
    line_thick_h="=", line_thick_v="H",
    # Edge corners
    corner_top_left="+", corner_top_right="+",
    corner_bottom_left="+", corner_bottom_right="+",
    # T-junctions
    tee_right="+", tee_left="+", tee_down="+", tee_up="+",
    # Cross
    cross="+",
    # Diamond
    diamond_top="/", diamond_bottom="\\", diamond_left="/", diamond_right="\\",
    lid_left="\\", lid_fill="_", lid_right="/",
    stadium_left="(", stadium_right=")",
    # Endpoints
    circle_endpoint="o", cross_endpoint="x",
    # Subgraph
    sg_top_left="+", sg_top_right="+",
    sg_bottom_left="+", sg_bottom_right="+",
    sg_horizontal="-", sg_vertical="|",
)


ARROW_STYLES: dict[str, tuple[str, str, str, str]] = {
    # name: (right, left, down, up)
    "pointer": ("►", "◄", "▼", "▲"),   # the default
    "triangle": ("▶", "◀", "▼", "▲"),  # solid triangles, matching ▼ ▲
    "outline": ("▷", "◁", "▽", "△"),   # open triangles
}
"""Unicode arrowhead styles, for ``arrow_style=``. ASCII always uses ``> < v ^``."""


def default_charset(use_ascii: bool) -> CharSet:
    """The built-in character set: ASCII, or Unicode box drawing."""
    return ASCII if use_ascii else UNICODE


def build_charset(use_ascii: bool = False, arrow_style: str = "pointer") -> CharSet:
    """The character set for a render: ASCII, or Unicode with an arrowhead style.

    Raises:
        ValueError: ``arrow_style`` isn't one of ``ARROW_STYLES``.
    """
    if arrow_style not in ARROW_STYLES:
        raise ValueError(
            f"unknown arrow style {arrow_style!r}; expected one of {', '.join(ARROW_STYLES)}"
        )
    if use_ascii or arrow_style == "pointer":
        return default_charset(use_ascii)
    right, left, down, up = ARROW_STYLES[arrow_style]
    arrows = (right, left, down, up)
    inheritance = (UNICODE.inherit_right, UNICODE.inherit_left, UNICODE.inherit_down, UNICODE.inherit_up)
    # A class-diagram dependency must never look like inheritance.
    dependency = ARROW_STYLES["triangle"] if arrows == inheritance else arrows
    return replace(
        UNICODE,
        arrow_right=right, arrow_left=left, arrow_down=down, arrow_up=up,
        dependency_right=dependency[0], dependency_left=dependency[1],
        dependency_down=dependency[2], dependency_up=dependency[3],
    )
