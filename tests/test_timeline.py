"""Tests for timeline diagram parsing and rendering."""
from __future__ import annotations

from termaid import render
from termaid.parser.timeline import parse_timeline


class TestTimelineParser:
    def test_sections_and_events(self):
        d = parse_timeline(
            'timeline\n'
            '    title History\n'
            '    section 2023\n'
            '        January : Kickoff\n'
            '        March : Alpha\n'
            '    section 2024\n'
            '        January : v1.0\n'
        )
        assert d.title == "History"
        assert len(d.sections) == 2
        assert d.sections[0].title == "2023"
        assert len(d.sections[0].events) == 2
        assert d.sections[0].events[0].title == "January"
        assert d.sections[0].events[0].details == ["Kickoff"]

    def test_event_with_details(self):
        d = parse_timeline(
            'timeline\n'
            '    section S\n'
            '        Event : Some detail\n'
        )
        assert d.sections[0].events[0].details == ["Some detail"]


class TestTimelineRendering:
    def test_render_full(self):
        output = render(
            'timeline\n'
            '    title Releases\n'
            '    section 2024\n'
            '        March : v1.0\n'
            '        June : v2.0\n'
            '    section 2025\n'
            '        January : v3.0\n'
        )
        assert "Releases" in output
        assert "2024" in output
        assert "March" in output
        assert "v1.0" in output
        assert "●" in output  # timeline marker


class TestEvents:
    """As in Mermaid, ``:`` separates events and a line starting with ``:`` adds to the period above."""

    def _events(self, body: str) -> dict[str, list[str]]:
        d = parse_timeline("timeline\n" + body)
        return {e.title: e.details for s in d.sections for e in s.events}

    def test_a_line_starting_with_a_colon_continues_the_period_above(self):
        events = self._events("    2004 : Facebook\n         : Google\n")
        assert events == {"2004": ["Facebook", "Google"]}

    def test_colons_separate_events_and_commas_are_text(self):
        events = self._events("    2005 : YouTube, then Vimeo\n    2006 : Twitter : Tumblr\n")
        assert events == {"2005": ["YouTube, then Vimeo"], "2006": ["Twitter", "Tumblr"]}

    def test_a_colon_inside_a_word_is_text(self):
        assert self._events("    Launch : at 10:30\n") == {"Launch": ["at 10:30"]}
