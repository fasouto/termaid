"""Tests for shared utility functions."""
from __future__ import annotations

from termaid.utils import display_width, truncate_to_width


class TestTruncateToWidth:
    def test_fits_unchanged(self):
        assert truncate_to_width("hello", 10) == "hello"
        assert truncate_to_width("hello", 5) == "hello"

    def test_ascii_truncation(self):
        assert truncate_to_width("hello world", 6) == "hello."

    def test_cjk_never_exceeds_width(self):
        for width in range(1, 12):
            result = truncate_to_width("中文字符测试", width)
            assert display_width(result) <= width

    def test_cjk_truncation_keeps_whole_chars(self):
        # 3 columns: one wide char (2) + "." (1)
        assert truncate_to_width("中文字", 3) == "中."
        # 4 columns: can't fit half of the second wide char
        assert truncate_to_width("中文字", 4) == "中."

    def test_custom_ellipsis(self):
        assert truncate_to_width("hello world", 6, ellipsis="…") == "hello…"

    def test_tiny_width(self):
        assert display_width(truncate_to_width("中文", 1)) <= 1
        assert truncate_to_width("ab", 1) == "."
