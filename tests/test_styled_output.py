"""Tests for render_styled and --format styled-json."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from termaid import render, render_styled
from termaid.cli import _DEMO_SOURCES, main

FIXTURES_DIR = Path(__file__).parent / "fixtures"

SOURCES = {
    **{str(p.relative_to(FIXTURES_DIR)): p.read_text(encoding="utf-8") for p in sorted(FIXTURES_DIR.rglob("*.mmd"))},
    **{f"demo/{key}": source for key, (_, source) in _DEMO_SOURCES.items()},
}

WIDE_FLOWCHART = "graph LR\n  A-->B-->C-->D-->E-->F-->G-->H"


def _plain(doc) -> str:
    return "\n".join("".join(chunk["text"] for chunk in line) for line in doc["lines"])


def _styles(doc) -> set[str]:
    return {chunk["style"] for line in doc["lines"] for chunk in line}


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_plain_text_matches_render(name: str):
    source = SOURCES[name]
    assert _plain(render_styled(source)) == render(source)


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_plain_text_matches_render_with_options(name: str):
    source = SOURCES[name]
    options = {"use_ascii": True, "rounded_edges": False, "gap": 2, "padding_x": 2, "padding_y": 1}
    assert _plain(render_styled(source, **options)) == render(source, **options)


@pytest.mark.parametrize("name", sorted(SOURCES))
def test_document_shape(name: str):
    doc = render_styled(SOURCES[name])
    assert doc["version"] == 1
    for line in doc["lines"]:
        for chunk in line:
            assert set(chunk) == {"text", "style"}
            assert chunk["text"]
            assert "\x1b" not in chunk["text"]
            assert chunk["style"]
        for left, right in zip(line, line[1:]):
            assert left["style"] != right["style"]
    if doc["lines"]:
        assert doc["lines"][-1]


def test_unrenderable_input_is_an_empty_document():
    assert render_styled("graph TD") == {"version": 1, "lines": []}


def test_label_with_spaces_is_one_chunk():
    doc = render_styled("graph LR\n  A[Hello big world]")
    labels = [chunk for line in doc["lines"] for chunk in line if chunk["style"] == "label"]
    assert labels == [{"text": "Hello big world", "style": "label"}]


def test_blank_cells_carry_no_foreground_style():
    source = "sequenceDiagram\n  A->>B: hi\n  par Fetch data\n    A->>B: go\n  end"
    doc = render_styled(source)
    blanks = [chunk for line in doc["lines"] for chunk in line if not chunk["text"].strip()]
    assert blanks and all(chunk["style"] == "default" for chunk in blanks)
    titles = [chunk["text"] for line in doc["lines"] for chunk in line if chunk["text"].startswith("[par]")]
    assert titles == ["[par] Fetch data"]


def test_class_def_nodes_keep_their_class_key():
    doc = render_styled((FIXTURES_DIR / "flowcharts" / "showcase_class_shorthand.mmd").read_text())
    assert {"class:highlight", "class:error"} <= _styles(doc)


def test_inline_style_and_link_style_keys():
    styles = _styles(render_styled(
        "graph LR\n  A --> B --> C\n  style B fill:#3b82f6\n  linkStyle 1 stroke:#f00"
    ))
    assert "nodestyle:B" in styles
    assert "linkstyle:1" in styles


def test_section_keys_pass_through():
    assert any(s.startswith("section:") for s in _styles(render_styled(_DEMO_SOURCES["kanban"][1])))


def test_rich_and_styled_share_geometry():
    pytest.importorskip("rich")
    from termaid import render_rich

    options = {"gap": 2, "padding_x": 2, "padding_y": 1, "rounded_edges": False}
    for name, source in SOURCES.items():
        rich_lines = [line.rstrip() for line in render_rich(source, theme="dracula", **options).plain.split("\n")]
        assert rich_lines == _plain(render_styled(source, **options)).split("\n"), name


class TestCli:
    def _run(self, tmp_path: Path, capsys, source: str, *args: str):
        mmd = tmp_path / "d.mmd"
        mmd.write_text(source)
        code = main([str(mmd), "--format", "styled-json", *args])
        return code, capsys.readouterr()

    def test_prints_one_json_line(self, tmp_path: Path, capsys):
        code, captured = self._run(tmp_path, capsys, "graph LR\n  A --> B")
        assert code == 0
        assert captured.out.count("\n") == 1
        assert json.loads(captured.out) == render_styled("graph LR\n  A --> B")

    def test_writes_output_file(self, tmp_path: Path, capsys):
        out = tmp_path / "out.json"
        code, captured = self._run(tmp_path, capsys, "graph LR\n  A --> B", "-o", str(out))
        assert code == 0
        assert captured.out == ""
        assert json.loads(out.read_text()) == render_styled("graph LR\n  A --> B")

    def test_theme_is_ignored(self, tmp_path: Path, capsys, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        code, captured = self._run(tmp_path, capsys, "graph LR\n  A --> B", "--theme", "neon")
        assert code == 0
        assert "\x1b" not in captured.out
        assert json.loads(captured.out) == render_styled("graph LR\n  A --> B")

    def test_width_fits_like_text(self, tmp_path: Path, capsys):
        mmd = tmp_path / "d.mmd"
        mmd.write_text(WIDE_FLOWCHART)
        assert main([str(mmd), "--width", "70"]) == 0
        text = capsys.readouterr().out.rstrip("\n")

        code, captured = self._run(tmp_path, capsys, WIDE_FLOWCHART, "--width", "70")
        assert code == 0
        assert _plain(json.loads(captured.out)) == text
        assert text != render(WIDE_FLOWCHART)
        assert max(len(line) for line in text.split("\n")) <= 70

    @pytest.mark.parametrize("flag", ["--tui", "--markdown", "--claude-hook"])
    def test_incompatible_modes_are_rejected(self, tmp_path: Path, capsys, flag: str):
        code, captured = self._run(tmp_path, capsys, "graph LR\n  A --> B", flag)
        assert code == 2
        assert captured.out == ""
        assert "styled-json" in captured.err


def _style_at(text, index: int) -> list[str]:
    return [str(span.style) for span in text.spans if span.start <= index < span.end]


@pytest.mark.parametrize("label", ["日本語 X", "ผู้ใช้ X"], ids=["cjk", "thai"])
def test_rich_label_after_wide_or_marked_text_keeps_its_style(label: str):
    from termaid import render_rich

    flowchart = render_rich(f'graph LR\n  A["{label}"] --> B["end"]', theme="default")
    sequence = render_rich(f"sequenceDiagram\n  participant A as {label}\n  participant B as end\n  A->>B: hi", theme="default")
    for text in (flowchart, sequence):
        index = text.plain.index("end")
        assert _style_at(text, index) == _style_at(text, text.plain.index("X"))


def test_styled_chunks_keep_a_thai_label_whole():
    doc = render_styled('graph LR\n  A["ผู้ใช้"] --> B')
    assert any("ผู้ใช้" in chunk["text"] for line in doc["lines"] for chunk in line)
