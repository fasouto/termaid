"""Diagram text shown by the Textual widget and the --tui viewer is literal, never markup."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("textual")

from textual.app import App
from textual.widget import Widget

from termaid import MermaidWidget, render
from termaid.cli import main

SOURCE = 'graph LR\n  A["[bold]x[/]"] --> B["[red]hot[/red] a[b]c"]'


def _shown(widget: Widget) -> str:
    lines = widget.render_lines(widget.region.reset_offset)
    return "\n".join("".join(segment.text for segment in strip).rstrip() for strip in lines).rstrip()


def _show(app: App, widget_type: type[Widget]) -> str:
    async def run() -> str:
        async with app.run_test(size=(120, 20)) as pilot:
            await pilot.pause()
            return _shown(app.query_one(widget_type))
    return asyncio.run(run())


def test_widget_shows_brackets_literally():
    class WidgetApp(App):
        def compose(self):
            yield MermaidWidget(SOURCE)

    assert _show(WidgetApp(), MermaidWidget) == render(SOURCE).rstrip()


def test_tui_shows_brackets_literally(tmp_path: Path, monkeypatch):
    from textual.widgets import Static

    shown: list[str] = []
    monkeypatch.setattr(App, "run", lambda self: shown.append(_show(self, Static)))
    mmd = tmp_path / "t.mmd"
    mmd.write_text(SOURCE)
    assert main([str(mmd), "--tui"]) == 0
    assert shown == [render(SOURCE).rstrip()]
