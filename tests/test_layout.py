"""Tests for the grid layout engine."""
from __future__ import annotations

import pytest

from termaid.parser.flowchart import parse_flowchart
from termaid.layout.grid import compute_layout, STRIDE


class TestLayerAssignment:
    def test_single_node(self):
        g = parse_flowchart("graph LR\n  A")
        layout = compute_layout(g)
        assert "A" in layout.placements

    def test_chain_layers(self):
        """Nodes in a chain should be in successive layers."""
        g = parse_flowchart("graph LR\n  A --> B --> C")
        layout = compute_layout(g)
        pa = layout.placements["A"]
        pb = layout.placements["B"]
        pc = layout.placements["C"]
        # In LR, layers map to columns
        assert pa.grid.col < pb.grid.col < pc.grid.col

    def test_branching_same_layer(self):
        """Children of the same parent should be in the same layer."""
        g = parse_flowchart("graph LR\n  A --> B\n  A --> C")
        layout = compute_layout(g)
        pb = layout.placements["B"]
        pc = layout.placements["C"]
        assert pb.grid.col == pc.grid.col

    def test_td_layers_vertical(self):
        """In TD mode, layers should map to rows."""
        g = parse_flowchart("graph TD\n  A --> B --> C")
        layout = compute_layout(g)
        pa = layout.placements["A"]
        pb = layout.placements["B"]
        pc = layout.placements["C"]
        assert pa.grid.row < pb.grid.row < pc.grid.row


class TestGridPlacement:
    def test_no_overlap(self):
        """No two nodes should overlap on the grid."""
        g = parse_flowchart("graph LR\n  A --> B\n  A --> C\n  B --> D\n  C --> D")
        layout = compute_layout(g)
        occupied_blocks: list[set[tuple[int, int]]] = []
        for p in layout.placements.values():
            block = set()
            for dc in range(-1, 2):
                for dr in range(-1, 2):
                    block.add((p.grid.col + dc, p.grid.row + dr))
            # Check no overlap with previous blocks
            for prev in occupied_blocks:
                assert not block & prev, f"Node {p.node_id} overlaps with another node"
            occupied_blocks.append(block)

    def test_cycle_doesnt_explode(self):
        """Cycles should not cause infinite layers."""
        g = parse_flowchart("graph LR\n  A --> B --> C --> A")
        layout = compute_layout(g)
        # All nodes should have reasonable grid positions
        for p in layout.placements.values():
            assert p.grid.col < 50, f"Node {p.node_id} at col {p.grid.col} - too far right"
            assert p.grid.row < 50, f"Node {p.node_id} at row {p.grid.row} - too far down"

    def test_all_nodes_placed(self):
        """All nodes in the graph should get placements."""
        g = parse_flowchart("graph LR\n  A --> B\n  C --> D\n  E")
        layout = compute_layout(g)
        for nid in g.node_order:
            assert nid in layout.placements, f"Node {nid} not placed"

    def test_two_roots_separate(self):
        """Two disconnected subgraphs should be placed separately."""
        g = parse_flowchart("graph LR\n  A --> B\n  C --> D")
        layout = compute_layout(g)
        pa = layout.placements["A"]
        pc = layout.placements["C"]
        # Should be in different rows
        assert pa.grid.row != pc.grid.row


class TestDrawCoordinates:
    def test_draw_coords_positive(self):
        """All draw coordinates should be non-negative."""
        g = parse_flowchart("graph LR\n  A --> B --> C")
        layout = compute_layout(g)
        for p in layout.placements.values():
            assert p.draw_x >= 0, f"Node {p.node_id} has negative x"
            assert p.draw_y >= 0, f"Node {p.node_id} has negative y"

    def test_draw_width_height(self):
        """All nodes should have positive width and height."""
        g = parse_flowchart("graph LR\n  A[Long Label Here] --> B")
        layout = compute_layout(g)
        for p in layout.placements.values():
            assert p.draw_width >= 3
            assert p.draw_height >= 3

    def test_canvas_size(self):
        """Canvas should be large enough to contain all nodes."""
        g = parse_flowchart("graph LR\n  A --> B --> C")
        layout = compute_layout(g)
        assert layout.canvas_width > 0
        assert layout.canvas_height > 0
        for p in layout.placements.values():
            assert p.draw_x + p.draw_width <= layout.canvas_width + 1
            assert p.draw_y + p.draw_height <= layout.canvas_height + 1


class TestSubgraphBounds:
    def test_subgraph_contains_nodes(self):
        """Subgraph bounds should contain all its nodes."""
        g = parse_flowchart(
            "graph LR\n  subgraph one\n    A --> B\n  end"
        )
        layout = compute_layout(g)
        assert len(layout.subgraph_bounds) > 0
        sb = layout.subgraph_bounds[0]
        for nid in ["A", "B"]:
            if nid in layout.placements:
                p = layout.placements[nid]
                assert p.draw_x >= sb.x, f"Node {nid} left of subgraph"
                assert p.draw_y >= sb.y, f"Node {nid} above subgraph"


class TestLargeGraph:
    def test_15_node_graph(self):
        """A large graph should layout without errors."""
        g = parse_flowchart(
            "graph TD\n"
            "  A --> B\n  A --> C\n  B --> D\n  B --> E\n"
            "  C --> F\n  C --> G\n  D --> H\n  E --> H\n"
            "  F --> I\n  G --> I\n  H --> J\n  I --> J\n"
            "  J --> K\n  J --> L\n  K --> M\n  L --> M"
        )
        layout = compute_layout(g)
        assert len(layout.placements) == 13  # A-M
        assert layout.canvas_width > 0
        assert layout.canvas_height > 0


class TestOrthogonalSubgraphOrdering:
    def test_cyclic_subgraph_keeps_all_nodes(self):
        from termaid.layout.layers import assign_layers, order_layers

        src = (
            "flowchart TD\n"
            "subgraph S\n"
            "direction LR\n"
            "B\n"
            "A\n"
            "C\n"
            "A --> B\n"
            "B --> C\n"
            "C --> B\n"
            "end\n"
        )
        graph = parse_flowchart(src)
        ordered = order_layers(graph, assign_layers(graph))
        flat = [n for layer in ordered for n in layer]
        assert sorted(flat) == sorted(graph.nodes)


class TestSubgraphEdgeLayers:
    """Edges with subgraph endpoints constrain layer assignment (issue #6)."""

    def test_direct_subgraph_link_separates_layers(self):
        from termaid.layout.layers import assign_layers, expand_subgraph_edges

        src = (
            "flowchart TD\n"
            "subgraph A\n  A1\n  A2\nend\n"
            "subgraph B\n  B1\n  B2\nend\n"
            "A --> B\n"
        )
        g = parse_flowchart(src)
        virtual = expand_subgraph_edges(g)
        assert len(virtual) == 4  # 2 members x 2 members
        g.edges.extend(virtual)
        layers = assign_layers(g)
        assert max(layers["A1"], layers["A2"]) < min(layers["B1"], layers["B2"])

    def test_chain_through_standalone_node(self):
        from termaid.layout.layers import assign_layers, expand_subgraph_edges

        src = (
            "flowchart TD\n"
            "subgraph A\n  A1\n  A2\nend\n"
            "subgraph B\n  B1\n  B2\nend\n"
            "A --> C --> B\n"
        )
        g = parse_flowchart(src)
        g.edges.extend(expand_subgraph_edges(g))
        layers = assign_layers(g)
        assert max(layers["A1"], layers["A2"]) < layers["C"]
        assert layers["C"] < min(layers["B1"], layers["B2"])

    def test_boxes_do_not_touch(self):
        src = (
            "flowchart TD\n"
            "subgraph A\n  A1\n  A2\nend\n"
            "subgraph B\n  B1\n  B2\nend\n"
            "A --> C\n"
        )
        g = parse_flowchart(src)
        layout = compute_layout(g)
        bounds = {sb.subgraph.id: sb for sb in layout.subgraph_bounds}
        box_a, box_b = bounds["A"], bounds["B"]
        # A is above B with a real gap between the borders
        assert box_a.y + box_a.height < box_b.y

    def test_self_and_empty_subgraph_edges_skipped(self):
        from termaid.layout.layers import expand_subgraph_edges

        src = (
            "flowchart TD\n"
            "subgraph A\n  A1\nend\n"
            "A --> A\n"
        )
        g = parse_flowchart(src)
        assert expand_subgraph_edges(g) == []
