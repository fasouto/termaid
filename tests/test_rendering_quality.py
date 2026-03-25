"""Tests for rendering quality issues.

These tests document known rendering bugs and verify fixes.
Each test is marked with xfail until the corresponding bug is fixed.
"""
from __future__ import annotations

import pytest

from termaid import render


class TestTrailingDanglingCharacters:
    """Bug 2: Trailing dangling characters after back-edge junctions."""

    def test_back_edge_no_trailing_chars(self):
        """Back edges should not leave trailing chars after junction characters.

        With D-->A and D-->B back edges, the output shows:
            │  B  │◄─┼─     (trailing ─ after ┼)
            │  D  ├──┴─     (trailing ─ after ┴)
        """
        src = "graph TD\n  A-->B\n  B-->C\n  C-->D\n  D-->A\n  D-->B"
        out = render(src)
        for line in out.split("\n"):
            stripped = line.rstrip()
            if stripped.endswith("┼─") or stripped.endswith("┴─"):
                pytest.fail(f"Trailing '─' after junction: {stripped!r}")

    def test_single_back_edge_no_trailing(self):
        """A single back edge should not leave trailing chars."""
        src = "graph TD\n  A-->B\n  B-->C\n  C-->A"
        out = render(src)
        for line in out.split("\n"):
            stripped = line.rstrip()
            if stripped.endswith("┼─") or stripped.endswith("┴─"):
                pytest.fail(f"Trailing '─' after junction: {stripped!r}")


class TestArrowBorderCollision:
    """Bug 3: Arrow tip ◄ collides with node border ├."""

    def test_hub_node_no_arrow_border_collision(self):
        """A node receiving and sending edges should not have ├◄ collision.

        With 3 inputs and 3 outputs on node D, the output shows:
            │  D  ├◄─╮──────────╯
        The ├ (outgoing border) and ◄ (incoming arrow) should not be adjacent.
        """
        src = "graph TD\n  A-->D\n  B-->D\n  C-->D\n  D-->E\n  D-->F\n  D-->G"
        out = render(src)
        assert "├◄" not in out, f"Arrow-border collision ├◄ found:\n{out}"

    def test_fan_in_edge_touches_border(self):
        """Fan-in edges should not connect directly to unrelated node borders.

        With 4 nodes pointing to E, the output shows:
            │  C  │  ╭─┤  C  │
        The ╭─┤ means the routing edge runs directly into C's border.
        """
        src = "graph TD\n  A-->E\n  B-->E\n  C-->E\n  D-->E"
        out = render(src)
        # ╭─┤ means an edge line runs into a node's right border
        assert "╭─┤" not in out, f"Edge connects to wrong node border:\n{out}"


class TestJunctionCharacters:
    """Bug 5: Wrong junction characters in LR branching."""

    def test_lr_branch_no_corner_before_arrow(self):
        """LR branching edges should not have ╭► or ╯► sequences.

        With cross-connected A->C, A->D, B->C, B->D, the output shows:
            │  A  ├──╭►│  C  │
            │  B  ├──╯►│  D  │
        ╭► and ╯► are wrong: the corner implies a turn but ► goes straight right.
        """
        src = "graph LR\n  A-->C\n  B-->D\n  A-->D\n  B-->C"
        out = render(src)
        assert "╭►" not in out, f"Wrong junction ╭► in LR branch:\n{out}"
        assert "╯►" not in out, f"Wrong junction ╯► in LR branch:\n{out}"


class TestSubgraphLayout:
    """Bug 7: Nodes rendered in wrong subgraph when cross-boundary edges exist."""

    def test_nodes_stay_in_declared_subgraph(self):
        """Nodes should be visually inside their declared subgraph.

        With A,B in S1 and C,D in S2, plus cross-edges B-->C and A-->D,
        node B (belongs to S1) gets rendered inside S2's visual boundary.
        """
        src = (
            "graph TD\n"
            "  subgraph S1\n    A-->B\n  end\n"
            "  subgraph S2\n    C-->D\n  end\n"
            "  B-->C\n  A-->D"
        )
        out = render(src)
        lines = out.split("\n")

        # Find the row where S2 label appears
        s2_start = None
        for i, line in enumerate(lines):
            if "S2" in line:
                s2_start = i
                break

        assert s2_start is not None, f"S2 not found in output:\n{out}"

        # Find row where B appears
        b_row = None
        for i, line in enumerate(lines):
            if "  B  " in line:
                b_row = i
                break

        assert b_row is not None, f"Node B not found in output:\n{out}"

        # B should appear BEFORE S2 starts (it belongs to S1)
        assert b_row < s2_start, (
            f"Node B (row {b_row}) appears after S2 label (row {s2_start}), "
            f"but B belongs to S1:\n{out}"
        )


class TestMissingEdges:
    """Bug 8: Edges missing when labels overlap with crossings."""

    def test_all_four_edges_rendered(self):
        """All 4 edges should be visible even with crossing labels.

        With A-->|left|C, B-->|right|D, A-->D, B-->C, only 2 arrows
        appear in the output instead of 4.
        """
        src = 'graph TD\n  A-->|left|C\n  B-->|right|D\n  A-->D\n  B-->C'
        out = render(src)
        arrow_count = out.count("▼") + out.count("►")
        assert arrow_count >= 4, (
            f"Expected 4 arrows for 4 edges, found {arrow_count}:\n{out}"
        )

    def test_crossing_labels_on_separate_lines(self):
        """Edge labels on crossing edges should not merge into one line.

        The output shows:
            ╭left───right╯
        Both labels are on the same horizontal segment, which is wrong.
        """
        src = 'graph TD\n  A-->|left|C\n  B-->|right|D\n  A-->D\n  B-->C'
        out = render(src)
        for line in out.split("\n"):
            if "left" in line and "right" in line:
                pytest.fail(
                    f"Labels merged on same line: {line!r}\n{out}"
                )


class TestSubgraphBorderCrossings:
    """Subgraph borders should remain intact when edges cross them."""

    def test_simple_cross_boundary_has_crossing_char(self):
        """Vertical edge through horizontal subgraph border should use ┼."""
        src = (
            "graph TD\n"
            "  subgraph S1\n    A-->B\n  end\n"
            "  subgraph S2\n    C-->D\n  end\n"
            "  B-->C"
        )
        out = render(src)
        assert "┼" in out, f"Expected ┼ at subgraph border crossing:\n{out}"

    def test_three_subgraphs_all_present(self):
        """All three subgraphs should be visible with cross-boundary edges."""
        src = (
            "graph TD\n"
            "  subgraph S1\n    A\n  end\n"
            "  subgraph S2\n    B\n  end\n"
            "  subgraph S3\n    C\n  end\n"
            "  A-->B\n  B-->C"
        )
        out = render(src)
        for sg in ["S1", "S2", "S3"]:
            assert sg in out, f"Subgraph {sg} missing:\n{out}"
        for node in ["A", "B", "C"]:
            assert node in out, f"Node {node} missing:\n{out}"


class TestGapParameter:
    """Test the gap parameter for compact rendering."""

    def test_gap_reduces_width_lr(self):
        """Smaller gap should produce narrower LR output."""
        src = "graph LR\n  A-->B-->C-->D-->E"
        w4 = max(len(l) for l in render(src, gap=4).split("\n"))
        w1 = max(len(l) for l in render(src, gap=1).split("\n"))
        assert w1 < w4

    def test_gap_minimum_clamped_to_one(self):
        """Gap of 0 should be clamped to 1."""
        src = "graph LR\n  A-->B-->C"
        assert render(src, gap=0) == render(src, gap=1)

    def test_gap_preserves_all_nodes(self):
        """All nodes should be visible with compact gap."""
        src = "graph LR\n  A-->B-->C-->D-->E-->F"
        out = render(src, gap=1)
        for node in "ABCDEF":
            assert node in out

    def test_gap_preserves_arrows(self):
        """Arrows should be visible with gap=1."""
        src = "graph LR\n  A-->B-->C"
        out = render(src, gap=1)
        assert "►" in out or ">" in out

    def test_gap_reduces_height_td(self):
        """Smaller gap should produce shorter TD output."""
        src = "graph TD\n  A-->B-->C"
        h4 = render(src, gap=4).count("\n")
        h2 = render(src, gap=2).count("\n")
        assert h2 < h4

    def test_large_gap(self):
        """Large gap values should work."""
        src = "graph LR\n  A-->B-->C"
        out = render(src, gap=20)
        for node in "ABC":
            assert node in out

    def test_gap_with_edge_labels(self):
        """Edge labels should still fit with compact gap."""
        src = 'graph LR\n  A-->|yes|B-->|no|C'
        out = render(src, gap=2)
        assert "yes" in out
        assert "no" in out
