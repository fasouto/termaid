"""Snapshot tests for all non-flowchart diagram types.

Each .mmd fixture is rendered and compared against the expected .txt output.
If expected output doesn't exist, the test generates it and marks as "needs review".
Run with --update-snapshots to regenerate all expected outputs.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from termaid import render
from tests.conftest import (
    assert_reasonable_dimensions,
    assert_valid_unicode,
    get_all_fixture_pairs,
)


_ALL_PAIRS = get_all_fixture_pairs()


class TestAllDiagramSnapshots:
    """Snapshot tests: render each fixture and compare to expected output."""

    @pytest.mark.parametrize(
        "name,input_path,expected_path",
        _ALL_PAIRS,
        ids=[p[0] for p in _ALL_PAIRS],
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

        expected_path.parent.mkdir(parents=True, exist_ok=True)

        if not update_snapshots and not expected_path.exists() and os.environ.get("CI"):
            pytest.fail(f"No snapshot for {name}. Run the tests locally and commit the file.")

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


class TestAllDiagramInvariants:
    """Property-based tests that verify rendering invariants across all diagram fixtures."""

    @pytest.mark.parametrize(
        "name,input_path,expected_path",
        _ALL_PAIRS,
        ids=[p[0] for p in _ALL_PAIRS],
    )
    def test_valid_unicode(self, name: str, input_path: Path, expected_path: Path):
        source = input_path.read_text(encoding="utf-8").strip()
        output = render(source)
        assert_valid_unicode(output)

    @pytest.mark.parametrize(
        "name,input_path,expected_path",
        _ALL_PAIRS,
        ids=[p[0] for p in _ALL_PAIRS],
    )
    def test_reasonable_dimensions(self, name: str, input_path: Path, expected_path: Path):
        source = input_path.read_text(encoding="utf-8").strip()
        output = render(source)
        assert_reasonable_dimensions(output)

    @pytest.mark.parametrize(
        "name,input_path,expected_path",
        _ALL_PAIRS,
        ids=[p[0] for p in _ALL_PAIRS],
    )
    def test_ascii_mode(self, name: str, input_path: Path, expected_path: Path):
        source = input_path.read_text(encoding="utf-8").strip()
        output = render(source, use_ascii=True)
        assert len(output) > 0
        box_chars = set("┌┐└┘─│├┤┬┴┼╭╮╰╯►◄▲▼┄┆━┃╋")
        used_box_chars = set(output) & box_chars
        assert not used_box_chars, (
            f"ASCII mode output for {name} contains unicode chars: {used_box_chars}"
        )
