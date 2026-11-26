"""Subgraph boxes as drawn: every title shows, each box holds exactly its own
nodes, and no two boxes overlap."""
from __future__ import annotations

import re

import pytest

from termaid import render
from tests.conftest import find_box


def subgraph_box(lines: list[str], title: str) -> tuple[int, int, int, int]:
    """(top, bottom, left, right) of the subgraph box whose title row reads
    ``│ title``. The borders are followed through the ``┼`` and tees that
    edges leave where they cross them, and a line that joins the bottom
    border at its corner turns ``└`` into ``┴``."""
    pattern = re.compile(r"│ " + re.escape(title) + r"( |│|$)")
    found = [(i, m.start()) for i, line in enumerate(lines) for m in [pattern.search(line)] if m]
    assert found, f"No subgraph titled {title!r}:\n" + "\n".join(lines)
    row, left = found[0]
    top = row - 1
    assert lines[top][left] == "┌", f"{title!r} has no top-left corner:\n" + "\n".join(lines)
    right = left + 1
    while lines[top][right] != "┐":
        assert lines[top][right] in "─┬┴┼", f"{title!r} top border is broken:\n" + "\n".join(lines)
        right += 1
    bottom = row
    while lines[bottom][left] not in "└┴":
        assert lines[bottom][left] in "│├┤┼", f"{title!r} left border is broken:\n" + "\n".join(lines)
        bottom += 1
    return top, bottom, left, right


def _inside(inner: tuple[int, int, int, int], outer: tuple[int, int, int, int]) -> bool:
    return outer[0] < inner[0] and inner[1] < outer[1] and outer[2] < inner[2] and inner[3] < outer[3]


def _touch(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1] and a[2] <= b[3] and b[2] <= a[3]


def _node(lines: list[str], label: str) -> tuple[int, int, int, int]:
    try:
        return find_box(lines, label)
    except StopIteration:
        raise AssertionError(f"Node {label!r} is not drawn whole:\n" + "\n".join(lines)) from None


def assert_subgraphs(out: str, members: dict[str, list[str]], outside: list[str] = ()) -> None:
    """Each title in ``members`` is drawn on its own box, holding exactly the
    nodes listed for it; the boxes are apart, and ``outside`` nodes are clear
    of every box."""
    lines = out.split("\n")
    boxes = {title: subgraph_box(lines, title) for title in members}
    titles = list(boxes)
    for i, a in enumerate(titles):
        for b in titles[i + 1:]:
            assert not _touch(boxes[a], boxes[b]), f"Boxes {a!r} and {b!r} overlap:\n{out}"
    for title, labels in members.items():
        for other, box in boxes.items():
            for label in labels:
                node = _node(lines, label)
                if other == title:
                    assert _inside(node, box), f"{label!r} is not inside {title!r}:\n{out}"
                else:
                    assert not _touch(node, box), f"{label!r} is drawn on {other!r}:\n{out}"
    for label in outside:
        node = _node(lines, label)
        for title, box in boxes.items():
            assert not _touch(node, box), f"{label!r} is drawn on {title!r}:\n{out}"


CLIENT_SERVER = (
    "flowchart {d}\n"
    "  subgraph C [Client]\n    req[Send request]\n    show[Show result]\n  end\n"
    "  subgraph S [Server]\n    handle[Handle]\n    reply[Reply]\n  end\n"
    "  req --> handle\n  reply --> show\n"
)


class TestSubgraphsLinkedBothWays:
    """Edges both ways between two subgraphs used to leave both on the same
    layers, so they were drawn as one box and one title vanished."""

    @pytest.mark.parametrize("d", ["LR", "TD", "RL", "BT"])
    def test_client_and_server_are_two_boxes(self, d):
        assert_subgraphs(
            render(CLIENT_SERVER.format(d=d)),
            {"Client": ["Send request", "Show result"], "Server": ["Handle", "Reply"]},
        )

    def test_flows_inside_each_subgraph(self):
        src = (
            "flowchart LR\n"
            "  subgraph Browser\n    buy[Click buy] --> show[Show receipt]\n  end\n"
            "  subgraph Server\n    api[POST order] --> save[Save order]\n  end\n"
            "  buy --> api\n  save --> show\n"
        )
        assert_subgraphs(
            render(src),
            {"Browser": ["Click buy", "Show receipt"], "Server": ["POST order", "Save order"]},
        )


class TestTitleWiderThanContents:
    """A title wider than the nodes in its subgraph stretches the box only as
    far as the next node or box. Past that the title is clipped, so the
    drawing gets no wider and the box covers no neighbour."""

    @pytest.mark.parametrize("d", ["LR", "RL"])
    def test_next_node_stays_outside(self, d):
        src = (
            f"flowchart {d}\n"
            "  subgraph A [Payment processing service]\n    pay\n  end\n"
            "  pay --> db[(Ledger)]\n"
        )
        out = render(src)
        assert_subgraphs(out, {"Payment …": ["pay"]}, outside=["Ledger"])
        plain = render(src.replace("Payment processing service", "Pay"))
        assert len(out.split("\n")[0]) <= max(map(len, plain.split("\n"))), out

    @pytest.mark.parametrize("d", ["TD", "BT"])
    def test_node_beside_stays_outside(self, d):
        src = (
            f"flowchart {d}\n  start --> pay & audit\n"
            "  subgraph A [Payment processing service]\n    pay\n  end\n"
        )
        assert_subgraphs(render(src), {"Payment proce…": ["pay"]}, outside=["start", "audit"])

    def test_next_subgraph_stays_apart(self):
        src = (
            "flowchart LR\n"
            "  subgraph A [Authentication and session service]\n    login\n  end\n"
            "  subgraph B [Billing]\n    pay\n  end\n"
            "  login --> pay\n"
        )
        assert_subgraphs(render(src), {"Authenticatio…": ["login"], "Billing": ["pay"]})

    def test_title_with_nothing_beside_it_is_whole(self):
        out = render("flowchart TD\n  subgraph A [Payment processing service]\n    pay\n  end\n")
        assert "│ Payment processing service │" in out

    def test_ascii_clips_with_a_dot(self):
        src = (
            "flowchart LR\n"
            "  subgraph A [Payment processing service]\n    pay\n  end\n"
            "  pay --> db[Ledger]\n"
        )
        out = render(src, use_ascii=True)
        assert "| Payment . |" in out, out


class TestOutsideNodeBetweenMembers:
    """A node outside a subgraph whose layer falls between the members'
    layers was drawn inside the box."""

    @pytest.mark.parametrize("d", ["LR", "TB"])
    def test_a_node_both_fed_by_and_feeding_a_subgraph_stays_outside(self, d):
        src = (
            f"flowchart {d}\n"
            "  subgraph Server\n    api[API]\n    worker[Worker]\n  end\n"
            "  client[Client] --> api\n  worker --> client\n"
        )
        assert_subgraphs(render(src), {"Server": ["API", "Worker"]}, outside=["Client"])

    def test_a_node_on_a_layer_between_members_stays_outside(self):
        src = (
            "flowchart TD\n"
            "  subgraph S\n    a\n    b\n  end\n"
            "  r --> a\n  r --> q --> p --> b\n"
        )
        assert_subgraphs(render(src), {"S": ["a", "b"]}, outside=["r", "q", "p"])

    @pytest.mark.parametrize("d", ["TD", "LR", "BT", "RL"])
    def test_a_sibling_declared_between_members_stays_outside(self, d):
        src = (
            f"flowchart {d}\n  R --> A\n  R --> X\n  R --> B\n"
            "  subgraph S\n    A\n    B\n  end\n"
        )
        assert_subgraphs(render(src), {"S": ["A", "B"]}, outside=["R", "X"])

    def test_a_sibling_between_nested_members_stays_outside_both(self):
        src = (
            "flowchart TD\n  R --> A & X & B & C\n"
            "  subgraph Outer\n    C\n    subgraph Inner\n      A\n      B\n    end\n  end\n"
        )
        assert_subgraphs(render(src), {"Inner": ["A", "B"]}, outside=["R", "X"])
        lines = render(src).split("\n")
        assert not _touch(_node(lines, "X"), subgraph_box(lines, "Outer")), render(src)

    def test_a_node_between_nested_members_stays_outside_both(self):
        src = (
            "flowchart LR\n"
            "  subgraph Outer\n    subgraph Server\n      api[API]\n      worker[Worker]\n    end\n  end\n"
            "  client[Client] --> api\n  worker --> client\n"
        )
        out = render(src)
        lines = out.split("\n")
        client = _node(lines, "Client")
        for title in ("Outer", "Server"):
            assert not _touch(client, subgraph_box(lines, title)), out

