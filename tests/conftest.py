"""Test configuration and snapshot testing infrastructure."""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"
FLOWCHARTS_DIR = FIXTURES_DIR / "flowcharts"
EXPECTED_DIR = FIXTURES_DIR / "expected"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-snapshots",
        action="store_true",
        default=False,
        help="Update expected output snapshots",
    )


@pytest.fixture
def update_snapshots(request: pytest.FixtureRequest) -> bool:
    return request.config.getoption("--update-snapshots")


def get_fixture_pairs() -> list[tuple[str, Path, Path]]:
    """Get all (name, input_path, expected_path) tuples for flowchart snapshot testing."""
    pairs = []
    if not FLOWCHARTS_DIR.exists():
        return pairs
    for mmd_file in sorted(FLOWCHARTS_DIR.glob("*.mmd")):
        name = mmd_file.stem
        expected_file = EXPECTED_DIR / f"{name}.txt"
        pairs.append((name, mmd_file, expected_file))
    return pairs


def get_all_fixture_pairs() -> list[tuple[str, Path, Path]]:
    """Scan all diagram-type subdirectories for (name, input_path, expected_path) tuples."""
    pairs = []
    if not FIXTURES_DIR.exists():
        return pairs
    for subdir in sorted(FIXTURES_DIR.iterdir()):
        if not subdir.is_dir() or subdir.name in ("expected", "flowcharts"):
            continue
        diagram_type = subdir.name
        expected_subdir = EXPECTED_DIR / diagram_type
        for mmd_file in sorted(subdir.glob("*.mmd")):
            name = f"{diagram_type}/{mmd_file.stem}"
            expected_file = expected_subdir / f"{mmd_file.stem}.txt"
            pairs.append((name, mmd_file, expected_file))
    return pairs


def assert_no_edge_node_overlap(output: str, nodes: list[str]) -> None:
    """Verify that no edge characters appear inside node boxes.

    This is a heuristic check: for each node label found in the output,
    the characters immediately to the left and right should be spaces or
    box-drawing characters, not edge-routing characters.
    """
    edge_chars = set("┄┆━┃")
    lines = output.split("\n")
    for line in lines:
        for node_label in nodes:
            idx = line.find(node_label)
            if idx >= 0:
                # Check left and right of label
                left_pos = idx - 1
                right_pos = idx + len(node_label)
                if left_pos >= 0:
                    ch = line[left_pos]
                    # Should be space, box char, or part of label
                    assert ch not in edge_chars, (
                        f"Edge char '{ch}' found left of node '{node_label}' in: {line}"
                    )
                if right_pos < len(line):
                    ch = line[right_pos]
                    assert ch not in edge_chars, (
                        f"Edge char '{ch}' found right of node '{node_label}' in: {line}"
                    )


def assert_all_nodes_rendered(output: str, node_labels: list[str]) -> None:
    """Verify all node labels appear in the output.

    Labels may be word-wrapped across multiple lines, so if the full label
    isn't found as a contiguous substring, check that every word appears.
    """
    for label in node_labels:
        if label in output:
            continue
        # Label may be word-wrapped: check all words are present
        words = label.split()
        missing = [w for w in words if w not in output]
        assert not missing, (
            f"Node label '{label}' not found in output "
            f"(missing words: {missing})"
        )


def assert_valid_unicode(output: str) -> None:
    """Verify the output is valid unicode with no replacement characters."""
    assert "\ufffd" not in output, "Output contains Unicode replacement character"
    # Verify it can roundtrip encode/decode
    encoded = output.encode("utf-8")
    decoded = encoded.decode("utf-8")
    assert decoded == output, "Output does not survive UTF-8 roundtrip"


def assert_reasonable_dimensions(output: str, max_width: int = 500, max_height: int = 200) -> None:
    """Verify output dimensions are within reasonable bounds."""
    lines = output.split("\n")
    assert len(lines) <= max_height, f"Output has {len(lines)} lines (max {max_height})"
    max_line_width = max(len(line) for line in lines) if lines else 0
    assert max_line_width <= max_width, f"Output has lines up to {max_line_width} chars (max {max_width})"


def find_box(lines: list[str], label: str) -> tuple[int, int, int, int]:
    """(top, bottom, left, right) rows and columns of the box around ``label``.

    The box is found from its left border, the nearest ``│`` or ``(`` left of
    the first line that shows the label, or ``┤`` where an edge leaves that
    side. Bottom is the first row where that border stops, so a border shared
    with another box reports the shared row. A stadium capsule reports its inset
    top and bottom borders.
    """
    pattern = re.compile(r"[│┤(❨] +" + re.escape(label) + r"( |$)")
    row = next(i for i, line in enumerate(lines) if pattern.search(line))
    left = pattern.search(lines[row]).start()
    side = lines[row][left] if lines[row][left] in "(❨" else "│┤"
    top = row
    while lines[top - 1][left] in side:
        top -= 1
    top -= 1
    bottom = row
    while lines[bottom + 1][left] in side:
        bottom += 1
    bottom += 1
    if lines[top][left : left + 2] == "╭╯" and lines[bottom][left : left + 2] == "╰╮":
        # A stadium capsule: the stepped rows sit inside inset top and bottom borders.
        right = lines[top].index("╮", left + 2)
        return top - 1, bottom + 1, left, right
    right = left + 1
    while lines[top][right] not in "┐┤╮╯/":
        right += 1
    return top, bottom, left, right


_LINKS = {
    "│": "UD", "─": "LR", "┌": "DR", "╭": "DR", "┐": "DL", "╮": "DL",
    "└": "UR", "╰": "UR", "┘": "UL", "╯": "UL",
    "├": "UDR", "┤": "UDL", "┬": "LRD", "┴": "LRU", "┼": "UDLR",
}
_ARROWS = {"▼": "D", "▲": "U", "►": "R", "◄": "L"}
_STEP = {"U": (-1, 0), "D": (1, 0), "L": (0, -1), "R": (0, 1)}
_BACK = {"U": "D", "D": "U", "L": "R", "R": "L"}


def edge_targets(lines: list[str], label: str, labels: list[str]) -> set[str]:
    """Labels of the boxes that the lines leaving ``label``'s box point into.

    Follows box-drawing connectors outward from every side of the box, goes
    straight through ``┼`` crossings, and records the box an arrowhead points
    at. ``labels`` are the node boxes to look for, located with ``find_box``.
    """
    boxes = {name: find_box(lines, name) for name in labels}

    def box_at(row: int, col: int) -> str | None:
        for name, (top, bottom, left, right) in boxes.items():
            if top <= row <= bottom and left <= col <= right:
                return name
        return None

    def char(row: int, col: int) -> str:
        if 0 <= row < len(lines) and 0 <= col < len(lines[row]):
            return lines[row][col]
        return " "

    top, bottom, left, right = boxes[label]
    todo = [(top - 1, c, "U") for c in range(left, right + 1)]
    todo += [(bottom + 1, c, "D") for c in range(left, right + 1)]
    todo += [(r, left - 1, "L") for r in range(top, bottom + 1)]
    todo += [(r, right + 1, "R") for r in range(top, bottom + 1)]
    todo = [(r, c, d) for r, c, d in todo if _BACK[d] in _LINKS.get(char(r, c), "")]
    seen: set[tuple[int, int, str]] = set()
    reached: set[str] = set()
    while todo:
        row, col, heading = todo.pop()
        if (row, col, heading) in seen:
            continue
        seen.add((row, col, heading))
        ch = char(row, col)
        if ch in _ARROWS:
            dr, dc = _STEP[_ARROWS[ch]]
            hit = box_at(row + dr, col + dc)
            if hit:
                reached.add(hit)
            continue
        links = _LINKS.get(ch, "")
        if _BACK[heading] not in links:
            continue
        outs = heading if ch == "┼" else [d for d in links if d != _BACK[heading]]
        for d in outs:
            dr, dc = _STEP[d]
            if box_at(row + dr, col + dc) is None:
                todo.append((row + dr, col + dc, d))
    return reached
