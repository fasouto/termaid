"""Tests for gantt diagram parsing and rendering."""
from __future__ import annotations

from datetime import date

from termaid import render
from termaid.parser.gantt import parse_gantt


class TestGanttParser:
    def test_sections_and_tasks(self):
        d = parse_gantt(
            'gantt\n'
            '    title Project Plan\n'
            '    dateFormat YYYY-MM-DD\n'
            '    section Design\n'
            '        Wireframes :des1, 2024-01-01, 2024-01-14\n'
            '    section Development\n'
            '        Frontend :dev1, 2024-01-15, 2024-02-15\n'
        )
        assert d.title == "Project Plan"
        assert len(d.sections) == 2
        assert d.sections[0].title == "Design"
        assert d.sections[1].title == "Development"
        assert d.sections[0].tasks[0].title == "Wireframes"
        assert d.sections[1].tasks[0].title == "Frontend"

    def test_task_tags(self):
        d = parse_gantt(
            'gantt\n'
            '    section S\n'
            '        A :done, a1, 2024-01-01, 2024-01-10\n'
            '        B :active, b1, 2024-02-01, 2024-02-10\n'
            '        C :crit, c1, 2024-03-01, 2024-03-15\n'
            '        D :milestone, m1, 2024-04-01, 2024-04-01\n'
            '        E :done, crit, e1, 2024-05-01, 2024-05-05\n'
        )
        tasks = d.sections[0].tasks
        assert tasks[0].is_done is True
        assert tasks[1].is_active is True
        assert tasks[2].is_crit is True
        assert tasks[3].is_milestone is True
        assert tasks[4].is_done is True and tasks[4].is_crit is True

    def test_after_dependency(self):
        d = parse_gantt(
            'gantt\n'
            '    section S\n'
            '        Task A :a1, 2024-01-01, 2024-01-10\n'
            '        Task B :b1, after a1, 10d\n'
        )
        task_b = d.sections[0].tasks[1]
        assert task_b.after == "a1"
        assert task_b.start == date(2024, 1, 10)

    def test_duration_parsing(self):
        d = parse_gantt(
            'gantt\n'
            '    section S\n'
            '        Days :t1, 2024-01-01, 30d\n'
            '        Weeks :t2, 2024-01-01, 2w\n'
        )
        assert d.sections[0].tasks[0].end == date(2024, 1, 31)
        assert d.sections[0].tasks[1].end == date(2024, 1, 15)

    def test_today_marker_off(self):
        d = parse_gantt(
            'gantt\n'
            '    todayMarker off\n'
            '    section S\n'
            '        Task :t1, 2024-01-01, 2024-01-10\n'
        )
        assert d.today_marker is False


class TestGanttRendering:
    def test_render_full(self):
        output = render(
            'gantt\n'
            '    title Sprint 1\n'
            '    dateFormat YYYY-MM-DD\n'
            '    section Backend\n'
            '        API design :done, a1, 2024-01-01, 7d\n'
            '        Implementation :active, a2, after a1, 14d\n'
            '    section Frontend\n'
            '        Build UI :crit, b1, 2024-01-01, 10d\n'
        )
        assert "Sprint 1" in output
        assert "Backend" in output
        assert "Frontend" in output
        assert "API design" in output
        assert "░" in output  # done char
        assert "▓" in output  # active char
        assert "█" in output  # crit/normal char
