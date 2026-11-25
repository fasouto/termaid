"""Tests for gantt diagram parsing and rendering."""
from __future__ import annotations

from datetime import datetime

import pytest

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
        assert task_b.start == datetime(2024, 1, 10)

    def test_duration_parsing(self):
        d = parse_gantt(
            'gantt\n'
            '    section S\n'
            '        Days :t1, 2024-01-01, 30d\n'
            '        Weeks :t2, 2024-01-01, 2w\n'
        )
        assert d.sections[0].tasks[0].end == datetime(2024, 1, 31)
        assert d.sections[0].tasks[1].end == datetime(2024, 1, 15)

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


class TestGanttDateFormat:
    def test_custom_date_format_is_honored(self):
        g = parse_gantt(
            "gantt\n"
            "  dateFormat DD-MM-YYYY\n"
            "  section S\n"
            "    Task :t1, 01-02-2024, 05-02-2024"
        )
        t = g.sections[0].tasks[0]
        assert t.start == datetime(2024, 2, 1)
        assert t.end == datetime(2024, 2, 5)

    def test_default_iso_format_still_works(self):
        g = parse_gantt(
            "gantt\n"
            "  section S\n"
            "    Task :t1, 2024-01-01, 2024-01-05"
        )
        t = g.sections[0].tasks[0]
        assert t.start == datetime(2024, 1, 1)
        assert t.end == datetime(2024, 1, 5)


class TestGanttLabelWidth:
    def test_longest_label_not_truncated(self):
        output = render(
            "gantt\n"
            "  section Build\n"
            "    Implement feature :t1, 2024-01-01, 2024-01-10\n"
            "    Test :t2, 2024-01-05, 2024-01-12"
        )
        assert "Implement feature" in output

    def test_single_task_label_not_truncated(self):
        output = render(
            "gantt\n"
            "  section S\n"
            "    Design :d1, 2024-02-01, 2024-02-04"
        )
        assert "Design" in output


def _task(source: str, index: int = 0):
    return parse_gantt("gantt\n" + source).sections[0].tasks[index]


class TestGanttDurationUnits:
    def test_every_mermaid_unit(self):
        cases = {
            "406ms": datetime(2024, 1, 1, 0, 0, 0, 406000),
            "45s": datetime(2024, 1, 1, 0, 0, 45),
            "3m": datetime(2024, 1, 1, 0, 3),
            "2h": datetime(2024, 1, 1, 2, 0),
            "30d": datetime(2024, 1, 31),
            "2w": datetime(2024, 1, 15),
            "3M": datetime(2024, 4, 1),
            "1y": datetime(2025, 1, 1),
        }
        for text, end in cases.items():
            assert _task("  section S\n    T :t1, 2024-01-01, " + text).end == end, text

    def test_units_are_case_sensitive(self):
        assert _task("  section S\n    T :t1, 2024-01-01, 3m").end == datetime(2024, 1, 1, 0, 3)
        assert _task("  section S\n    T :t1, 2024-01-01, 3M").end == datetime(2024, 4, 1)
        assert _task("  section S\n    T :t1, 2024-01-01, 30D").end is None

    def test_decimal_amounts(self):
        assert _task("  section S\n    T :t1, 2024-01-01, 1.5h").end == datetime(2024, 1, 1, 1, 30)
        assert _task("  section S\n    T :t1, 2024-01-01, 1.2s").end == datetime(2024, 1, 1, 0, 0, 1, 200000)

    def test_fractional_days_round_like_dayjs(self):
        assert _task("  section S\n    T :t1, 2024-01-01, 1.5d").end == datetime(2024, 1, 3)
        assert _task("  section S\n    T :t1, 2024-01-01, 0.5w").end == datetime(2024, 1, 5)

    def test_month_and_year_clamp_to_month_length(self):
        assert _task("  section S\n    T :t1, 2024-01-31, 1M").end == datetime(2024, 2, 29)
        assert _task("  section S\n    T :t1, 2024-02-29, 1y").end == datetime(2025, 2, 28)

    def test_long_spellings_still_accepted(self):
        assert _task("  section S\n    T :t1, 2024-01-01, 10days").end == datetime(2024, 1, 11)
        assert _task("  section S\n    T :t1, 2024-01-01, 2 weeks").end == datetime(2024, 1, 15)
        assert _task("  section S\n    T :t1, 2024-01-01, 1month").end == datetime(2024, 2, 1)

    def test_zero_duration_ends_at_start(self):
        t = _task("  section S\n    T :milestone, t1, 2024-01-01, 0ms")
        assert t.end == t.start == datetime(2024, 1, 1)


class TestGanttTimeOfDay:
    def test_time_of_day_is_kept(self):
        t = _task("  dateFormat YYYY-MM-DD HH:mm\n  section S\n    T :t1, 2024-03-05 09:30, 2024-03-05 17:45")
        assert t.start == datetime(2024, 3, 5, 9, 30)
        assert t.end == datetime(2024, 3, 5, 17, 45)

    def test_milliseconds_token(self):
        t = _task("  dateFormat YYYY-MM-DD HH:mm:ss.SSS\n  section S\n    T :t1, 2024-03-05 09:30:15.250, 500ms")
        assert t.start == datetime(2024, 3, 5, 9, 30, 15, 250000)
        assert t.end == datetime(2024, 3, 5, 9, 30, 15, 750000)

    def test_unix_milliseconds_are_utc(self):
        t = _task("  dateFormat x\n  section S\n    T :t1, 1729850000410, 1729850001920")
        assert t.start == datetime(2024, 10, 25, 9, 53, 20, 410000)
        assert t.end == datetime(2024, 10, 25, 9, 53, 21, 920000)

    def test_unix_seconds_are_utc(self):
        t = _task("  dateFormat X\n  section S\n    T :t1, 1729850000, 90m")
        assert t.start == datetime(2024, 10, 25, 9, 53, 20)
        assert t.end == datetime(2024, 10, 25, 11, 23, 20)

    def test_after_resolves_with_time(self):
        b = _task("  dateFormat X\n  section S\n    A :a1, 1729850000, 1.2s\n    B :b1, after a1, 300ms", 1)
        assert b.start == datetime(2024, 10, 25, 9, 53, 21, 200000)
        assert b.end == datetime(2024, 10, 25, 9, 53, 21, 500000)

    def test_after_with_explicit_end_date(self):
        b = _task("  section S\n    A :a1, 2024-01-01, 2024-01-10\n    B :b1, after a1, 2024-01-20", 1)
        assert b.start == datetime(2024, 1, 10)
        assert b.end == datetime(2024, 1, 20)


class TestGanttAxis:
    def test_axis_format_labels_hours(self):
        output = render(
            "gantt\n"
            "  dateFormat YYYY-MM-DD HH:mm\n"
            "  axisFormat %H:%M\n"
            "  section Deploy\n"
            "    Build :b1, 2024-03-05 09:00, 2h\n"
            "    Ship :s1, after b1, 30m\n"
        )
        assert "09:00" in output
        assert "11:00" in output
        assert "Mar 05" not in output

    def test_axis_format_milliseconds_are_zero_padded(self):
        output = render(
            "gantt\n"
            "  dateFormat x\n"
            "  axisFormat %S.%L\n"
            "  tickInterval 40millisecond\n"
            "  section S\n"
            "    A :a1, 1729850000000, 1729850000240\n"
        )
        axis_labels = output.rstrip("\n").splitlines()[-1].split()
        assert axis_labels == ["20.000", "20.040", "20.080", "20.120", "20.160", "20.200", "20.240"]

    def test_tick_interval_days(self):
        output = render(
            "gantt\n"
            "  dateFormat YYYY-MM-DD\n"
            "  axisFormat %d\n"
            "  tickInterval 1day\n"
            "  section S\n"
            "    A :a1, 2024-01-01, 2024-01-04\n"
        )
        axis_labels = output.rstrip("\n").splitlines()[-1].split()
        assert axis_labels == ["01", "02", "03", "04"]

    def test_tick_interval_aligns_to_unit_multiples(self):
        output = render(
            "gantt\n"
            "  dateFormat YYYY-MM-DD HH:mm\n"
            "  axisFormat %H\n"
            "  tickInterval 6hour\n"
            "  section S\n"
            "    A :a1, 2024-01-01 03:00, 2024-01-02 03:00\n"
        )
        axis_labels = output.rstrip("\n").splitlines()[-1].split()
        assert axis_labels == ["06", "12", "18", "00"]


class TestGanttSubSecondRendering:
    SOURCE = (
        "gantt\n"
        "    dateFormat x\n"
        "    axisFormat %S.%L\n"
        "    section agent\n"
        "    plan       :done, p1, 1729850000000, 406ms\n"
        "    search     :s1, 1729850000410, 1.2s\n"
        "    fetch page :crit, f1, 1729850000420, 900ms\n"
        "    answer     :after s1, 300ms\n"
        "    done       :milestone, m1, 1729850001920, 0ms\n"
    )

    def test_zero_length_milestone_is_visible(self):
        rows = render(self.SOURCE).splitlines()
        done_row = next(r for r in rows if "done" in r)
        assert "◆" in done_row

    def test_overlapping_bars_render_in_their_rows(self):
        rows = {r.split("│")[0].strip(): r.split("│")[1] for r in render(self.SOURCE).splitlines() if "│" in r}
        search_cols = {i for i, ch in enumerate(rows["search"]) if ch == "█"}
        fetch_cols = {i for i, ch in enumerate(rows["fetch page"]) if ch == "█"}
        assert search_cols and fetch_cols
        assert search_cols & fetch_cols


class TestInputsThatOnceRaised:
    """Issue #51, M33, M36 and L6."""

    def test_month_names_in_the_date_format(self):
        out = render("gantt\n  dateFormat MMM D YYYY\n  section A\n  Design :a1, Jan 1 2024, 5d\n  Build :after a1, 10d\n")
        assert "Design" in out and "Build" in out and "█" in out

    def test_a_full_month_name(self):
        out = render("gantt\n  dateFormat MMMM D YYYY\n  axisFormat %b\n  section A\n  Design :a1, March 1 2024, 40d\n")
        assert "Mar" in out and "Apr" in out

    def test_a_format_that_names_a_field_twice_falls_back_to_the_other_forms(self):
        out = render("gantt\n  dateFormat MM/DD/MM/YYYY\n  section A\n  Design :a1, 2024-01-01, 5d\n")
        assert "Design" in out and "█" in out

    @pytest.mark.parametrize("fmt,expected", [("%-d", "5"), ("%d", "05"), ("%_d", " 5"), ("%0e", "05"), ("%-m/%-d", "1/5")])
    def test_d3_padding_flags_work_on_every_platform(self, fmt, expected):
        from datetime import datetime

        from termaid.renderer.gantt import format_time
        assert format_time(datetime(2024, 1, 5), fmt) == expected

    @pytest.mark.parametrize("task", ["Far :a1, 2024-01-01, 99999y", "Far :a1, 2024-01-01, 9999999999d"])
    def test_a_duration_that_ends_past_year_9999_does_not_raise(self, task):
        out = render(f"gantt\n  dateFormat YYYY-MM-DD\n  section A\n  Near :n1, 2024-01-01, 5d\n  {task}\n")
        assert "Near" in out

    def test_a_timestamp_past_year_9999_does_not_raise(self):
        out = render("gantt\n  dateFormat x\n  section A\n  Near :n1, 1700000000000, 5d\n  Far :f1, 999999999999999999, 1d\n")
        assert "Near" in out


def _schedule(source: str) -> dict[str, tuple[datetime | None, datetime | None]]:
    d = parse_gantt("gantt\n  dateFormat YYYY-MM-DD\n" + source)
    return {t.title: (t.start, t.end) for s in d.sections for t in s.tasks}


class TestImplicitStart:
    """A task with no start begins when the task written before it ends, as in Mermaid."""

    def test_a_task_after_an_after_task_and_across_sections(self):
        s = _schedule(
            "  section Build\n"
            "    Design :des, 2024-01-01, 5d\n"
            "    Implement :impl, after des, 5d\n"
            "    Review :3d\n"
            "  section Ship\n"
            "    Release :2d\n"
        )
        assert s["Review"] == (datetime(2024, 1, 11), datetime(2024, 1, 14))
        assert s["Release"] == (datetime(2024, 1, 14), datetime(2024, 1, 16))

    def test_every_task_gets_a_bar(self):
        out = render(
            "gantt\n  dateFormat YYYY-MM-DD\n  section Build\n    Design :des, 2024-01-01, 5d\n"
            "    Implement :impl, after des, 5d\n    Review :3d\n  section Ship\n    Release :2d\n"
        )
        rows = {line.split("│")[0].strip(): line for line in out.splitlines() if "│" in line}
        assert "█" in rows["Review"] and "█" in rows["Release"]

    def test_until_ends_at_the_start_of_a_later_task(self):
        s = _schedule(
            "  section S\n"
            "    A :a, 2024-01-01, 2d\n"
            "    Wait :until m\n"
            "    Done :milestone, m, 2024-01-10, 0d\n"
        )
        assert s["Wait"] == (datetime(2024, 1, 3), datetime(2024, 1, 10))


class TestExcludes:
    """Excluded days stretch a task's duration, as Mermaid's checkTaskDates does."""

    def test_weekends_push_later_tasks_back(self):
        s = _schedule("  excludes weekends\n  section S\n    A :a, 2024-01-05, 3d\n    B :after a, 1d\n")
        assert s["A"] == (datetime(2024, 1, 5), datetime(2024, 1, 10))
        assert s["B"] == (datetime(2024, 1, 10), datetime(2024, 1, 11))

    def test_a_listed_date_and_a_day_name(self):
        s = _schedule("  excludes 2024-01-08, tuesday\n  section S\n    A :a, 2024-01-05, 3d\n")
        assert s["A"][1] == datetime(2024, 1, 10)

    def test_weekend_friday_makes_friday_and_saturday_the_weekend(self):
        s = _schedule("  excludes weekends\n  weekend friday\n  section S\n    A :a, 2024-01-04, 2d\n")
        assert s["A"][1] == datetime(2024, 1, 8)

    def test_a_written_end_date_is_kept(self):
        s = _schedule("  excludes weekends\n  section S\n    A :a, 2024-01-05, 2024-01-08\n")
        assert s["A"][1] == datetime(2024, 1, 8)

    def test_every_day_excluded_does_not_hang(self):
        days = "monday tuesday wednesday thursday friday saturday sunday"
        s = _schedule(f"  excludes {days}\n  section S\n    A :a, 2024-01-05, 3d\n")
        assert s["A"][0] == datetime(2024, 1, 5)
