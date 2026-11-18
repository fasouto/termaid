"""Tests for rendering quality issues.

These tests document known rendering bugs and verify fixes.
Each test is marked with xfail until the corresponding bug is fixed.
"""
from __future__ import annotations

import re

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
        arrow_count = sum(out.count(arrow) for arrow in "▼►◄▲")
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



class TestLabelsKeepOffOtherLines:
    """A label written over another edge's line cuts that edge."""

    def test_label_leaves_a_sibling_line_whole(self):
        from tests.conftest import edge_targets

        src = (
            "flowchart LR\n"
            "  A[Hard edge] -->|Link text| B(Round edge)\n"
            "  B --> C{Decision}\n"
            "  C -->|One| D[Result one]\n"
            "  C -->|Two| E[Result two]"
        )
        out = render(src)
        reached = edge_targets(out.split("\n"), "Decision", ["Decision", "Result one", "Result two"])
        assert reached == {"Result one", "Result two"}, out

    def test_label_stays_out_of_a_node_box(self):
        from tests.conftest import find_box

        src = (
            "graph LR\n"
            "  A[Client] <-->|sync| B[Server]\n"
            "  B <-.->|heartbeat| C[Monitor]\n"
            "  C <==>|data| D[Storage]"
        )
        out = render(src)
        lines = out.split("\n")
        top, bottom, left, right = find_box(lines, "Storage")
        inside = [line[left + 1:right] for line in lines[top + 1:bottom]]
        assert not any("data" in row for row in inside), out

    @pytest.mark.parametrize(
        "src,boxes,labels",
        [
            ("graph TD\n  A -->|yes| B\n  A -->|no| B", ["B"], ["yes", "no"]),
            (
                "stateDiagram-v2\n"
                "  [*] --> Draft\n"
                "  Draft --> Approved : approve\n"
                "  state Approved {\n"
                "    [*] --> Queued\n"
                "    Queued --> Building : runner free\n"
                "    Building --> Testing : build ok\n"
                "    Testing --> Ready : tests pass\n"
                "  }\n"
                "  Approved --> Released : publish",
                ["Building", "Testing", "Ready"],
                ["runner free", "build ok", "tests pass"],
            ),
        ],
    )
    def test_label_never_lands_on_the_blank_inside_of_a_box(self, src, boxes, labels):
        """A box's blank inside read as free space, so labels with no room
        between boxes were written into the next box."""
        from tests.conftest import find_box

        out = render(src)
        lines = out.split("\n")
        for name in boxes:
            top, bottom, left, right = find_box(lines, name)
            inside = " ".join(line[left + 1:right] for line in lines[top + 1:bottom])
            assert inside.split() == [name], out
        for label in labels:
            assert label in out, out

    def test_label_keeps_off_a_subgraph_title(self):
        """Titles were drawn after the labels, over any label that had
        taken the title's cells: `│ Servicesk│`."""
        src = (
            "flowchart TD\n"
            "  U[User request] --> GW{API gateway}\n"
            "  subgraph Edge\n"
            "    GW -->|static| CDN[CDN cache]\n"
            "    GW -->|api| AUTH[Auth check]\n"
            "  end\n"
            "  subgraph Services\n"
            "    AUTH -->|ok| ORD[Orders]\n"
            "    AUTH -->|ok| CAT[Catalog]\n"
            "    ORD --> PAY[Payments]\n"
            "    ORD --> INV[Inventory]\n"
            "  end\n"
            "  subgraph Data\n"
            "    PAY --> PG[(Postgres)]\n"
            "    INV --> PG\n"
            "    CAT --> RD[(Redis)]\n"
            "    ORD --> MQ[[Event queue]]\n"
            "  end\n"
            "  MQ --> MAIL[Email worker]\n"
            "  MQ --> AN[Analytics]\n"
            "  AUTH -->|denied| ERR[401 response]"
        )
        out = render(src)
        assert "│ Services " in out, out
        assert len(re.findall(r"\bok\b", out)) == 2, out

    @pytest.mark.parametrize(
        "src,kwargs,title,labels",
        [
            (
                "stateDiagram-v2\n"
                "  state Approved {\n"
                "    [*] --> Queued\n"
                "    Queued --> Building : runner free\n"
                "    Building --> Testing : build ok\n"
                "  }",
                {},
                "Approved",
                ["runner free", "build ok"],
            ),
            (
                "flowchart LR\n  subgraph S[Console]\n    A --> B\n  end\n"
                "  B -->|too big?<br>shrink 30%| B2[_shrink]\n  B -->|fits| C[x]",
                {"padding_x": 2, "padding_y": 0, "gap": 2},
                "Console",
                ["too big?", "shrink 30%", "fits"],
            ),
        ],
        ids=["composite-state", "block-label"],
    )
    def test_label_never_cuts_a_subgraph_border(self, src, kwargs, title, labels):
        """With no room inside a subgraph, the last-resort spot ran the label
        through the subgraph's side: `│        │runner free`."""
        from tests.conftest import find_box

        out = render(src, **kwargs)
        lines = out.split("\n")
        top, bottom, left, right = find_box(lines, title)
        for line in lines[top + 1:bottom]:
            assert line[left] in "│├┼" and line[right:right + 1] in ("│", "┤", "┼"), out
        for label in labels:
            assert label in out, out


def _find_label(lines: list[str], label: str) -> tuple[int, int]:
    """Row and column of a label drawn whole on one line."""
    row = next((i for i, line in enumerate(lines) if label in line), None)
    assert row is not None, f"{label!r} not drawn whole\n" + "\n".join(lines)
    return row, lines[row].index(label)


class TestLayoutLeavesRoomForLabels:
    """Each label gets a spot beside its own edge, cutting no line."""

    @pytest.mark.parametrize(
        "src,chain",
        [
            (
                "flowchart TD\n"
                "  A[Start] --> P\n"
                "  subgraph P[Pipeline]\n"
                "    direction LR\n"
                "    B[Build] -->|compile ok| C[Test]\n"
                "    C -->|tests pass| D[Ship]\n"
                "  end",
                [("Build", "compile ok", "Test"), ("Test", "tests pass", "Ship")],
            ),
            (
                "stateDiagram-v2\n"
                "  [*] --> Draft\n"
                "  Draft --> Review : submit\n"
                "  Review --> Approved : approve\n"
                "  state Approved {\n"
                "    [*] --> Queued\n"
                "    Queued --> Building : runner free\n"
                "    Building --> Testing : build ok\n"
                "    Testing --> Ready : tests pass\n"
                "  }\n"
                "  Approved --> Released : publish",
                [
                    ("Queued", "runner free", "Building"),
                    ("Building", "build ok", "Testing"),
                    ("Testing", "tests pass", "Ready"),
                ],
            ),
        ],
        ids=["lr-subgraph", "composite-state"],
    )
    def test_label_sits_on_an_arrow_across_the_flow(self, src, chain):
        """A subgraph laid out across a top-down flow got no room between
        its boxes, so its labels went to the empty row above them."""
        from tests.conftest import edge_targets, find_box

        out = render(src)
        lines = out.split("\n")
        for source, label, target in chain:
            s_top, s_bottom, _, s_right = find_box(lines, source)
            _, _, t_left, _ = find_box(lines, target)
            row, col = _find_label(lines, label)
            assert s_top < row < s_bottom and s_right < col and col + len(label) <= t_left, out
            assert edge_targets(lines, source, [source, target]) == {target}, out

    def test_label_inside_a_subgraph_keeps_off_its_border(self):
        """A subgraph was only as wide as its nodes, so `runner free` was
        forced across its own line and `build ok` touched the border."""
        from tests.conftest import edge_targets, find_box

        src = (
            "stateDiagram-v2\n"
            "  state Approved {\n"
            "    [*] --> Queued\n"
            "    Queued --> Building : runner free\n"
            "    Building --> Testing : build ok\n"
            "  }"
        )
        out = render(src)
        lines = out.split("\n")
        _, _, left, right = find_box(lines, "Approved")
        for label in ("runner free", "build ok"):
            _, col = _find_label(lines, label)
            assert left + 1 < col and col + len(label) < right, out
        names = ["Queued", "Building", "Testing"]
        assert edge_targets(lines, "Queued", names) == {"Building"}, out
        assert edge_targets(lines, "Building", names) == {"Testing"}, out


class TestBackEdgesIntoOneNode:
    """Two back-edges spread along one border of the node they both reach."""

    def test_state_back_edges_turn_cleanly_and_do_not_cross(self):
        src = (
            "stateDiagram-v2\n"
            "  Draft --> Review : submit\n"
            "  Review --> Draft : changes requested\n"
            "  Review --> Approved : approve\n"
            "  Approved --> Draft : build or tests fail"
        )
        out = render(src)
        assert "┤" not in out, f"A back-edge turn doubles back on itself:\n{out}"
        assert "┼" not in out, f"The back-edges cross:\n{out}"

    def test_lr_back_edges_do_not_cross(self):
        src = "flowchart LR\n  Draft --> Review\n  Review --> Draft\n  Review --> Approved\n  Approved --> Draft"
        out = render(src)
        assert "┼" not in out, f"The back-edges cross:\n{out}"


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
