"""Tests for edge routing (A* pathfinding and direction selection)."""
from __future__ import annotations

import pytest

from termaid.parser.flowchart import parse_flowchart
from termaid.layout.grid import compute_layout
from termaid.routing.router import route_edges, RoutedEdge
from termaid.routing.pathfinder import find_path, simplify_path, heuristic


class TestHeuristic:
    def test_same_point(self):
        assert heuristic(0, 0, 0, 0) == 0.0

    def test_horizontal(self):
        assert heuristic(0, 0, 5, 0) == 5.0

    def test_vertical(self):
        assert heuristic(0, 0, 0, 5) == 5.0

    def test_diagonal_penalty(self):
        # Manhattan distance is 10, but +1 corner penalty
        assert heuristic(0, 0, 5, 5) == 11.0


class TestPathfinder:
    def test_straight_path(self):
        path = find_path(0, 0, 5, 0, lambda c, r: True)
        assert path is not None
        assert path[0] == (0, 0)
        assert path[-1] == (5, 0)

    def test_path_around_obstacle(self):
        # Obstacle at (2, 0)
        def is_free(c, r):
            return not (c == 2 and r == 0)

        path = find_path(0, 0, 4, 0, is_free)
        assert path is not None
        assert (2, 0) not in path
        assert path[0] == (0, 0)
        assert path[-1] == (4, 0)

    def test_no_path(self):
        # Completely walled off
        def is_free(c, r):
            return c == 0 and r == 0

        path = find_path(0, 0, 5, 5, is_free)
        assert path is None

    def test_adjacent_cells(self):
        path = find_path(0, 0, 1, 0, lambda c, r: True)
        assert path == [(0, 0), (1, 0)]


class TestSimplifyPath:
    def test_already_simple(self):
        assert simplify_path([(0, 0), (5, 0)]) == [(0, 0), (5, 0)]

    def test_straight_line(self):
        path = [(0, 0), (1, 0), (2, 0), (3, 0)]
        assert simplify_path(path) == [(0, 0), (3, 0)]

    def test_one_corner(self):
        path = [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2)]
        result = simplify_path(path)
        assert result == [(0, 0), (2, 0), (2, 2)]

    def test_two_corners(self):
        path = [(0, 0), (1, 0), (2, 0), (2, 1), (2, 2), (3, 2), (4, 2)]
        result = simplify_path(path)
        assert result == [(0, 0), (2, 0), (2, 2), (4, 2)]


class TestEdgeRouting:
    def test_simple_lr_routing(self):
        g = parse_flowchart("graph LR\n  A --> B")
        layout = compute_layout(g)
        routed = route_edges(g, layout)
        assert len(routed) == 1
        re = routed[0]
        assert re.edge.source == "A"
        assert re.edge.target == "B"
        assert len(re.draw_path) >= 2

    def test_all_edges_routed(self):
        g = parse_flowchart("graph LR\n  A --> B\n  A --> C\n  B --> D")
        layout = compute_layout(g)
        routed = route_edges(g, layout)
        assert len(routed) == 3

    def test_self_reference_routing(self):
        g = parse_flowchart("graph LR\n  A --> A")
        layout = compute_layout(g)
        routed = route_edges(g, layout)
        assert len(routed) == 1
        re = routed[0]
        assert len(re.draw_path) >= 3  # Self-loop has multiple points

    def test_no_edge_through_node(self):
        """Edges should not route through node interiors."""
        g = parse_flowchart("graph LR\n  A --> B\n  A --> C\n  B --> D\n  C --> D")
        layout = compute_layout(g)
        routed = route_edges(g, layout)

        # Collect all node grid cells
        node_cells: dict[tuple[int, int], str] = {}
        for nid, p in layout.placements.items():
            for dc in range(-1, 2):
                for dr in range(-1, 2):
                    node_cells[(p.grid.col + dc, p.grid.row + dr)] = nid

        for re in routed:
            for col, row in re.grid_path[1:-1]:  # Skip start and end
                if (col, row) in node_cells:
                    owner = node_cells[(col, row)]
                    # This cell belongs to a node, but it should only be the source or target
                    assert owner in (re.edge.source, re.edge.target), (
                        f"Edge {re.edge.source}->{re.edge.target} routes through "
                        f"node {owner} at ({col}, {row})"
                    )

    def test_draw_path_coordinates_valid(self):
        """Draw path coordinates should be non-negative."""
        g = parse_flowchart("graph LR\n  A --> B --> C")
        layout = compute_layout(g)
        routed = route_edges(g, layout)
        for re in routed:
            for x, y in re.draw_path:
                assert x >= 0, f"Negative x in path: {x}"
                assert y >= 0, f"Negative y in path: {y}"

    def test_soft_obstacles_prevent_overlap(self):
        """Edges routed later should prefer paths that don't overlap earlier edges."""
        g = parse_flowchart("graph LR\n  A --> C\n  B --> D\n  A --> D\n  B --> C")
        layout = compute_layout(g)
        routed = route_edges(g, layout)
        # Check that at least some edges have different paths
        paths = [tuple(re.grid_path) for re in routed]
        # Not all paths should be identical
        assert len(set(paths)) > 1


class TestSubgraphEdgeRouting:
    """Edges to/from subgraph IDs attach to the subgraph border (issue #6)."""

    SIMPLE = (
        "flowchart TD\n"
        "subgraph A\n  A1\n  A2\nend\n"
        "subgraph B\n  B1\n  B2\nend\n"
        "A --> B\n"
    )

    def _sg_box(self, layout, sg_id):
        for sb in layout.subgraph_bounds:
            if sb.subgraph.id == sg_id:
                return sb
        raise AssertionError(f"no bounds for subgraph {sg_id}")

    def test_endpoints_on_subgraph_borders(self):
        g = parse_flowchart(self.SIMPLE)
        layout = compute_layout(g)
        routed = route_edges(g, layout)
        assert len(routed) == 1
        path = routed[0].draw_path
        assert len(path) >= 2

        box_a = self._sg_box(layout, "A")
        box_b = self._sg_box(layout, "B")

        # Start point sits on A's border rectangle
        sx, sy = path[0]
        assert sy == box_a.y + box_a.height - 1
        assert box_a.x <= sx <= box_a.x + box_a.width - 1

        # End point sits on B's border rectangle
        ex, ey = path[-1]
        assert ey == box_b.y
        assert box_b.x <= ex <= box_b.x + box_b.width - 1

    def test_endpoints_not_inside_boxes(self):
        """No visible path point may fall strictly inside either subgraph box."""
        g = parse_flowchart(self.SIMPLE)
        layout = compute_layout(g)
        routed = route_edges(g, layout)
        box_a = self._sg_box(layout, "A")
        box_b = self._sg_box(layout, "B")
        for x, y in routed[0].draw_path:
            for box in (box_a, box_b):
                inside = (
                    box.x < x < box.x + box.width - 1
                    and box.y < y < box.y + box.height - 1
                )
                assert not inside, f"path point ({x},{y}) inside subgraph box"

    def test_all_mixed_edges_routed(self):
        src = (
            "flowchart TD\n"
            "subgraph A\n  A1\n  A2\nend\n"
            "subgraph B\n  B1\n  B2\nend\n"
            "A --> C --> B\n"
            "A --> B\n"
            "A --> B1\n"
            "A1 --> A2\n"
            "A1 --> B1\n"
            "A1 --> B\n"
            "A1 --> C\n"
            "C --> B1\n"
        )
        g = parse_flowchart(src)
        layout = compute_layout(g)
        routed = route_edges(g, layout)
        assert len(routed) == len(g.edges) == 9
        # Every routed edge has a drawable path
        for re in routed:
            assert len(re.draw_path) >= 2

    def test_subgraph_self_edge_does_not_crash(self):
        src = "flowchart TD\nsubgraph A\n  A1\nend\nA --> A\n"
        g = parse_flowchart(src)
        layout = compute_layout(g)
        route_edges(g, layout)  # must not raise
