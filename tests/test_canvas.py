"""Tests for the Canvas character grid."""
from __future__ import annotations

from termaid.renderer.canvas import Canvas


class TestWideCharBounds:
    def test_put_text_wide_char_below_canvas_does_not_crash(self):
        c = Canvas(10, 3)
        c.put_text(5, 0, "中")
        assert c.to_string() == ""

    def test_put_text_wide_char_negative_col_no_corruption(self):
        c = Canvas(10, 1)
        c.put_text(0, -5, "中文字")
        # Negative columns must not leak into the row via negative indexing
        assert all(c.get(0, i) == " " for i in range(10))

    def test_put_styled_text_wide_char_below_canvas_does_not_crash(self):
        c = Canvas(10, 3)
        c.put_styled_text(5, 0, [("中", "label")])
        assert c.to_string() == ""

    def test_put_text_wide_char_in_bounds_still_works(self):
        c = Canvas(10, 1)
        c.put_text(0, 0, "中x")
        assert c.get(0, 0) == "中"
        assert c.get(0, 1) == ""  # shadow cell
        assert c.get(0, 2) == "x"
