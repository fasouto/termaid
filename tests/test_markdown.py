"""Tests for rendering the Mermaid blocks in a Markdown document."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from termaid.cli import main
from termaid.markdown import split_markdown

FENCE = "```"


def _md(*lines: str) -> str:
    return "\n".join(lines)


class TestSplitMarkdown:
    def test_text_without_diagrams_is_one_segment(self):
        text = _md("# Title", "", "prose")
        segs = split_markdown(text)
        assert len(segs) == 1
        assert not segs[0].is_mermaid
        assert segs[0].text == text

    def test_diagram_between_text(self):
        segs = split_markdown(_md("before", FENCE + "mermaid", "graph LR", "  A --> B", FENCE, "after"))
        assert [s.is_mermaid for s in segs] == [False, True, False]
        assert segs[1].text == "graph LR\n  A --> B"
        assert segs[1].raw == _md(FENCE + "mermaid", "graph LR", "  A --> B", FENCE)
        assert segs[1].line == 2

    def test_rejoining_segments_reproduces_the_document(self):
        text = _md("a", FENCE + "mermaid", "graph LR", FENCE, "", FENCE + "mermaid", "pie", FENCE, "z")
        segs = split_markdown(text)
        assert "\n".join(s.raw if s.is_mermaid else s.text for s in segs) == text

    def test_info_string_and_case(self):
        segs = split_markdown(_md("``` Mermaid title=x", "graph LR", "```"))
        assert segs[0].is_mermaid

    def test_tilde_fence(self):
        segs = split_markdown(_md("~~~mermaid", "graph LR", "~~~"))
        assert segs[0].is_mermaid and segs[0].text == "graph LR"

    def test_closing_fence_must_match_and_be_at_least_as_long(self):
        segs = split_markdown(_md("````mermaid", "graph LR", "```", "  A --> B", "````"))
        assert segs[0].is_mermaid
        assert segs[0].text == _md("graph LR", "```", "  A --> B")

    def test_list_item_indent_is_removed_and_recorded(self):
        segs = split_markdown(_md("1. step", "   ```mermaid", "   graph TD", "     A --> B", "   ```"))
        diagram = segs[1]
        assert diagram.text == "graph TD\n  A --> B"
        assert diagram.indent == "   "

    def test_other_languages_are_text(self):
        segs = split_markdown(_md(FENCE + "python", "print(1)", FENCE))
        assert len(segs) == 1 and not segs[0].is_mermaid

    def test_mermaid_quoted_inside_a_longer_fence_is_not_a_diagram(self):
        text = _md("````markdown", FENCE + "mermaid", "graph LR", FENCE, "````")
        segs = split_markdown(text)
        assert len(segs) == 1 and segs[0].text == text

    def test_unclosed_mermaid_fence_stays_text(self):
        text = _md("intro", FENCE + "mermaid", "graph LR")
        segs = split_markdown(text)
        assert len(segs) == 1 and segs[0].text == text

    def test_crlf_code_block_does_not_hide_a_later_diagram(self):
        text = "\r\n".join([FENCE + "bash", "echo hi", FENCE, FENCE + "mermaid", "graph LR", FENCE, ""])
        segs = split_markdown(text)
        assert [s.is_mermaid for s in segs] == [False, True, False]
        assert segs[1].text == "graph LR"

    def test_backtick_in_info_string_is_not_a_fence(self):
        text = _md("```mermaid `x`", "graph LR", "```")
        assert not any(s.is_mermaid for s in split_markdown(text))


class TestCliMarkdown:
    def _run(self, tmp_path: Path, text: str, *args: str) -> int:
        md = tmp_path / "doc.md"
        md.write_text(text)
        return main([str(md), "--markdown", *args])

    def test_renders_diagrams_in_place(self, tmp_path: Path, capsys):
        rc = self._run(tmp_path, _md("# Doc", "", FENCE + "mermaid", "graph LR", "  A --> B", FENCE, "", "the end"))
        out = capsys.readouterr().out
        assert rc == 0
        assert out.startswith("# Doc\n")
        assert "┌" in out and "►" in out
        assert "mermaid" not in out
        assert out.rstrip().endswith("the end")

    def test_text_and_other_code_pass_through(self, tmp_path: Path, capsys):
        text = _md("prose", FENCE + "bash", "echo hi", FENCE)
        assert self._run(tmp_path, text) == 0
        assert capsys.readouterr().out == text + "\n"

    def test_nested_diagram_keeps_list_indent(self, tmp_path: Path, capsys):
        self._run(tmp_path, _md("1. step", "   ```mermaid", "   graph LR", "     A --> B", "   ```"), "--ascii")
        drawn = capsys.readouterr().out.split("\n")[1:]
        assert all(line.startswith("   ") for line in drawn if line)

    def test_width_accounts_for_indent(self, tmp_path: Path, capsys):
        wide = "graph LR\n  A-->B-->C-->D-->E-->F-->G-->H"
        body = "\n".join("    " + line for line in wide.split("\n"))
        self._run(tmp_path, _md("- item", "    ```mermaid", body, "    ```"), "--width", "70")
        out = capsys.readouterr().out
        assert max(len(line) for line in out.split("\n")) <= 70

    def test_unrenderable_block_is_kept_with_a_warning(self, tmp_path: Path, capsys):
        text = _md("before", "", FENCE + "mermaid", "not a diagram !!", FENCE, "", "after")
        rc = self._run(tmp_path, text)
        captured = capsys.readouterr()
        assert rc == 0
        assert "not a diagram !!" in captured.out
        assert "line 3" in captured.err

    def test_render_error_is_kept_with_a_warning(self, tmp_path: Path, capsys, monkeypatch):
        import termaid.renderer.draw as draw

        def boom(*a, **k):
            raise RuntimeError("internal failure")

        monkeypatch.setattr(draw, "render_graph_canvas", boom)
        rc = self._run(tmp_path, _md(FENCE + "mermaid", "graph LR", "  A --> B", FENCE))
        captured = capsys.readouterr()
        assert rc == 0
        assert "graph LR" in captured.out
        assert "internal failure" in captured.err

    def test_output_file(self, tmp_path: Path):
        out = tmp_path / "out.txt"
        assert self._run(tmp_path, _md("x", FENCE + "mermaid", "graph LR", "  A --> B", FENCE), "-o", str(out)) == 0
        assert "┌" in out.read_text(encoding="utf-8")

    def test_theme(self, tmp_path: Path, monkeypatch):
        pytest.importorskip("rich")
        monkeypatch.delenv("NO_COLOR", raising=False)
        out = tmp_path / "out.txt"
        text = _md("intro [not markup]", "1. step", "   ```mermaid", "   graph LR", "     A --> B", "   ```")
        assert self._run(tmp_path, text, "--theme", "neon", "-o", str(out)) == 0
        plain = re.sub(r"\x1b\[[0-9;]*m", "", out.read_text(encoding="utf-8"))
        assert "intro [not markup]" in plain
        assert "   ┌" in plain

    def test_piped_crlf_input(self):
        # Unlike a file opened in text mode, piped stdin keeps CRLF endings.
        import subprocess
        import sys

        doc = "\r\n".join(["before", FENCE + "mermaid", "graph LR", "  A --> B", FENCE, "after", ""])
        result = subprocess.run(
            [sys.executable, "-m", "termaid", "--markdown"],
            input=doc.encode(),
            capture_output=True,
        )
        out = result.stdout.decode()
        assert result.returncode == 0
        assert "┌" in out
        assert "mermaid" not in out

    @pytest.mark.parametrize("flag", [["--json", "pie"], ["--tui"]])
    def test_conflicting_flags(self, tmp_path: Path, flag: list[str], capsys):
        assert self._run(tmp_path, "x", *flag) == 2
        assert "--markdown" in capsys.readouterr().err


QUOTED = "Intro\n> A quote:\n>\n> ```mermaid\n> graph LR\n>   Q --> R\n> ```\n\nAfter\n"


def test_a_diagram_in_a_blockquote_is_found():
    diagrams = [s for s in split_markdown(QUOTED) if s.is_mermaid]
    assert len(diagrams) == 1
    assert diagrams[0].text == "graph LR\n  Q --> R"
    assert diagrams[0].indent == "> "


def test_a_diagram_in_a_blockquote_is_drawn_inside_the_quote(tmp_path, capsys):
    doc = tmp_path / "q.md"
    doc.write_text(QUOTED)
    assert main([str(doc), "--markdown"]) == 0
    out = capsys.readouterr().out
    assert "```mermaid" not in out
    drawn = [line for line in out.splitlines() if "─" in line or "│" in line]
    assert drawn and all(line.startswith("> ") for line in drawn)


def test_a_quote_that_ends_before_its_fence_closes_stays_text():
    doc = "> ```mermaid\n> graph LR\nA --> B\n```\n"
    assert not any(s.is_mermaid for s in split_markdown(doc))


def test_another_fence_in_a_blockquote_hides_its_contents():
    doc = "> ```text\n> ```mermaid\n> graph LR\n> ```\n"
    assert not any(s.is_mermaid for s in split_markdown(doc))
