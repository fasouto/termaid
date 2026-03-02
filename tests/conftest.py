"""Test configuration and snapshot testing infrastructure."""
from __future__ import annotations

import os
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
    """Get all (name, input_path, expected_path) tuples for snapshot testing."""
    pairs = []
    if not FLOWCHARTS_DIR.exists():
        return pairs
    for mmd_file in sorted(FLOWCHARTS_DIR.glob("*.mmd")):
        name = mmd_file.stem
        expected_file = EXPECTED_DIR / f"{name}.txt"
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
