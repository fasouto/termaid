"""Snapshot tests for rendered output.

Each .mmd fixture is rendered and compared against the expected .txt output.
If expected output doesn't exist, the test generates it and marks as "needs review".
Run with --update-snapshots to regenerate all expected outputs.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from termaid import render
from tests.conftest import (
    EXPECTED_DIR,
    FLOWCHARTS_DIR,
    assert_all_nodes_rendered,
    assert_no_edge_node_overlap,
    assert_reasonable_dimensions,
    assert_valid_unicode,
    get_fixture_pairs,
)


# Ensure expected dir exists
EXPECTED_DIR.mkdir(parents=True, exist_ok=True)


def _get_node_labels(source: str) -> list[str]:
    """Extract expected node labels from mermaid source."""
    from termaid import parse
    graph = parse(source)
    return [n.label for n in graph.nodes.values()]


class TestSnapshotRendering:
    """Snapshot tests: render each fixture and compare to expected output."""

    @pytest.mark.parametrize(
        "name,input_path,expected_path",
        get_fixture_pairs(),
        ids=[p[0] for p in get_fixture_pairs()],
    )
    def test_snapshot(
        self,
        name: str,
        input_path: Path,
        expected_path: Path,
        update_snapshots: bool,
    ):
        source = input_path.read_text(encoding="utf-8").strip()
        output = render(source)

        if update_snapshots or not expected_path.exists():
            expected_path.write_text(output + "\n", encoding="utf-8")
            if not update_snapshots:
                pytest.skip(f"Generated new snapshot for {name} - needs review")
            return

        expected = expected_path.read_text(encoding="utf-8").rstrip("\n")
        assert output == expected, (
            f"Snapshot mismatch for {name}.\n"
            f"Run with --update-snapshots to update.\n"
            f"Got:\n{output}\n\nExpected:\n{expected}"
        )


class TestRenderingInvariants:
    """Property-based tests that verify rendering invariants across all fixtures."""

    @pytest.mark.parametrize(
        "name,input_path,expected_path",
        get_fixture_pairs(),
        ids=[p[0] for p in get_fixture_pairs()],
    )
    def test_all_nodes_rendered(self, name: str, input_path: Path, expected_path: Path):
        source = input_path.read_text(encoding="utf-8").strip()
        output = render(source)
        labels = _get_node_labels(source)
        assert_all_nodes_rendered(output, labels)

    @pytest.mark.parametrize(
        "name,input_path,expected_path",
        get_fixture_pairs(),
        ids=[p[0] for p in get_fixture_pairs()],
    )
    def test_valid_unicode(self, name: str, input_path: Path, expected_path: Path):
        source = input_path.read_text(encoding="utf-8").strip()
        output = render(source)
        assert_valid_unicode(output)

    @pytest.mark.parametrize(
        "name,input_path,expected_path",
        get_fixture_pairs(),
        ids=[p[0] for p in get_fixture_pairs()],
    )
    def test_reasonable_dimensions(self, name: str, input_path: Path, expected_path: Path):
        source = input_path.read_text(encoding="utf-8").strip()
        output = render(source)
        assert_reasonable_dimensions(output)

    @pytest.mark.parametrize(
        "name,input_path,expected_path",
        get_fixture_pairs(),
        ids=[p[0] for p in get_fixture_pairs()],
    )
    def test_no_edge_node_overlap(self, name: str, input_path: Path, expected_path: Path):
        source = input_path.read_text(encoding="utf-8").strip()
        output = render(source)
        labels = _get_node_labels(source)
        assert_no_edge_node_overlap(output, labels)


class TestAsciiMode:
    """Test that ASCII mode works for all fixtures."""

    @pytest.mark.parametrize(
        "name,input_path,expected_path",
        get_fixture_pairs(),
        ids=[p[0] for p in get_fixture_pairs()],
    )
    def test_ascii_renders(self, name: str, input_path: Path, expected_path: Path):
        source = input_path.read_text(encoding="utf-8").strip()
        output = render(source, use_ascii=True)
        assert len(output) > 0
        # ASCII output should not contain unicode box-drawing characters
        box_chars = set("┌┐└┘─│├┤┬┴┼╭╮╰╯►◄▲▼┄┆━┃╋")
        used_box_chars = set(output) & box_chars
        assert not used_box_chars, (
            f"ASCII mode output contains unicode chars: {used_box_chars}"
        )


