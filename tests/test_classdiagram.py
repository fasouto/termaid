"""Tests for class diagram parsing and rendering."""
from __future__ import annotations

from termmaid import render
from termmaid.parser.classdiagram import parse_class_diagram


# ── Parser tests ──────────────────────────────────────────────────────────────


class TestClassDiagramParser:
    def test_basic_class(self):
        d = parse_class_diagram(
            "classDiagram\n"
            "  class Animal {\n"
            "    +String name\n"
            "    +makeSound()\n"
            "  }"
        )
        assert "Animal" in d.classes
        assert len(d.classes["Animal"].members) == 2

    def test_class_attributes(self):
        d = parse_class_diagram(
            "classDiagram\n"
            "  class Foo {\n"
            "    +String bar\n"
            "    -int baz\n"
            "  }"
        )
        members = d.classes["Foo"].members
        assert any("bar" in m.name for m in members)
        assert any("baz" in m.name for m in members)

    def test_class_methods(self):
        d = parse_class_diagram(
            "classDiagram\n"
            "  class Foo {\n"
            "    +doStuff()\n"
            "    -helper(x)\n"
            "  }"
        )
        members = d.classes["Foo"].members
        assert len(members) == 2

    def test_inheritance_relationship(self):
        d = parse_class_diagram(
            "classDiagram\n"
            "  Animal <|-- Dog"
        )
        assert len(d.relationships) == 1
        r = d.relationships[0]
        assert r.source == "Animal"
        assert r.target == "Dog"

    def test_composition_relationship(self):
        d = parse_class_diagram(
            "classDiagram\n"
            "  Car *-- Engine"
        )
        assert len(d.relationships) == 1

    def test_aggregation_relationship(self):
        d = parse_class_diagram(
            "classDiagram\n"
            "  Pond o-- Duck"
        )
        assert len(d.relationships) == 1

    def test_dashed_relationship(self):
        d = parse_class_diagram(
            "classDiagram\n"
            "  A ..> B"
        )
        assert d.relationships[0].line_style == "dashed"

    def test_realization(self):
        d = parse_class_diagram(
            "classDiagram\n"
            "  Interface ..|> Impl"
        )
        assert len(d.relationships) == 1

    def test_relationship_with_label(self):
        d = parse_class_diagram(
            "classDiagram\n"
            '  A --> B : uses'
        )
        assert d.relationships[0].label == "uses"

    def test_annotation(self):
        d = parse_class_diagram(
            "classDiagram\n"
            "  class Shape {\n"
            "    <<interface>>\n"
            "    +draw()\n"
            "  }"
        )
        assert d.classes["Shape"].annotation == "interface"

    def test_colon_member(self):
        d = parse_class_diagram(
            "classDiagram\n"
            "  class Foo\n"
            "  Foo : +bar()"
        )
        assert "Foo" in d.classes
        assert len(d.classes["Foo"].members) == 1

    def test_multiple_classes(self):
        d = parse_class_diagram(
            "classDiagram\n"
            "  class A\n"
            "  class B\n"
            "  class C\n"
            "  A --> B\n"
            "  B --> C"
        )
        assert len(d.classes) == 3
        assert len(d.relationships) == 2

    def test_direction(self):
        d = parse_class_diagram(
            "classDiagram\n"
            "  direction LR\n"
            "  class A\n"
            "  class B"
        )
        assert d.direction == "LR"


# ── Rendering tests ──────────────────────────────────────────────────────────


class TestClassDiagramRendering:
    def test_basic_renders(self):
        output = render(
            "classDiagram\n"
            "  class Animal {\n"
            "    +String name\n"
            "    +makeSound()\n"
            "  }"
        )
        assert "Animal" in output
        assert "+String name" in output
        assert "+makeSound()" in output

    def test_box_borders(self):
        output = render(
            "classDiagram\n"
            "  class Foo {\n"
            "    +bar()\n"
            "  }"
        )
        assert "┌" in output  # box top-left
        assert "┤" in output or "├" in output  # divider junctions

    def test_inheritance_rendered(self):
        output = render(
            "classDiagram\n"
            "  class Animal {\n"
            "    +name\n"
            "  }\n"
            "  class Dog {\n"
            "    +breed\n"
            "  }\n"
            "  Animal <|-- Dog"
        )
        assert "Animal" in output
        assert "Dog" in output
        assert "△" in output  # inheritance marker

    def test_multiple_relationships(self):
        output = render(
            "classDiagram\n"
            "  class A\n"
            "  class B\n"
            "  class C\n"
            "  A --> B\n"
            "  B --> C"
        )
        assert "A" in output
        assert "B" in output
        assert "C" in output

    def test_ascii_mode(self):
        output = render(
            "classDiagram\n"
            "  class Foo {\n"
            "    +bar()\n"
            "  }",
            use_ascii=True,
        )
        assert "Foo" in output
        unicode_chars = set("┌┐└┘─│├┤┬┴┼╭╮╰╯►◄▲▼┄┆━┃╋")
        for ch in output:
            assert ch not in unicode_chars
