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
