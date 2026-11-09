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

    def test_lr_boxes_in_a_column_keep_their_own_height(self):
        """Stacked LR nodes aren't padded to the tallest one in their column."""
        g = parse_flowchart('graph LR\n  A --> B["1<br>2<br>3<br>4"] & C')
        layout = compute_layout(g)
        assert layout.placements["C"].draw_height < layout.placements["B"].draw_height

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


class TestSiblingAlignment:
    """Issue #14: nodes line up with their own parents, not the packed slot order."""

    SOURCE = "flowchart {direction}\n  A --> B\n  A --> C\n  D --> E\n"

    def _placements(self, direction: str):
        from termaid.layout.grid import compute_layout
        from termaid.parser.flowchart import parse_flowchart

        graph = parse_flowchart(self.SOURCE.format(direction=direction))
        layout = compute_layout(graph)
        return {nid: p.grid for nid, p in layout.placements.items()}

    def test_lr_children_sit_beside_their_parent(self):
        g = self._placements("LR")
        # A's children B and C are the two rows nearest A; D moves down beside E
        assert g["B"].row < g["C"].row < g["E"].row
        assert g["D"].row == g["E"].row
        assert g["A"].row < g["D"].row

    def test_td_children_sit_under_their_parent(self):
        g = self._placements("TD")
        assert g["B"].col < g["C"].col < g["E"].col
        assert g["D"].col == g["E"].col
        assert g["A"].col < g["D"].col

    def test_fan_out_parent_is_centred_over_children(self):
        from termaid.layout.grid import compute_layout
        from termaid.parser.flowchart import parse_flowchart

        layout = compute_layout(parse_flowchart("graph TD\n  A --> B\n  A --> C\n  A --> D\n"))
        g = {nid: p.grid for nid, p in layout.placements.items()}
        assert g["A"].col == g["C"].col


class TestMaxLabelWidth:
    SOURCE = "graph TD\n  A[Read complete words]"

    def test_explicit_width_wraps_at_word_boundaries(self):
        from termaid import render
        output = render(self.SOURCE, max_label_width=8)
        rows = output.splitlines()
        assert "Read complete" not in output
        words = ["Read", "complete", "words"]
        row_of = {word: next(i for i, row in enumerate(rows) if word in row) for word in words}
        assert [row_of[w] for w in words] == list(range(row_of["Read"], row_of["Read"] + 3))

    def test_default_output_unchanged(self):
        from termaid import render
        assert render(self.SOURCE) == render(self.SOURCE, max_label_width=None)
        assert "Read complete words" in render(self.SOURCE)


LONG_EDGE_LABEL = "customer confirms the order and pays with a stored card"


class TestEdgeLabelWrap:
    @pytest.mark.parametrize("direction", ["LR", "TD"])
    def test_edge_label_wraps_into_a_block_of_whole_words(self, direction):
        import re
        from termaid import render
        from termaid.utils import display_width
        source = (
            f"graph {direction}\n"
            f"  A[Start] -->|{LONG_EDGE_LABEL}| B[Charge]\n"
            "  B --> C[Ship]\n"
        )
        words = LONG_EDGE_LABEL.split()
        wrapped = render(source, max_label_width=12)
        label_rows = []
        for row in wrapped.splitlines():
            found = [m for m in re.finditer(r"[A-Za-z]+", row) if m.group() in words]
            if found:
                label_rows.append((row, found))
        assert [m.group() for _, found in label_rows for m in found] == words
        assert len(label_rows) <= 5
        for row, found in label_rows:
            assert display_width(row[found[0].start():found[-1].end()]) <= 12
        widest = lambda text: max(display_width(line) for line in text.splitlines())
        assert widest(wrapped) < widest(render(source))

    def test_default_edge_label_unchanged(self):
        from termaid import render
        source = f"graph LR\n  A -->|{LONG_EDGE_LABEL}| B\n"
        assert LONG_EDGE_LABEL in render(source)
        assert render(source) == render(source, max_label_width=None)


class TestStackedSubgraphBorders:
    """Every subgraph border gets its own row, even when the node above the
    border and the subgraph below it are on adjacent layers."""

    def test_node_border_subgraph_border_and_next_subgraph_are_distinct_rows(self):
        from termaid import render
        from termaid.layout.grid import SG_BORDER_PAD
        from tests.conftest import FLOWCHARTS_DIR, find_box

        lines = render((FLOWCHARTS_DIR / "subgraph_stacked_borders.mmd").read_text()).split("\n")
        r_bottom = find_box(lines, "r")[1]
        a_bottom = find_box(lines, "A")[1]
        b_top = find_box(lines, "B")[0]
        assert r_bottom + SG_BORDER_PAD == a_bottom < b_top


class TestSubgraphWidth:
    """A subgraph box hugs the nodes it owns, plus room for one edge corridor."""

    OWNED = {
        "Ingest": ["Webhook received", "Signature valid?", "Reject 401", "Parse payload"],
        "Processing": [
            "Event type", "Settle invoice", "Reverse ledger entry", "Open case",
            "Ledger DB", "Notify ops",
        ],
        "Delivery": ["Emit domain event", "Publish to Kafka", "Done"],
    }
    CORRIDOR = 8  # one gap column beside the outermost nodes

    def test_width_is_bounded_by_owned_nodes(self):
        from termaid import render
        from termaid.layout.grid import SG_BORDER_PAD
        from tests.conftest import FLOWCHARTS_DIR, find_box

        lines = render((FLOWCHARTS_DIR / "subgraph_pipeline.mmd").read_text()).split("\n")
        widths = {}
        for sg, labels in self.OWNED.items():
            _, _, left, right = find_box(lines, sg)
            boxes = [find_box(lines, label) for label in labels]
            content = max(b[3] for b in boxes) - min(b[2] for b in boxes) + 1
            widths[sg] = (right - left + 1, content + 2 * SG_BORDER_PAD + self.CORRIDOR)
        assert all(width <= bound for width, bound in widths.values()), widths


class TestCycleInsideSubgraph:
    """A back-edge inside a subgraph must not stretch or reorder it."""

    SRC = ("graph TD\n"
           "  subgraph X\n    A --> B --> C\n    C -.-> A\n  end\n"
           "  subgraph Y\n    D --> E --> F\n    F -.-> D\n  end\n")

    def test_order_follows_the_forward_edges(self):
        layout = compute_layout(parse_flowchart(self.SRC))
        rows = {n: layout.placements[n].grid.row for n in "ABCDEF"}
        assert rows["A"] < rows["B"] < rows["C"]
        assert rows["D"] < rows["E"] < rows["F"]

    def test_no_empty_layers(self):
        from termaid import render
        out = render(self.SRC, padding_x=1, padding_y=0, gap=1)
        assert sum(1 for line in out.splitlines() if not line.strip()) <= 5
