"""How class and ER diagrams place boxes and route the lines between them."""
from __future__ import annotations

import re

import pytest

from termaid import render

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
        assert all(left < c < right for c, ch in enumerate(below) if ch != " "), below
