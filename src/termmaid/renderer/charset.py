"""Character sets for Unicode and ASCII rendering."""
from __future__ import annotations

from dataclasses import dataclass


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
    # Endpoints
    circle_endpoint="o", cross_endpoint="x",
    # Subgraph
    sg_top_left="+", sg_top_right="+",
    sg_bottom_left="+", sg_bottom_right="+",
    sg_horizontal="-", sg_vertical="|",
)
