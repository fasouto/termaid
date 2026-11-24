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
                node = find_box(lines, label)
                if other == title:
                    assert _inside(node, box), f"{label!r} is not inside {title!r}:\n{out}"
                else:
                    assert not _touch(node, box), f"{label!r} is drawn on {other!r}:\n{out}"
    for label in outside:
        node = find_box(lines, label)
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
