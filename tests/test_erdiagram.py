"""Tests for ER diagram parsing and rendering."""
from __future__ import annotations

from termmaid import render
from termmaid.parser.erdiagram import parse_er_diagram


# ── Parser tests ──────────────────────────────────────────────────────────────


class TestERDiagramParser:
    def test_basic_relationship(self):
        d = parse_er_diagram(
            "erDiagram\n"
            "  CUSTOMER ||--o{ ORDER : places"
        )
        assert "CUSTOMER" in d.entities
        assert "ORDER" in d.entities
        assert len(d.relationships) == 1
        assert d.relationships[0].label == "places"

    def test_cardinality_one_to_many(self):
        d = parse_er_diagram(
            "erDiagram\n"
            "  A ||--|{ B : has"
        )
        r = d.relationships[0]
        assert r.card1 == "||"
        assert r.card2 == "|{"

    def test_cardinality_zero_to_many(self):
        d = parse_er_diagram(
            "erDiagram\n"
            "  A ||--o{ B : has"
        )
        r = d.relationships[0]
        assert r.card2 == "o{"

    def test_cardinality_zero_or_one(self):
        d = parse_er_diagram(
            "erDiagram\n"
            "  A ||--o| B : has"
        )
        r = d.relationships[0]
        assert r.card2 == "o|"

    def test_dashed_line(self):
        d = parse_er_diagram(
            "erDiagram\n"
            '  A }|..|{ B : uses'
        )
        assert d.relationships[0].line_style == "dashed"

    def test_entity_attributes(self):
        d = parse_er_diagram(
            "erDiagram\n"
            "  CUSTOMER {\n"
            "    string name\n"
            "    int age\n"
            "  }"
        )
        assert "CUSTOMER" in d.entities
        attrs = d.entities["CUSTOMER"].attributes
        assert len(attrs) == 2
        assert attrs[0].type == "string"
        assert attrs[0].name == "name"

    def test_attribute_keys(self):
        d = parse_er_diagram(
            "erDiagram\n"
            "  CUSTOMER {\n"
            "    int id PK\n"
            "    string email UK\n"
            "  }"
        )
        attrs = d.entities["CUSTOMER"].attributes
        assert "PK" in attrs[0].keys
        assert "UK" in attrs[1].keys

    def test_multiple_relationships(self):
        d = parse_er_diagram(
            "erDiagram\n"
            "  CUSTOMER ||--o{ ORDER : places\n"
            "  ORDER ||--|{ LINE-ITEM : contains"
        )
        assert len(d.relationships) == 2
        assert len(d.entities) == 3

    def test_direction(self):
        d = parse_er_diagram(
            "erDiagram\n"
            "  direction LR\n"
            "  A ||--o{ B : has"
        )
        assert d.direction == "LR"

    def test_entity_with_hyphen(self):
        d = parse_er_diagram(
            "erDiagram\n"
            "  CUSTOMER ||--|{ LINE-ITEM : has"
        )
        assert "LINE-ITEM" in d.entities


# ── Rendering tests ──────────────────────────────────────────────────────────


class TestERDiagramRendering:
    def test_basic_renders(self):
        output = render(
            "erDiagram\n"
            "  CUSTOMER ||--o{ ORDER : places"
        )
        assert "CUSTOMER" in output
        assert "ORDER" in output

    def test_relationship_label_rendered(self):
        output = render(
            "erDiagram\n"
            "  CUSTOMER ||--o{ ORDER : places"
        )
        assert "places" in output

    def test_cardinality_rendered(self):
        output = render(
            "erDiagram\n"
            "  CUSTOMER ||--o{ ORDER : places"
        )
        assert "1" in output     # || = exactly one
        assert "0..*" in output  # o{ = zero or more

    def test_attributes_rendered(self):
        output = render(
            "erDiagram\n"
            "  CUSTOMER {\n"
            "    string name\n"
            "    int age\n"
            "  }"
        )
        assert "CUSTOMER" in output
        assert "string" in output
        assert "name" in output

    def test_box_borders(self):
        output = render(
            "erDiagram\n"
            "  CUSTOMER ||--o{ ORDER : places"
        )
        assert "┌" in output
        assert "┘" in output

    def test_multiple_entities(self):
        output = render(
            "erDiagram\n"
            "  CUSTOMER ||--o{ ORDER : places\n"
            "  ORDER ||--|{ LINE-ITEM : contains"
        )
        assert "CUSTOMER" in output
        assert "ORDER" in output
        assert "LINE-ITEM" in output

    def test_ascii_mode(self):
        output = render(
            "erDiagram\n"
            "  CUSTOMER ||--o{ ORDER : places",
            use_ascii=True,
        )
        assert "CUSTOMER" in output
        assert "ORDER" in output
        unicode_chars = set("┌┐└┘─│├┤┬┴┼╭╮╰╯►◄▲▼┄┆━┃╋")
        for ch in output:
            assert ch not in unicode_chars
