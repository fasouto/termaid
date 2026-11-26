"""How class and ER diagrams place boxes and route the lines between them."""
from __future__ import annotations

import re

import pytest

from termaid import render
from termaid.renderer.relation_layout import Link, layout

_LINE_CHARS = set("│─┼┌┐└┘├┤┬┴▲▼►◄△▽◁▷◆◇┄┆")


def _crossed_boxes(output: str) -> list[str]:
    """Rows inside a box that a line runs through, written as the box's row text."""
    grid = output.split("\n")

    def cell(r: int, c: int) -> str:
        return grid[r][c] if 0 <= r < len(grid) and 0 <= c < len(grid[r]) else " "

    crossed = []
    for r, row in enumerate(grid):
        for c, ch in enumerate(row):
            if ch != "┌":
                continue
            right = c + 1
            while cell(r, right) in "─┬┴┼":
                right += 1
            if cell(r, right) != "┐":
                continue
            bottom = r + 1
            while cell(bottom, c) in "│├┤┼":
                bottom += 1
            if cell(bottom, c) != "└":
                continue
            for inner in range(r + 1, bottom):
                if cell(inner, c) == "├":
                    continue  # a divider between sections
                text = grid[inner][c + 1:right]
                if _LINE_CHARS & set(text):
                    crossed.append(text)
    return crossed


def _arrowheads(output: str) -> int:
    return sum(output.count(ch) for ch in "▲▼►◄")


class TestSameRowLinks:
    def test_class_link_goes_around_the_box_between(self):
        out = render(
            "classDiagram\n"
            "  Shop --> Cart\n  Shop --> Product\n  Shop --> Order\n"
            "  Cart --> Order : becomes"
        )
        assert _crossed_boxes(out) == []
        assert "becomes" in out
        assert _arrowheads(out) == 4

    def test_er_link_goes_around_the_box_between(self):
        out = render(
            "erDiagram\n"
            "  A ||--o{ B : x\n  A ||--o{ C : y\n  D ||--o{ E : z\n  B ||--|{ E : w"
        )
        assert _crossed_boxes(out) == []
        assert out.count("1..*") == 1
        assert out.count("0..*") == 3


class TestLinksIntoOneBox:
    def test_class_link_keeps_its_arrowhead(self):
        out = render(
            "classDiagram\n"
            "  App --> Logger\n  App --> Db\n  Db --> Pool\n  Pool --> Logger : logs to"
        )
        assert _crossed_boxes(out) == []
        assert _arrowheads(out) == 4
        assert "logs to" in out

    def test_er_cardinalities_do_not_overprint(self):
        out = render(
            "erDiagram\n"
            "  A ||--o{ B : x\n  A ||--o{ C : y\n  C ||--o{ D : z\n  D ||--o{ B : w"
        )
        assert out.count("0..*") == 4
        assert "1..*" not in out


class TestCyclesAndSelfLinks:
    def test_links_both_ways_are_both_drawn(self):
        out = render("classDiagram\n  A --> B : x\n  B ..> A : y")
        assert "▼" in out and "▲" in out
        assert " x" in out and " y" in out

    def test_every_link_of_a_cycle_is_drawn(self):
        out = render("classDiagram\n  A --> B : ab\n  B --> C : bc\n  C --> A : ca")
        assert _arrowheads(out) == 3
        for label in ("ab", "bc", "ca"):
            assert label in out

    def test_class_related_to_itself_gets_a_loop(self):
        out = render("classDiagram\n  class Node {\n    +next Node\n  }\n  Node --> Node : next")
        assert "◄" in out
        assert out.count("next") == 2

    def test_entity_related_to_itself_gets_a_loop(self):
        out = render("erDiagram\n  EMPLOYEE ||--o{ EMPLOYEE : manages")
        assert "manages" in out
        assert "1" in out.replace("0..*", "") and "0..*" in out

    @pytest.mark.parametrize("direction", ["TB", "LR"])
    def test_self_loop_label_and_cards_in_any_direction(self, direction):
        out = render(f'classDiagram\n  direction {direction}\n  Node "1" --> "*" Node : next')
        assert re.search(r"│\s+Node\s+│", out)
        assert "next" in out and "*" in out and "1" in out


class TestNotes:
    def test_note_for_a_class_leaves_its_neighbours_alone(self):
        out = render(
            "classDiagram\n"
            "  Animal <|-- Duck\n  Animal <|-- Fish\n  Animal <|-- Zebra\n"
            '  note for Fish "lives in water"'
        )
        for name in ("Animal", "Duck", "Fish", "Zebra", "lives in water"):
            assert name in out
        assert _crossed_boxes(out) == []

    def test_free_note_does_not_push_lines_into_boxes(self):
        out = render(
            'classDiagram\n  note "Hello"\n  Animal <|-- Duck\n  Animal <|-- Fish\n  Animal : +int age'
        )
        assert _crossed_boxes(out) == []
        assert out.count("△") == 2


class TestLabels:
    def test_neighbouring_labels_stay_whole(self):
        out = render(
            "classDiagram\n"
            "  User --> Profile : has exactly one public profile\n"
            "  Admin --> Settings : manages"
        )
        assert "has exactly one public profile" in out
        assert "manages" in out

    def test_labels_fanning_out_of_one_box_stay_whole(self):
        out = render(
            "classDiagram\n"
            "  Library --> Book : lends\n"
            "  Library --> Member : registers members\n"
            "  Library --> Loan : tracks loans"
        )
        for label in ("lends", "registers members", "tracks loans"):
            assert label in out

    def test_er_labels_and_cards_stay_whole(self):
        out = render(
            "erDiagram\n"
            '  USER ||--|| PROFILE : "has exactly one public profile"\n'
            "  ADMIN ||--o{ SETTING : manages"
        )
        assert "has exactly one public profile" in out
        assert "manages" in out
        assert out.count("0..*") == 1


class TestDirections:
    def test_lr_labels_and_cards_are_whole(self):
        out = render(
            "classDiagram\n  direction LR\n"
            '  Customer "1" --> "*" Order : places\n'
            '  Order "1" *-- "1..*" LineItem : contains'
        )
        assert "places" in out and "contains" in out and "1..*" in out
        assert _crossed_boxes(out) == []

    def test_lr_fan_out_does_not_run_along_borders(self):
        out = render(
            "classDiagram\n  direction LR\n"
            '  Customer "1" --> "*" Order : places\n'
            '  Customer "1" --> "*" Address : has'
        )
        assert "││" not in out
        assert "places" in out and "has" in out

    def test_er_lr_labels_are_whole(self):
        out = render("erDiagram\n  direction LR\n  USER ||--o{ POST : writes\n  USER ||--o{ COMMENT : leaves")
        assert "writes" in out and "leaves" in out
        assert out.count("0..*") == 2

    def _column(self, out: str, name: str) -> int:
        return next(row.index(name) for row in out.split("\n") if name in row)

    def _row(self, out: str, name: str) -> int:
        return next(i for i, row in enumerate(out.split("\n")) if name in row)

    def test_rl_puts_the_source_on_the_right(self):
        out = render("classDiagram\n  direction RL\n  Customer --> Order : places")
        assert self._column(out, "Customer") > self._column(out, "Order")
        assert "◄" in out

    def test_bt_puts_the_source_at_the_bottom(self):
        out = render("classDiagram\n  direction BT\n  Customer --> Order : places")
        assert self._row(out, "Customer") > self._row(out, "Order")
        assert "▲" in out


class TestLineOrder:
    def test_lines_leaving_one_box_do_not_cross(self):
        out = render(
            "classDiagram\n  Student -- Course\n"
            "  Department --> Teacher : employs\n  Department --> Course : offers"
        )
        assert "┼" not in out


class TestAscii:
    def _marker_row(self, src: str) -> str:
        out = render(src, use_ascii=True).split("\n")
        return next(row.strip() for row in out if row.strip() and set(row.strip()) <= set("vV^A<>|"))

    def test_inheritance_and_association_markers_differ(self):
        inherit = self._marker_row("classDiagram\n  Animal <|-- Dog")
        assoc = self._marker_row("classDiagram\n  Owner <-- Dog")
        assert inherit != assoc

    def test_lines_bend_with_plus_corners(self):
        out = render("classDiagram\n  A --> B\n  A --> C", use_ascii=True)
        assert "|-" not in out and "-|" not in out
        assert out.count("v") == 2


def _box_span(out: str, name: str) -> tuple[int, int, int]:
    """(bottom border row, left column, right column) of the box whose title is ``name``."""
    grid = out.split("\n")
    r = next(i for i, row in enumerate(grid) if re.search(rf"│\s*{name}\s*│", row))
    left = grid[r].rindex("│", 0, grid[r].index(name))
    right = grid[r].index("│", grid[r].index(name))
    bottom = r
    while grid[bottom][left] != "└":
        bottom += 1
    return bottom, left, right


class TestManyLinksOnOneFace:
    @pytest.mark.parametrize("kind", ["class", "er"])
    def test_every_line_leaves_from_under_the_box(self, kind):
        if kind == "class":
            src = "classDiagram\n" + "".join(f"  A --> B{i}\n" for i in range(10))
        else:
            src = "erDiagram\n" + "".join(f"  A ||--o{{ B{i} : r\n" for i in range(10))
        out = render(src)
        bottom, left, right = _box_span(out, "A")
        below = out.split("\n")[bottom + 1]
        assert below.count("│") == 10
        assert all(left < c < right for c, ch in enumerate(below) if ch == "│"), below
        assert all(left <= c <= right for c, ch in enumerate(below) if ch != " "), below


class TestSeveralSelfLoops:
    def test_class_loops_return_on_their_own_rows_with_whole_labels(self):
        out = render("classDiagram\n  A --> A : parent\n  A --> A : child")
        assert "parent" in out and "child" in out
        rows = [i for i, row in enumerate(out.split("\n")) if "◄" in row]
        assert len(rows) == 2 and len(set(rows)) == 2

    def test_er_loops_keep_their_labels_whole(self):
        out = render("erDiagram\n  A ||--o{ A : parent\n  A ||--o{ A : child")
        assert "parent" in out and "child" in out
        assert out.count("0..*") == 2

    def test_lr_loops_all_leave_from_under_the_box(self):
        out = render("classDiagram\n  direction LR\n" + "  A --> A\n" * 4)
        bottom, left, right = _box_span(out, "A")
        grid = out.split("\n")
        assert out.count("▲") == 4
        assert grid[bottom].count("┬") == 4
        assert all(left < c < right for c, ch in enumerate(grid[bottom + 1]) if ch != " ")

    def test_lr_loop_labels_stay_whole(self):
        out = render('classDiagram\n  direction LR\n  A "1" --> "*" A : self\n  A --> A : again')
        assert "self" in out and "again" in out


def _shared_runs(links: list[Link], direction: str) -> list[tuple[int, int, int, int]]:
    """Cells where lines of two different links run the same way, so they
    read as one line; a plain crossing does not count."""
    lay = layout({n: (16, 3) for link in links for n in (link.a, link.b)}, links, 4, direction)
    seen: dict[tuple[int, int, str], int] = {}
    shared = []
    for i, route in enumerate(lay.routes):
        pts = route.points
        for (r1, c1), (r2, c2) in zip(pts, pts[1:]):
            way = "v" if c1 == c2 else "h"
            cells = ([(r, c1) for r in range(min(r1, r2), max(r1, r2) + 1)] if way == "v"
                     else [(r1, c) for c in range(min(c1, c2), max(c1, c2) + 1)])
            for r, c in cells:
                if seen.setdefault((r, c, way), i) != i:
                    shared.append((seen[(r, c, way)], i, r, c))
    return shared


class TestLinesKeepApart:
    @pytest.mark.parametrize("direction", ["LR", "RL"])
    def test_lr_lines_into_one_box_do_not_share_a_run(self, direction):
        pairs = [("A", "B"), ("A", "C"), ("A", "D"), ("B", "D"), ("C", "D")]
        assert _shared_runs([Link(a, b) for a, b in pairs], direction) == []

    def test_lr_er_fan_out_does_not_share_a_run(self):
        links = [Link("A", f"B{i}", True, "r", "1", "0..*") for i in range(6)]
        assert _shared_runs(links, "LR") == []


class TestParallelLinkLabels:
    @pytest.mark.parametrize("src", [
        "classDiagram\n  A --> B : owns\n  A --> B : uses\n  A --> B : makes",
        "classDiagram\n  A-->B:one\n  A-->B:two\n  B-->A:back\n  A-->B:four",
        "erDiagram\n  A ||--o{ B : owns\n  A ||--o{ B : uses\n  A ||--o{ B : makes",
    ])
    def test_no_label_is_written_over_a_line(self, src):
        grid = render(src).split("\n")

        def cell(r, c):
            return grid[r][c] if 0 <= r < len(grid) and c < len(grid[r]) else " "

        for label in re.findall(r":\s*(\w+)", src):
            spots = [(r, m) for r, row in enumerate(grid) for m in re.finditer(rf"\b{label}\b", row)]
            assert spots, label
            for r, m in spots:
                covered = [c for c in range(m.start(), m.end())
                           if cell(r - 1, c) in "│▲▼" and cell(r + 1, c) in "│▲▼"]
                assert covered == [], "\n".join(grid)


class TestLrLoopLabelRoom:
    def test_long_loop_label_stays_clear_of_the_next_column(self):
        out = render(
            "classDiagram\n  direction LR\n  A --> A : a rather long self label\n"
            "  A --> B\n  A --> C\n  A --> D\n  X --> C"
        )
        assert "a rather long self label " in out + " ", out
