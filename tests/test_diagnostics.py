"""Tests for --diagnostics-format."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from termaid.cli import main

FENCE = "`" * 3


def _boom(*args, **kwargs):
    raise RuntimeError("internal failure")


@pytest.mark.parametrize("source,message", [
    ("graph LR\n", "Input produced no renderable diagram."),
    ("%% only a comment\n", "Input produced no renderable diagram."),
    ("not a diagram\n", "Unknown diagram type 'not'. Start the diagram with its type, "
                        "such as flowchart TD, sequenceDiagram or classDiagram."),
])
def test_input_that_draws_nothing_is_render_empty(tmp_path: Path, capsys, source: str, message: str):
    path = tmp_path / "nothing.mmd"
    path.write_text(source, encoding="utf-8")
    assert main([str(path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"Error: {message}\n"
    assert main([str(path), "--diagnostics-format", "json", "--format", "styled-json"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    diagnostic = _single(captured.err)
    assert diagnostic["code"] == "render_empty"
    assert diagnostic["exit_code"] == 1


def _json_lines(err: str) -> list[dict]:
    return [json.loads(line) for line in err.splitlines()]


def _single(err: str) -> dict:
    (diagnostic,) = _json_lines(err)
    assert set(diagnostic) == {"version", "severity", "code", "message", "details", "exit_code"}
    assert diagnostic["version"] == 1
    return diagnostic


@pytest.fixture
def diagram(tmp_path: Path) -> Path:
    path = tmp_path / "d.mmd"
    path.write_text("graph LR\n  A --> B")
    return path


class TestJsonErrors:
    def test_missing_file(self, capsys):
        code = main(["--diagnostics-format", "json", "/nonexistent/file.mmd"])
        d = _single(capsys.readouterr().err)
        assert code == 1 == d["exit_code"]
        assert d["code"] == "input_missing"
        assert d["severity"] == "error"
        assert d["details"] == {"path": "/nonexistent/file.mmd"}

    def test_unreadable_file(self, tmp_path: Path, capsys):
        path = tmp_path / "bad.mmd"
        path.write_bytes(b"\xff\xfe\xff")
        code = main(["--diagnostics-format", "json", str(path)])
        d = _single(capsys.readouterr().err)
        assert code == 1
        assert d["code"] == "input_missing"

    def test_empty_input(self, tmp_path: Path, capsys):
        path = tmp_path / "empty.mmd"
        path.write_text("   \n")
        code = main(["--diagnostics-format", "json", str(path)])
        d = _single(capsys.readouterr().err)
        assert code == 1
        assert d["code"] == "input_empty"

    def test_non_positive_width(self, diagram: Path, capsys):
        code = main(["--diagnostics-format", "json", "--width", "0", str(diagram)])
        d = _single(capsys.readouterr().err)
        assert code == 2 == d["exit_code"]
        assert d["code"] == "invalid_arguments"

    def test_markdown_with_json_ingest(self, diagram: Path, capsys):
        code = main(["--diagnostics-format", "json", "--markdown", "--json", "pie", str(diagram)])
        d = _single(capsys.readouterr().err)
        assert code == 1
        assert d["code"] == "invalid_arguments"

    def test_unknown_demo(self, capsys):
        code = main(["--diagnostics-format", "json", "--demo", "nope"])
        d = _single(capsys.readouterr().err)
        assert code == 1
        assert d["code"] == "invalid_arguments"

    def test_json_conversion_failure(self, tmp_path: Path, capsys):
        path = tmp_path / "data.json"
        path.write_text("{not json")
        code = main(["--diagnostics-format", "json", "--json", "pie", str(path)])
        d = _single(capsys.readouterr().err)
        assert code == 1
        assert d["code"] == "input_conversion_failed"

    def test_missing_rich(self, diagram: Path, capsys, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.setitem(sys.modules, "rich", None)
        code = main(["--diagnostics-format", "json", "--theme", "neon", str(diagram)])
        d = _single(capsys.readouterr().err)
        assert code == 1
        assert d["code"] == "dependency_missing"
        assert d["details"] == {"dependency": "rich"}

    def test_missing_textual(self, diagram: Path, capsys, monkeypatch):
        monkeypatch.setitem(sys.modules, "textual", None)
        monkeypatch.setitem(sys.modules, "textual.app", None)
        code = main(["--diagnostics-format", "json", "--tui", str(diagram)])
        d = _single(capsys.readouterr().err)
        assert code == 1
        assert d["code"] == "dependency_missing"
        assert d["details"] == {"dependency": "textual"}

    def test_render_failure(self, diagram: Path, capsys, monkeypatch):
        import termaid.renderer.draw as draw
        monkeypatch.setattr(draw, "render_graph_canvas", _boom)
        code = main(["--diagnostics-format", "json", str(diagram)])
        d = _single(capsys.readouterr().err)
        assert code == 1
        assert d["code"] == "render_failed"
        assert "internal failure" in d["message"]

    def test_output_write_failure(self, diagram: Path, capsys):
        code = main(["--diagnostics-format", "json", str(diagram), "-o", "/nonexistent/dir/out.txt"])
        d = _single(capsys.readouterr().err)
        assert code == 1
        assert d["code"] == "output_write_failed"
        assert d["details"] == {"path": "/nonexistent/dir/out.txt"}

    def test_failed_run_does_not_touch_output_file(self, diagram: Path, tmp_path: Path, capsys, monkeypatch):
        import termaid.renderer.draw as draw
        monkeypatch.setattr(draw, "render_graph_canvas", _boom)
        out = tmp_path / "out.txt"
        assert main(["--diagnostics-format", "json", str(diagram), "-o", str(out)]) == 1
        assert not out.exists()


class TestJsonWarnings:
    def test_width_exceeded(self, tmp_path: Path, capsys):
        path = tmp_path / "wide.mmd"
        path.write_text("graph LR\n  A-->B-->C-->D-->E-->F-->G-->H")
        code = main(["--diagnostics-format", "json", "--width", "10", str(path)])
        captured = capsys.readouterr()
        d = _single(captured.err)
        assert code == 0 == d["exit_code"]
        assert d["code"] == "width_exceeded"
        assert d["severity"] == "warning"
        assert d["details"]["max_width"] == 10
        assert d["details"]["actual_width"] > 10
        assert "┌" in captured.out

    def test_markdown_block_with_nothing_to_draw(self, tmp_path: Path, capsys):
        path = tmp_path / "doc.md"
        path.write_text(f"intro\n\n{FENCE}mermaid\nnot a diagram !!\n{FENCE}\n")
        assert main(["--diagnostics-format", "json", "--markdown", str(path)]) == 0
        d = _single(capsys.readouterr().err)
        assert d["code"] == "render_empty"
        assert d["severity"] == "warning"
        assert d["details"] == {"line": 3}

    def test_markdown_render_failure_warning(self, tmp_path: Path, capsys, monkeypatch):
        import termaid.renderer.draw as draw
        monkeypatch.setattr(draw, "render_graph_canvas", _boom)
        path = tmp_path / "doc.md"
        path.write_text(f"{FENCE}mermaid\ngraph LR\n  A --> B\n{FENCE}\n")
        assert main(["--diagnostics-format", "json", "--markdown", str(path)]) == 0
        d = _single(capsys.readouterr().err)
        assert d["code"] == "render_failed"
        assert d["severity"] == "warning"


class TestArgparseErrors:
    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "termaid", *args],
            capture_output=True,
            text=True,
        )

    def test_unknown_flag_as_json(self):
        result = self._run("--diagnostics-format", "json", "--bogus")
        assert result.returncode == 2
        d = _single(result.stderr)
        assert d["code"] == "invalid_arguments"
        assert d["exit_code"] == 2
        assert "--bogus" in d["message"]

    def test_bad_choice_as_json(self):
        result = self._run("--format", "yaml", "--diagnostics-format=json")
        assert result.returncode == 2
        assert _single(result.stderr)["code"] == "invalid_arguments"

    def test_unknown_flag_as_text(self):
        result = self._run("--bogus")
        assert result.returncode == 2
        assert result.stderr.startswith("usage: termaid")
        assert "error: unrecognized arguments: --bogus" in result.stderr


class TestTextFormatUnchanged:
    def test_missing_file(self, capsys):
        assert main(["/nonexistent/file.mmd"]) == 1
        assert capsys.readouterr().err == "Error: File not found: /nonexistent/file.mmd\n"

    def test_render_failure(self, diagram: Path, capsys, monkeypatch):
        import termaid.renderer.draw as draw
        monkeypatch.setattr(draw, "render_graph_canvas", _boom)
        assert main([str(diagram)]) == 1
        assert capsys.readouterr().err == "Error rendering diagram: internal failure\n"

    def test_output_write_failure(self, diagram: Path, capsys):
        assert main([str(diagram), "-o", "/nonexistent/dir/out.txt"]) == 1
        assert capsys.readouterr().err.startswith("Error writing to /nonexistent/dir/out.txt: ")

    def test_no_input(self):
        result = subprocess.run(
            [sys.executable, "-c", "import sys; from termaid.cli import main; sys.stdin.isatty = lambda: True; sys.exit(main([]))"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert result.stderr == (
            "Error: No input provided. Pass a file or pipe input.\n"
            "Usage: termaid diagram.mmd\n"
            "       echo 'graph LR; A-->B' | termaid\n"
        )

    def test_width_warning(self, tmp_path: Path, capsys):
        path = tmp_path / "wide.mmd"
        path.write_text("graph LR\n  A-->B-->C-->D-->E-->F-->G-->H")
        assert main(["--width", "10", str(path)]) == 0
        assert capsys.readouterr().err.startswith("Warning: diagram is ")

    def test_markdown_warning(self, tmp_path: Path, capsys):
        path = tmp_path / "doc.md"
        path.write_text(f"intro\n\n{FENCE}mermaid\ngraph LR\n{FENCE}\n")
        assert main(["--markdown", str(path)]) == 0
        assert capsys.readouterr().err == "Warning: could not render the diagram at line 3: nothing to draw\n"
