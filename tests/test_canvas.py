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


class TestClusterCells:
    def test_put_text_keeps_marks_in_the_letter_cell(self):
        canvas = Canvas(6, 1)
        canvas.put_text(0, 0, "ผู้ใช้|")
        assert canvas.get(0, 0) == "ผู้"
        assert canvas.get(0, 3) == "|"

    def test_put_styled_text_keeps_marks_in_the_letter_cell(self):
        canvas = Canvas(6, 1)
        canvas.put_styled_text(0, 0, [("ผู้", "label"), ("ใช้|", "bold_label")])
        assert canvas.get(0, 2) == "ช้"
        assert canvas.get_style(0, 2) == "bold_label"
        assert canvas.get(0, 3) == "|"

    def test_wide_cluster_still_blanks_its_shadow(self):
        canvas = Canvas(4, 1)
        canvas.put_text(0, 0, "日|")
        assert (canvas.get(0, 0), canvas.get(0, 1), canvas.get(0, 2)) == ("日", "", "|")
