"""Textual widget for embedding diagrams (optional dependency)."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


def _get_widget_class():
    """Get the MermaidWidget class, importing Textual lazily."""
    try:
        from textual.widget import Widget
        from textual.reactive import reactive
    except ImportError:
        raise ImportError(
            "The 'textual' package is required for the MermaidWidget. "
            "Install it with: pip install termaid[textual]"
        )

    class MermaidWidget(Widget):
        """A Textual widget that renders Mermaid diagrams."""

        source: reactive[str] = reactive("")

        def __init__(
            self,
            source: str = "",
            use_ascii: bool = False,
            arrow_style: str = "pointer",
            **kwargs,
        ) -> None:
            super().__init__(**kwargs)
            self.source = source
            self._use_ascii = use_ascii
            self._arrow_style = arrow_style

        def render(self) -> str:
            if not self.source:
                return ""
            from .. import render as _render
            return _render(
                self.source, use_ascii=self._use_ascii, arrow_style=self._arrow_style
            )

    return MermaidWidget
