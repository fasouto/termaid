"""Class diagram syntax that changes what a class is called or shows."""
from __future__ import annotations

from termaid import render


class TestClassNames:
    def test_class_label_with_body(self):
        out = render('classDiagram\n  class Car["Fast car"] {\n    +drive()\n  }')
        assert "Fast car" in out
        assert "+drive()" in out

    def test_class_label_used_in_relationships(self):
        out = render('classDiagram\n  class Animal["Animal with a label"]\n  Animal --> Car')
        assert "Animal with a label" in out
        assert "Car" in out

    def test_backtick_names(self):
        out = render("classDiagram\n  `User Account` --> Order\n  `User Account` : +login()")
        assert "User Account" in out
        assert "`" not in out
        assert "+login()" in out

    def test_generic_class_and_members(self):
        out = render("classDiagram\n  class Box~T~ {\n    +List~T~ items\n    +nested() List~List~int~~\n  }")
        assert "Box<T>" in out
        assert "+List<T> items" in out
        assert "List<List<int>>" in out
        assert "~" not in out


class TestBreaksAndNamespaces:
    def test_br_in_note_and_label(self):
        out = render(
            'classDiagram\n  A --> B : first<br/>second\n  note for A "one<br>two"'
        )
        assert "<br" not in out
        assert "first second" in out
        assert "one" in out and "two" in out

    def test_namespace_is_drawn_around_its_classes(self):
        out = render(
            "classDiagram\nnamespace BaseShapes {\n  class Triangle\n  class Rectangle {\n"
            "    double width\n  }\n}"
        )
        assert "BaseShapes" in out
        assert "Triangle" in out and "Rectangle" in out
