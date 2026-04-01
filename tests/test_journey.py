"""Tests for user journey diagram parsing and rendering."""
from __future__ import annotations

from termaid import render
from termaid.parser.journey import parse_journey


class TestJourneyParser:
    def test_sections_and_tasks(self):
        d = parse_journey(
            'journey\n'
            '    title My Day\n'
            '    section Morning\n'
            '        Wake up: 3: Me\n'
            '        Coffee: 5: Me\n'
            '    section Work\n'
            '        Code: 4: Me, Bob\n'
        )
        assert d.title == "My Day"
        assert len(d.sections) == 2
        assert d.sections[0].title == "Morning"
        assert len(d.sections[0].tasks) == 2
        assert d.sections[0].tasks[0].title == "Wake up"
        assert d.sections[0].tasks[0].score == 3
        assert d.sections[1].tasks[0].actors == ["Me", "Bob"]

    def test_score_clamping(self):
        d = parse_journey(
            'journey\n'
            '    section S\n'
            '        High: 10: A\n'
            '        Low: -5: A\n'
        )
        assert d.sections[0].tasks[0].score == 5
        assert d.sections[0].tasks[1].score == 1


class TestJourneyRendering:
    def test_render_full(self):
        output = render(
            'journey\n'
            '    title Deploy Day\n'
            '    section Prep\n'
            '        Write tests: 4: Dev\n'
            '        Code review: 3: Dev, Lead\n'
            '    section Ship\n'
            '        Deploy: 2: Dev\n'
            '        Monitor: 5: Dev, SRE\n'
        )
        assert "Deploy Day" in output
        assert "Prep" in output
        assert "Ship" in output
        assert "Write tests" in output
        assert "Deploy" in output
