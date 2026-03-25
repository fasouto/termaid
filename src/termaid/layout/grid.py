"""Grid-based layout engine for flowchart diagrams.

Coordinate systems
------------------
**Grid coordinates** (col, row): logical positions on a coarse grid.
Each node occupies a 3x3 block centered at (col, row). The 8 surrounding
cells are border/attachment cells used for edge routing.

**Draw coordinates** (x, y): character positions in the final output.
Column widths and row heights vary (content, padding, gap, subgraph
borders), so a single grid cell may span many characters.

Layout model
------------
Nodes are separated by ``STRIDE`` grid units (default 4 = 3 block + 1 gap).
Gap cells between node blocks provide routing space for edges.

The ``compute_layout`` function orchestrates the full pipeline:
layer assignment, ordering, placement, sizing, and coordinate conversion.

Submodules
----------
- ``layers``      -- layer assignment, ordering, crossing analysis
- ``placement``   -- node placement and cell sizing
- ``subgraphs``   -- subgraph border expansion and bounding boxes
- ``coordinates`` -- grid-to-draw conversion, negative-bounds adjustment
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..graph.model import Direction, Graph, Subgraph


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STRIDE = 4  # Grid distance between node centers

# Node sizing constants
MAX_LABEL_WIDTH = 20       # Characters before wrapping
MAX_NORMALIZED_WIDTH = 25  # Cap for per-layer column normalization
MAX_NORMALIZED_HEIGHT = 7  # Cap for per-layer row normalization

# Subgraph layout constants
SG_BORDER_PAD = 2    # Padding between content and subgraph border
SG_LABEL_HEIGHT = 2  # Space for subgraph label + border line
SG_GAP_PER_LEVEL = SG_BORDER_PAD + SG_LABEL_HEIGHT + 1  # Gap per nesting level


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class GridCoord:
    col: int
    row: int

    def __hash__(self) -> int:
        return hash((self.col, self.row))

    def __eq__(self, other: object) -> bool:
        if isinstance(other, GridCoord):
            return self.col == other.col and self.row == other.row
        return NotImplemented


@dataclass
class NodePlacement:
    node_id: str
    grid: GridCoord
    # Drawing coordinates (characters), set after column/row sizing
    draw_x: int = 0
    draw_y: int = 0
    draw_width: int = 0
    draw_height: int = 0


@dataclass
class SubgraphBounds:
    subgraph: Subgraph
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0


@dataclass
class GridLayout:
    """Result of the layout process."""
    placements: dict[str, NodePlacement] = field(default_factory=dict)
    col_widths: dict[int, int] = field(default_factory=dict)
    row_heights: dict[int, int] = field(default_factory=dict)
    grid_occupied: dict[tuple[int, int], str] = field(default_factory=dict)
    canvas_width: int = 0
    canvas_height: int = 0
    subgraph_bounds: list[SubgraphBounds] = field(default_factory=list)
    offset_x: int = 0
    offset_y: int = 0

    def is_free(self, col: int, row: int, exclude: set[str] | None = None) -> bool:
        """Check if a grid cell is not occupied by any node's 3x3 block."""
        if col < 0 or row < 0:
            return False
        key = (col, row)
        if key not in self.grid_occupied:
            return True
        if exclude and self.grid_occupied[key] in exclude:
            return True
        return False

    def grid_to_draw(self, col: int, row: int) -> tuple[int, int]:
        """Convert grid coordinates to drawing (character) coordinates.
        Returns the top-left position of the cell."""
        x = sum(self.col_widths.get(c, 1) for c in range(col)) + self.offset_x
        y = sum(self.row_heights.get(r, 1) for r in range(row)) + self.offset_y
        return x, y

    def grid_to_draw_center(self, col: int, row: int) -> tuple[int, int]:
        """Convert grid coordinates to the center of the cell in drawing coords."""
        x = sum(self.col_widths.get(c, 1) for c in range(col)) + self.offset_x
        y = sum(self.row_heights.get(r, 1) for r in range(row)) + self.offset_y
        w = self.col_widths.get(col, 1)
        h = self.row_heights.get(row, 1)
        return x + w // 2, y + h // 2


# ---------------------------------------------------------------------------
# Layout orchestrator
# ---------------------------------------------------------------------------

def compute_layout(graph: Graph, padding_x: int = 4, padding_y: int = 2, gap: int = 4) -> GridLayout:
    gap = max(gap, 1)  # minimum 1 for arrow visibility
    """Compute the grid layout for a graph."""
    # Lazy imports to avoid circular references at module load time
    from .layers import assign_layers, separate_subgraph_layers, order_layers, compute_gap_expansions
    from .placement import place_nodes, compute_sizes, normalize_sizes
    from .subgraphs import expand_gaps_for_subgraphs, compute_subgraph_bounds
    from .coordinates import compute_draw_coords, adjust_for_negative_bounds

    layout = GridLayout()
    direction = graph.direction.normalized()

    if not graph.node_order:
        return layout

    # Step 1: Assign layers via BFS from roots
    layers = assign_layers(graph)

    # Step 1b: Fix overlapping subgraph layer ranges
    layers = separate_subgraph_layers(graph, layers)

    # Step 2: Order nodes within layers (barycenter heuristic)
    layer_order = order_layers(graph, layers)

    # Step 2b: Compute extra gap cells for crossing edges
    gap_expansions = compute_gap_expansions(graph, layer_order)

    # Step 3: Place nodes on the grid (with expanded gaps for crossings)
    place_nodes(graph, layout, layer_order, direction, gap_expansions)

    # Step 4: Compute column widths and row heights (with word wrapping)
    compute_sizes(graph, layout, padding_x, padding_y, gap)

    # Step 4b: Normalize sizes (per-layer, capped)
    normalize_sizes(graph, layout)

    # Step 5: Expand gaps for subgraph borders and labels
    expand_gaps_for_subgraphs(graph, layout, direction)

    # Step 6: Compute drawing coordinates
    compute_draw_coords(layout)

    # Step 7: Compute subgraph bounds
    compute_subgraph_bounds(graph, layout)

    # Step 8: Adjust for negative subgraph bounds
    adjust_for_negative_bounds(layout)

    # Step 9: Compute canvas size
    max_x = 0
    max_y = 0
    for p in layout.placements.values():
        max_x = max(max_x, p.draw_x + p.draw_width)
        max_y = max(max_y, p.draw_y + p.draw_height)
    for sb in layout.subgraph_bounds:
        max_x = max(max_x, sb.x + sb.width)
        max_y = max(max_y, sb.y + sb.height)
    layout.canvas_width = max_x
    layout.canvas_height = max_y

    return layout
