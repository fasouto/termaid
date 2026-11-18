"""RL and BT drawings are the LR and TD drawings mirrored as geometry only:
text reads as written, shapes keep their look, titles stay on top."""
from __future__ import annotations

import pytest

from termaid import render


def lines_of(source: str) -> list[str]:
    return render(source).split("\n")


def find(lines: list[str], text: str) -> tuple[int, int]:
    hits = [(r, line.index(text)) for r, line in enumerate(lines) if text in line]
    assert len(hits) == 1, f"{text!r} drawn {len(hits)} times in\n" + "\n".join(lines)
    return hits[0]


class TestTextReadsAsWritten:
    def test_rl_node_and_edge_labels(self):
        out = render("graph RL\n  A[Hello World] -->|sends to| B[Second]\n")
        for text in ("Hello World", "Second", "sends to"):
            assert text in out, out

    def test_bt_labels_keep_their_characters_and_line_order(self):
        lines = lines_of(
            "graph BT\n"
            "  A[Vivid<br/>second line] --> B{Check ▲▼}\n"
            "  subgraph Group title\n"
            "    B --> C[/Trapezoid/]\n"
            "  end\n"
        )
        first, _ = find(lines, "Vivid")
        second, _ = find(lines, "second line")
        assert second == first + 1
        find(lines, "Check ▲▼")
        find(lines, "Trapezoid")

    def test_state_diagram_note_reads_as_written(self):
        source = (
            "stateDiagram-v2\n"
            "    direction {}\n"
            "    Waiting --> Running\n"
            "    note right of Running : runs the job\n"
        )
        forward, mirrored = render(source.format("LR")), render(source.format("RL"))
        for text in ("Waiting", "Running", "runs the job"):
            assert text in mirrored, mirrored
        assert max(map(len, mirrored.split("\n"))) <= max(map(len, forward.split("\n"))), mirrored


@pytest.mark.parametrize("direction", ["RL", "BT"])
def test_subgraph_title_on_the_top_row_of_its_box(direction):
    lines = lines_of(
        f"graph {direction}\n"
        "  X --> A\n"
        "  subgraph Group title\n"
        "    A --> B\n"
        "  end\n"
    )
    row, col = find(lines, "Group title")
    assert lines[row - 1][col - 2] == "┌", "\n".join(lines)
    assert lines[row][col - 2] == "│", "\n".join(lines)


def test_rl_arrowhead_points_left_into_the_target():
    lines = lines_of("graph RL\n  A[Source] --> B[Target]\n")
    row, col = find(lines, "Target")
    assert "│◄" in lines[row][col:], "\n".join(lines)
    assert "►" not in "\n".join(lines)


def test_bt_arrowhead_points_up_into_the_target():
    lines = lines_of("graph BT\n  A[Source] --> B[Target]\n")
    row, col = find(lines, "Target")
    below = [line[col + 2] if len(line) > col + 2 else " " for line in lines[row + 1:]]
    first_mark = next(ch for ch in below if ch != " ")
    assert first_mark in "─┬", "\n".join(lines)
    assert "▲" in "\n".join(lines) and "▼" not in "\n".join(lines)


@pytest.mark.parametrize("direction", ["RL", "BT"])
def test_no_leading_blank_rows_or_columns(direction):
    lines = lines_of(f"graph {direction}\n  A --> B --> C\n")
    assert lines[0].strip(), "\n".join(lines)
    assert any(line and line[0] != " " for line in lines), "\n".join(lines)


@pytest.mark.parametrize("shape", [
    "[/Lean/]", "[\\Lean\\]", "[/Trap\\]", "[\\Trap/]",
    ">Flag]", "{{Hexagon}}", "([Stadium])", "[(Cylinder)]",
])
@pytest.mark.parametrize("reversed_dir, forward_dir", [("RL", "LR"), ("BT", "TD")])
def test_a_shape_reads_as_in_the_forward_direction(shape, reversed_dir, forward_dir):
    assert render(f"graph {reversed_dir}\n  A{shape}\n") == render(f"graph {forward_dir}\n  A{shape}\n")


MIRROR_SOURCES = [
    "A[Alpha] --> B[Beta] --> C[Gamma]\n",
    "A[Alpha] --> B[Beta]\n  A --> C[Gamma]\n  B --> D[Delta]\n  C --> D\n",
    "A[Alpha] --> B[Beta] --> C[Gamma]\n  C --> A\n",
    "A[Alpha] -->|one| B[Beta]\n  A -->|two| C[Gamma]\n",
    "A[Alpha] --> B[Beta]\n  subgraph Group\n    B --> C[Gamma]\n  end\n  C --> D[Delta]\n",
]
NAMES = ("Alpha", "Beta", "Gamma", "Delta")


def boxes(lines: list[str], horizontal: bool) -> dict[str, tuple[int, int, int]]:
    """Each node's (row, left, right) for horizontal, (col, top, bottom)
    otherwise: the first border met walking out from its label."""
    found = {}
    for name in NAMES:
        hits = [(r, line.index(name)) for r, line in enumerate(lines) if name in line]
        if not hits:
            continue
        row, col = hits[0]
        if horizontal:
            line = lines[row]
            left = max(c for c in range(col) if line[c] != " ")
            right = min(c for c in range(col + len(name), len(line)) if line[c] != " ")
            found[name] = (row, left, right)
        else:
            column = [line[col] if len(line) > col else " " for line in lines]
            top = max(r for r in range(row) if column[r] != " ")
            bottom = min(r for r in range(row + 1, len(lines)) if column[r] != " ")
            found[name] = (col, top, bottom)
    return found


@pytest.mark.parametrize("body", MIRROR_SOURCES)
@pytest.mark.parametrize("reversed_dir, forward_dir", [("RL", "LR"), ("BT", "TD")])
def test_boxes_are_the_mirror_of_the_forward_drawing(body, reversed_dir, forward_dir):
    forward = lines_of(f"graph {forward_dir}\n  {body}")
    mirrored = lines_of(f"graph {reversed_dir}\n  {body}")
    horizontal = reversed_dir == "RL"
    fwd, rev = boxes(forward, horizontal), boxes(mirrored, horizontal)
    assert fwd.keys() == rev.keys()
    axes = {fwd[n][1] + rev[n][2] for n in fwd} | {fwd[n][2] + rev[n][1] for n in fwd}
    assert len(axes) == 1, "\n".join(forward + ["----"] + mirrored)
    assert all(fwd[n][0] == rev[n][0] for n in fwd), "\n".join(forward + ["----"] + mirrored)
    assert max(map(len, mirrored)) <= max(map(len, forward))
    assert len(mirrored) <= len(forward)
