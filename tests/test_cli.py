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


LONG_SEQUENCE = (
    "sequenceDiagram\n"
    "  participant Gateway\n  participant Orders\n"
    "  Gateway->>Orders: please fetch the complete order history for this customer\n"
    "  Orders-->>Gateway: the rows, or an empty list when nothing matched\n"
)


class TestCliWrapFit:
    def _render(self, tmp_path: Path, capsys, *flags: str):
        mmd = tmp_path / "seq.mmd"
        mmd.write_text(LONG_SEQUENCE)
        status = main([str(mmd), *flags])
        captured = capsys.readouterr()
        return status, captured.out, captured.err

    def test_width_wraps_labels_when_compaction_is_not_enough(self, tmp_path: Path, capsys):
        from termaid import render
        compacted = render(LONG_SEQUENCE, gap=1, padding_x=0)
        assert max(len(line) for line in compacted.splitlines()) > 60
        status, out, err = self._render(tmp_path, capsys, "--width", "60")
        assert status == 0
        assert "Warning" not in err
        lines = out.rstrip("\n").split("\n")
        assert max(len(line) for line in lines) <= 60
        words = set(LONG_SEQUENCE.replace(":", " ").replace(",", " ").split())
        assert all(word in words for line in lines for word in line.replace("┆", " ").split() if word.isalpha())

    def test_short_labels_still_wrap_when_spacing_cannot_fit(self, capsys):
        fixture = Path(__file__).parent / "fixtures/sequence/showcase_microservice_orchestration.mmd"
        assert main([str(fixture), "--width", "50", "--strict-width"]) == 0
        out = capsys.readouterr().out
        assert max(len(line) for line in out.splitlines()) <= 50
        assert "Validate" in out and "token" in out

    def test_stage_three_stops_after_one_render_for_types_that_ignore_label_width(self):
        import argparse
        from termaid import render
        from termaid.cli import _auto_fit
        source = 'pie title Languages\n  "Python" : 45\n  "Go" : 30\n  "Rust" : 25'
        args = argparse.Namespace(
            gap=4, padding_x=4, padding_y=2, ascii=False, sharp_edges=False,
            inline_edge_labels=False, no_auto_fit=False, strict_width=False, arrow_style="pointer",
            diagnostics_format="text",
        )
        calls: list[dict] = []

        def counting_render(src, **kwargs):
            calls.append(kwargs)
            return render(src, **kwargs)

        first = render(source)
        fitted = _auto_fit(first, source, args, render_fn=counting_render, target_width=10)
        assert fitted == render(source, gap=1, padding_x=0)
        assert [c["max_label_width"] for c in calls if "max_label_width" in c] == [1]

    def test_large_width_leaves_output_byte_identical(self, tmp_path: Path, capsys):
        _, plain, _ = self._render(tmp_path, capsys)
        _, fitted, _ = self._render(tmp_path, capsys, "--width", "500")
        assert fitted == plain

    def test_strict_width_exit_codes(self, tmp_path: Path, capsys):
        assert self._render(tmp_path, capsys, "--width", "60", "--strict-width")[0] == 0
        status, out, err = self._render(tmp_path, capsys, "--width", "6", "--strict-width")
        assert status == 2
        assert out == ""
        assert "Error: diagram is" in err and "target is 6" in err

    def test_strict_width_requires_width(self, tmp_path: Path, capsys):
        status, _, err = self._render(tmp_path, capsys, "--strict-width")
        assert status == 2
        assert "--width" in err

    def test_max_height(self, tmp_path: Path, capsys):
        status, out, _ = self._render(tmp_path, capsys, "--max-height", "40")
        assert status == 0 and out
        status, out, err = self._render(tmp_path, capsys, "--max-height", "3")
        assert status == 2
        assert out == ""
        assert "Error: diagram exceeds 3 output rows." in err
        assert self._render(tmp_path, capsys, "--max-height", "0")[0] == 2

    def test_width_wraps_flowchart_edge_labels(self, tmp_path: Path, capsys):
        from termaid.utils import display_width
        mmd = tmp_path / "edge.mmd"
        mmd.write_text(
            "graph LR\n"
            "  A[Start] -->|customer confirms the order and pays with a stored card| B[Charge]\n"
            "  B --> C[Ship]\n"
        )
        assert main([str(mmd), "--width", "50", "--strict-width"]) == 0
        out = capsys.readouterr().out
        assert max(display_width(line) for line in out.splitlines()) <= 50
        assert "stored card" in out

    def test_checks_apply_to_whole_markdown_output(self, tmp_path: Path, capsys):
        doc = tmp_path / "doc.md"
        doc.write_text("intro\n\n```mermaid\n" + LONG_SEQUENCE + "```\n")
        assert main([str(doc), "--markdown", "--max-height", "2"]) == 2
        assert "exceeds 2 output rows" in capsys.readouterr().err
        assert main([str(doc), "--markdown", "--width", "60", "--strict-width"]) == 0


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


def _boom(*args, **kwargs):
    raise RuntimeError("internal failure")


def _strip_ansi(text: str) -> str:
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


class TestRenderErrorPropagation:
    def test_render_raises_on_internal_error(self, monkeypatch):
        import termaid.renderer.draw as draw
        monkeypatch.setattr(draw, "render_graph_canvas", _boom)
        from termaid import render
        with pytest.raises(RuntimeError, match="internal failure"):
            render("graph LR\n  A --> B")

    def test_render_failure_exits_nonzero(self, tmp_path: Path, monkeypatch, capsys):
        import termaid.renderer.draw as draw
        monkeypatch.setattr(draw, "render_graph_canvas", _boom)
        mmd = tmp_path / "t.mmd"
        mmd.write_text("graph LR\n  A --> B")
        result = main([str(mmd)])
        captured = capsys.readouterr()
        assert result == 1
        assert "internal failure" in captured.err
        assert "Failed to render" not in captured.out

    def test_render_failure_does_not_write_output_file(self, tmp_path: Path, monkeypatch):
        import termaid.renderer.draw as draw
        monkeypatch.setattr(draw, "render_graph_canvas", _boom)
        mmd = tmp_path / "t.mmd"
        mmd.write_text("graph LR\n  A --> B")
        out = tmp_path / "out.txt"
        result = main([str(mmd), "-o", str(out)])
        assert result == 1
        assert not out.exists()


class TestShowIds:
    @pytest.mark.parametrize("prefix", [
        "",
        '%%{init: {"theme": "dark"}}%%\n',
        "%% a comment\n",
        "---\ntitle: Flow\n---\n",
    ], ids=["plain", "directive", "comment", "frontmatter"])
    def test_ids_shown_after_any_preamble(self, tmp_path: Path, prefix: str):
        mmd = tmp_path / "t.mmd"
        mmd.write_text(prefix + "graph LR\n  A[Start] --> B[End]")
        out = tmp_path / "out.txt"
        assert main([str(mmd), "--show-ids", "-o", str(out)]) == 0
        content = out.read_text()
        assert "A: Start" in content
        assert "B: End" in content
        assert "graph LR" not in content


class TestThemeOptionInteractions:
    """--theme must not silently drop -o, --show-ids, --gap, or --width."""

    @pytest.fixture(autouse=True)
    def _setup(self, monkeypatch):
        pytest.importorskip("rich")
        monkeypatch.delenv("NO_COLOR", raising=False)

    def _render_to_file(self, tmp_path: Path, source: str, extra_args: list[str], name: str = "out.txt") -> str:
        mmd = tmp_path / "t.mmd"
        mmd.write_text(source)
        out = tmp_path / name
        result = main([str(mmd), "--theme", "default", "-o", str(out), *extra_args])
        assert result == 0
        assert out.exists()
        return _strip_ansi(out.read_text())

    def test_theme_respects_output_file(self, tmp_path: Path, capsys):
        content = self._render_to_file(tmp_path, "graph LR\n  A --> B", [])
        assert "A" in content and "B" in content
        assert capsys.readouterr().out == ""

    def test_theme_respects_show_ids(self, tmp_path: Path):
        content = self._render_to_file(
            tmp_path, "graph LR\n  A[Start] --> B[End]", ["--show-ids"]
        )
        assert "A: Start" in content

    def test_theme_respects_gap(self, tmp_path: Path):
        source = "graph LR\n  A --> B --> C"
        wide = self._render_to_file(tmp_path, source, ["--gap", "8"], "wide.txt")
        narrow = self._render_to_file(tmp_path, source, ["--gap", "1"], "narrow.txt")
        def max_width(text: str) -> int:
            return max(len(line) for line in text.splitlines())
        assert max_width(narrow) < max_width(wide)

    def test_theme_respects_width(self, tmp_path: Path):
        source = "graph LR\n  A[aaaa] --> B[bbbb] --> C[cccc] --> D[dddd]"
        full = self._render_to_file(tmp_path, source, [], "full.txt")
        fitted = self._render_to_file(tmp_path, source, ["--width", "40"], "fitted.txt")
        def max_width(text: str) -> int:
            return max(len(line) for line in text.splitlines())
        assert max_width(fitted) < max_width(full)


def test_json_help_lists_all_types(capsys):
    # --help must name every --json TYPE choice; xychart was missing.
    with pytest.raises(SystemExit):
        main(["--help"])
    assert "xychart" in capsys.readouterr().out
