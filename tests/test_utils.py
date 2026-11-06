"""Tests for shared utility functions."""
from __future__ import annotations

import unicodedata

import pytest

from termaid.utils import (
    _is_zero_width,
    display_width,
    iter_cells,
    max_line_width,
    truncate_to_width,
    wrap_display_text,
)


def clusters(text: str) -> list[str]:
    return [cluster for cluster, _ in iter_cells(text)]


class TestCells:
    def test_thai_marks_share_the_letter_cell(self):
        assert list(iter_cells("ผู้ใช้")) == [("ผู้", 1), ("ใ", 1), ("ช้", 1)]
        assert clusters("น้ำแข็ง") == ["น้", "ำ", "แ", "ข็", "ง"]

    def test_display_width_per_script(self):
        cases = {
            "สวัสดีครับ": 7,
            "ภาษาไทย น้ำแข็ง": 13,
            "ភាសាខ្មែរ": 8,
            "שָׁלוֹם": 4,
            "مَرْحَبًا": 5,
            unicodedata.normalize("NFD", "Tiếng Việt"): 10,
            unicodedata.normalize("NFD", "한국어"): 6,
            "日本語": 6,
            "日本ผู้": 5,
            "का": 2,
            "abc": 3,
        }
        for text, width in cases.items():
            assert display_width(text) == width, text

    def test_symbol_and_emoji_widths(self):
        assert display_width("❤") == 1
        assert display_width("★") == 1
        assert display_width("❤️") == 2
        thumb = "\U0001F44D\U0001F3FD"
        assert display_width(thumb) == 4 and len(clusters(thumb)) == 2
        family = "\U0001F468‍\U0001F469‍\U0001F467"
        assert display_width(family) == 6 and len(clusters(family)) == 3

    def test_lone_leading_mark_keeps_a_cell(self):
        assert list(iter_cells("่ab")) == [("่", 1), ("a", 1), ("b", 1)]

    def test_soft_hyphen_stays_visible(self):
        assert display_width("a­b") == 3

    def test_max_line_width_counts_marks_as_zero(self):
        assert max_line_width("ผู้ใช้\nab") == 3


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


class TestWrapDisplayText:
    def test_prefers_word_boundaries(self):
        assert wrap_display_text("alpha beta gamma", 10) == ["alpha beta", "gamma"]

    def test_hard_breaks_unspaced_text_by_display_cells(self):
        lines = wrap_display_text("abcdefgh", 4)
        assert lines == ["abcd", "efgh"]
        assert all(display_width(line) <= 4 for line in lines)

    def test_can_preserve_long_tokens(self):
        token = "A" * 30
        assert wrap_display_text(token, 10, hard_break=False) == [token]

    def test_preserves_explicit_newlines(self):
        assert wrap_display_text("first\nsecond", 20) == ["first", "second"]

    def test_rejects_non_positive_width(self):
        with pytest.raises(ValueError):
            wrap_display_text("text", 0)

    @pytest.mark.parametrize("text,width,expected", [
        ("metadata_shard[s].mutex", 20, ["metadata_shard[s]", ".mutex"]),
        ("metadata_shard[s].mutex", 12, ["metadata_", "shard[s]", ".mutex"]),
        ("metadata_shard[s].mutex", 9, ["metadata_", "shard[s]", ".mutex"]),
        ("RealClient", 8, ["Real", "Client"]),
        ("MasterService", 9, ["Master", "Service"]),
        ("HTTPServer", 6, ["HTTP", "Server"]),
        ("Client::BatchGet", 11, ["Client", "::BatchGet"]),
        ("local-copy", 8, ["local-", "copy"]),
        ("path/to/file", 10, ["path/to/", "file"]),
        ("call metadata_shard[s].mutex", 20, ["call", "metadata_shard[s]", ".mutex"]),
        ("metadata_shard[s].mutex\nnext", 20, ["metadata_shard[s]", ".mutex", "next"]),
    ])
    def test_meaningful_breakpoints(self, text, width, expected):
        assert wrap_display_text(text, width) == expected
        assert all(display_width(line) <= width for line in expected)

    @pytest.mark.parametrize("text", [
        "metadata_shard[s].mutex", "HTTPServer::GetResult", "prefix_value-name/path",
        "abcdefghijk", "123.456789", "混合text测试.mutex",
    ])
    @pytest.mark.parametrize("width", [2, 3, 5, 6, 8, 10, 12, 20, 40])
    def test_fitting_preserves_every_character_and_display_width(self, text, width):
        lines = wrap_display_text(text, width)
        assert "".join(lines) == text
        assert all(line and display_width(line) <= width for line in lines)

    def test_unbreakable_suffix_still_obeys_strict_width(self):
        assert wrap_display_text(".mutex", 5) == [".mute", "x"]
        assert wrap_display_text("metadata_shard[s].mutex", 12, hard_break=False) == ["metadata_shard[s].mutex"]

    @pytest.mark.parametrize("text,width,expected", [
        ("Read complete words here", 14, ["Read complete", "words here"]),
        ("hello,world", 8, ["hello,", "world"]),
        ("获取mutex结束", 8, ["获取", "mutex", "结束"]),
        ("RPC结束", 5, ["RPC", "结束"]),
        ("don't split words", 7, ["don't", "split", "words"]),
        ("first paragraph\n\nsecond paragraph", 12, ["first", "paragraph", "", "second", "paragraph"]),
    ])
    def test_normal_text_keeps_complete_words(self, text, width, expected):
        assert wrap_display_text(text, width) == expected

    @pytest.mark.parametrize("width", [8, 10, 12, 20])
    def test_prose_words_are_never_split_when_each_word_can_fit(self, width):
        text = "Read complete words and keep ordinary prose readable"
        lines = wrap_display_text(text, width)
        assert " ".join(lines).split() == text.split()
        assert all(display_width(line) <= width for line in lines)

    @pytest.mark.parametrize("text,width,expected", [
        ("BatchQuery 返回，T_metadata 结束", 20, ["BatchQuery 返回，", "T_metadata 结束"]),
        ("错误，T_replica_rpc 结束", 20, ["错误，", "T_replica_rpc 结束"]),
        ("返回整批 descriptor 或逐 key 错误，T_replica_rpc 结束", 28,
         ["返回整批 descriptor 或逐 key", "错误，T_replica_rpc 结束"]),
        ("alpha beta gamma", 10, ["alpha beta", "gamma"]),
    ])
    def test_clause_breaks_and_exact_fit_words(self, text, width, expected):
        assert wrap_display_text(text, width) == expected


class TestClusterBoundaries:
    def test_wrap_never_starts_a_line_with_a_mark(self):
        lines = wrap_display_text("สวัสดีครับผู้ใช้ทุกคน", 4)
        assert all(not _is_zero_width(line[0]) for line in lines)
        assert all(display_width(line) <= 4 for line in lines)
        assert "".join(lines) == "สวัสดีครับผู้ใช้ทุกคน"

    def test_truncate_keeps_whole_clusters(self):
        assert truncate_to_width("ผู้ใช้งาน", 3, ellipsis="") == "ผู้ใช้"
        assert truncate_to_width("ผู้ใช้งาน", 3) == "ผู้ใ."


class TestMaxLineWidth:
    def test_matches_per_line_display_width_on_a_thai_box(self):
        drawing = "┌────────┐\n│ ผู้ใช้ 日本 │\n└────────┘"
        assert max_line_width(drawing) == max(display_width(line) for line in drawing.split("\n"))

    def test_box_drawing_without_wide_or_zero_width_chars_skips_the_cell_walk(self, monkeypatch):
        # Fitting measures every candidate drawing; walking cells there is the slow path.
        def walk_cells(_text):
            raise AssertionError("iter_cells called on a drawing with no wide or zero-width char")

        monkeypatch.setattr("termaid.utils.iter_cells", walk_cells)
        assert max_line_width("┌──┐\n│ab│\n└──┘") == 4
