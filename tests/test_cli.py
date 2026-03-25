"""Tests for the CLI interface."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from termaid.cli import main


class TestCliMain:
    def test_file_input(self, tmp_path: Path):
        mmd = tmp_path / "test.mmd"
        mmd.write_text("graph LR\n  A --> B")
        result = main([str(mmd)])
        assert result == 0

    def test_missing_file(self):
        result = main(["/nonexistent/file.mmd"])
        assert result == 1

    def test_ascii_flag(self, tmp_path: Path):
        mmd = tmp_path / "test.mmd"
        mmd.write_text("graph LR\n  A --> B")
        result = main([str(mmd), "--ascii"])
        assert result == 0

    def test_version_flag(self):
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0

    def test_empty_file(self, tmp_path: Path):
        mmd = tmp_path / "empty.mmd"
        mmd.write_text("")
        result = main([str(mmd)])
        assert result == 1

    def test_padding_flags(self, tmp_path: Path):
        mmd = tmp_path / "test.mmd"
        mmd.write_text("graph LR\n  A --> B")
        result = main([str(mmd), "--padding-x", "6", "--padding-y", "3"])
        assert result == 0


class TestCliOutput:
    def test_output_flag(self, tmp_path: Path):
        mmd = tmp_path / "test.mmd"
        mmd.write_text("graph LR\n  A --> B")
        out_file = tmp_path / "result.txt"
        result = main([str(mmd), "-o", str(out_file)])
        assert result == 0
        content = out_file.read_text()
        assert "A" in content
        assert "B" in content

    def test_output_bad_path(self, tmp_path: Path):
        mmd = tmp_path / "test.mmd"
        mmd.write_text("graph LR\n  A --> B")
        result = main([str(mmd), "-o", "/nonexistent/dir/out.txt"])
        assert result == 1


class TestCliWidth:
    def test_width_flag_compacts(self, tmp_path: Path, capsys):
        mmd = tmp_path / "test.mmd"
        mmd.write_text("graph LR\n  A-->B-->C-->D-->E-->F-->G-->H")
        result = main([str(mmd), "--width", "70"])
        assert result == 0
        output = capsys.readouterr().out
        max_w = max(len(line) for line in output.split("\n"))
        assert max_w <= 70

    def test_width_flag_no_change_if_fits(self, tmp_path: Path, capsys):
        mmd = tmp_path / "test.mmd"
        mmd.write_text("graph LR\n  A-->B")
        result = main([str(mmd), "--width", "200"])
        assert result == 0


class TestCliNoColor:
    def test_no_color_env(self):
        from termaid.cli import _use_color
        import argparse, os
        old = os.environ.get("NO_COLOR")
        try:
            os.environ["NO_COLOR"] = "1"
            args = argparse.Namespace(theme="neon")
            assert _use_color(args) is False
        finally:
            if old is None:
                os.environ.pop("NO_COLOR", None)
            else:
                os.environ["NO_COLOR"] = old


class TestCliPipe:
    def test_pipe_input(self):
        result = subprocess.run(
            [sys.executable, "-m", "termaid"],
            input="graph LR\n  A --> B",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "A" in result.stdout
        assert "B" in result.stdout

    def test_pipe_ascii(self):
        result = subprocess.run(
            [sys.executable, "-m", "termaid", "--ascii"],
            input="graph LR\n  A --> B",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "+" in result.stdout  # ASCII box char
        assert "┌" not in result.stdout  # No unicode

    def test_pipe_chain(self):
        result = subprocess.run(
            [sys.executable, "-m", "termaid"],
            input="graph LR\n  A --> B --> C --> D",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0
        assert "A" in result.stdout
        assert "D" in result.stdout
