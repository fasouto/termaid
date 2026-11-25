"""Tests for kanban diagram parsing and rendering."""
from __future__ import annotations

from termaid import render
from termaid.parser.kanban import parse_kanban


class TestKanbanParser:
    def test_columns_and_cards(self):
        d = parse_kanban(
            'kanban\n'
            '    Todo\n'
            '        Write docs\n'
            '        Fix bug\n'
            '    Done\n'
            '        Ship v1\n'
        )
        assert len(d.columns) == 2
        assert d.columns[0].title == "Todo"
        assert len(d.columns[0].cards) == 2
        assert d.columns[0].cards[0].title == "Write docs"
        assert d.columns[1].title == "Done"
        assert d.columns[1].cards[0].title == "Ship v1"


class TestKanbanRendering:
    def test_render_full(self):
        output = render(
            'kanban\n'
            '    Todo\n'
            '        Design API\n'
            '        Write tests\n'
            '    In Progress\n'
            '        Build auth\n'
            '    Done\n'
            '        Setup CI\n'
        )
        assert "Todo" in output
        assert "In Progress" in output
        assert "Done" in output
        assert "╭" in output  # rounded column border


class TestKanbanBracketIds:
    def test_id_bracket_label_on_column_and_card(self):
        kb = parse_kanban(
            "kanban\n"
            "  id1[In progress]\n"
            "    docs[Create Documentation]"
        )
        assert kb.columns[0].title == "In progress"
        assert kb.columns[0].cards[0].title == "Create Documentation"

    def test_plain_titles_unchanged(self):
        kb = parse_kanban("kanban\n  Todo\n    Fix bug")
        assert kb.columns[0].title == "Todo"
        assert kb.columns[0].cards[0].title == "Fix bug"


class TestKanbanWideChars:
    def test_widest_card_not_truncated(self):
        output = render("kanban\n  Todo\n    Create Documentation\n    short")
        assert "Create Documentation" in output

    def test_cjk_card_does_not_overflow_column(self):
        from termaid.utils import display_width
        output = render(
            "kanban\n"
            "  Todo\n"
            "    这是一个非常长的中文卡片标题测试内容\n"
            "    short"
        )
        lines = output.split("\n")
        border_w = max(display_width(l) for l in lines if "╭" in l or "┌" in l)
        assert all(display_width(l) <= border_w for l in lines)


class TestKanbanBracketIdsWithMetadata:
    def test_id_bracket_label_with_trailing_metadata(self):
        kb = parse_kanban(
            "kanban\n"
            "  todo[To Do]\n"
            "    spike[Research vector DB options] @alice"
        )
        card = kb.columns[0].cards[0]
        assert card.title == "Research vector DB options @alice"


class TestKanbanCardData:
    """Mermaid reads ``@{ … }`` only at the end of a card and draws its fields, never the raw text."""

    BOARD = (
        "kanban\n"
        "  todo[Todo]\n"
        "    id8[Design grammar]@{ assigned: 'knsv', priority: 'High', ticket: MC-2036 }\n"
        "    id9[Email bob@example.com]\n"
        "    id10[Low one]@{ priority: 'Very Low' }\n"
    )

    def test_shape_data_is_read_into_fields(self):
        cards = parse_kanban(self.BOARD).columns[0].cards
        assert cards[0].title == "Design grammar"
        assert (cards[0].assigned, cards[0].priority, cards[0].ticket) == ("knsv", "High", "MC-2036")
        assert cards[1].title == "Email bob@example.com"
        assert cards[2].priority == "Very Low"

    def test_the_drawing_shows_fields_not_raw_shape_data(self):
        out = render(self.BOARD)
        assert "@{" not in out and "assigned" not in out
        assert "Email bob@example.com" in out
        assert "MC-2036" in out and "knsv" in out
        assert "┃" in out and "┆" in out
        assert max(len(line) for line in out.splitlines()) < 40

    def test_meta_lines_are_not_columns(self):
        kb = parse_kanban(
            "kanban\n"
            "  accTitle: Board\n"
            "  accDescr: Work in flight\n"
            "  accDescr {\n"
            "    Many lines\n"
            "  }\n"
            "  todo[Todo]\n"
            "    t1[Write docs]\n"
        )
        assert [c.title for c in kb.columns] == ["Todo"]

    def test_br_tags_do_not_print(self):
        out = render("kanban\n  todo[To<br/>do]\n    t1[Write<br>docs]\n")
        assert "<br" not in out and "Write docs" in out
