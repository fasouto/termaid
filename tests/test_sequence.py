"""Tests for sequence diagram parsing and rendering."""
from __future__ import annotations

from termmaid import render
from termmaid.parser.sequence import parse_sequence_diagram


# ── Parser tests ──────────────────────────────────────────────────────────────


class TestSequenceParser:
    def test_basic_message(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n  Alice->>Bob: Hello"
        )
        assert len(d.participants) == 2
        assert d.participants[0].id == "Alice"
        assert d.participants[1].id == "Bob"
        assert len(d.events) == 1
        assert d.events[0].label == "Hello"

    def test_solid_arrow(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n  A->>B: msg"
        )
        assert d.events[0].line_type == "solid"
        assert d.events[0].arrow_type == "arrow"

    def test_dashed_arrow(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n  A-->>B: reply"
        )
        assert d.events[0].line_type == "dotted"
        assert d.events[0].arrow_type == "arrow"

    def test_solid_open(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n  A->B: msg"
        )
        assert d.events[0].line_type == "solid"
        assert d.events[0].arrow_type == "open"

    def test_dashed_open(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n  A-->B: msg"
        )
        assert d.events[0].line_type == "dotted"
        assert d.events[0].arrow_type == "open"

    def test_multiple_messages(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  Alice->>Bob: Hello\n"
            "  Bob-->>Alice: Hi\n"
            "  Alice->>Bob: Bye"
        )
        assert len(d.events) == 3

    def test_participant_declaration(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  participant A as Alice\n"
            "  participant B as Bob\n"
            "  A->>B: Hello"
        )
        assert d.participants[0].id == "A"
        assert d.participants[0].label == "Alice"
        assert d.participants[1].id == "B"
        assert d.participants[1].label == "Bob"

    def test_actor_declaration(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  actor U as User\n"
            "  U->>S: request"
        )
        assert d.participants[0].kind == "actor"
        assert d.participants[0].label == "User"

    def test_message_without_label(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n  A->>B:"
        )
        assert len(d.events) == 1

    def test_autonumber(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  autonumber\n"
            "  A->>B: msg"
        )
        assert d.autonumber is True

    def test_comments_ignored(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  %% this is a comment\n"
            "  A->>B: msg"
        )
        assert len(d.events) == 1


# ── Rendering tests ──────────────────────────────────────────────────────────


class TestSequenceRendering:
    def test_basic_renders(self):
        output = render("sequenceDiagram\n  Alice->>Bob: Hello")
        assert "Alice" in output
        assert "Bob" in output
        assert "Hello" in output

    def test_participants_in_boxes(self):
        output = render("sequenceDiagram\n  Alice->>Bob: Hi")
        assert "┌" in output or "+" in output  # box chars

    def test_solid_arrow_char(self):
        output = render("sequenceDiagram\n  A->>B: msg")
        assert "►" in output

    def test_dashed_arrow_char(self):
        output = render("sequenceDiagram\n  A-->>B: reply")
        assert "┄" in output or "◄" in output

    def test_multiple_messages_rendered(self):
        output = render(
            "sequenceDiagram\n"
            "  Alice->>Bob: Hello\n"
            "  Bob-->>Alice: Hi\n"
            "  Alice->>Bob: How are you?\n"
            "  Bob-->>Alice: Great!"
        )
        assert "Hello" in output
        assert "Hi" in output
        assert "How are you?" in output
        assert "Great!" in output

    def test_lifelines_drawn(self):
        output = render("sequenceDiagram\n  A->>B: msg")
        assert "┆" in output  # lifeline char

    def test_ascii_mode(self):
        output = render(
            "sequenceDiagram\n  A->>B: msg",
            use_ascii=True,
        )
        assert "A" in output
        assert "B" in output
        unicode_chars = set("┌┐└┘─│├┤┬┴┼╭╮╰╯►◄▲▼┄┆━┃╋")
        for ch in output:
            assert ch not in unicode_chars

    def test_participant_alias_displayed(self):
        output = render(
            "sequenceDiagram\n"
            "  participant A as Alice\n"
            "  participant B as Bob\n"
            "  A->>B: Hello"
        )
        assert "Alice" in output
        assert "Bob" in output
