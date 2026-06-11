"""Tests for sequence diagram parsing and rendering."""
from __future__ import annotations

from termaid import render
from termaid.parser.sequence import parse_sequence_diagram
from termaid.model.sequence import ActivateEvent, Block, DestroyEvent, Message, Note


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

    def test_cross_arrow(self):
        d = parse_sequence_diagram("sequenceDiagram\n  A-xB: lost")
        assert d.events[0].line_type == "solid"
        assert d.events[0].arrow_type == "cross"

    def test_dotted_cross_arrow(self):
        d = parse_sequence_diagram("sequenceDiagram\n  A--xB: lost")
        assert d.events[0].line_type == "dotted"
        assert d.events[0].arrow_type == "cross"

    def test_async_arrow(self):
        d = parse_sequence_diagram("sequenceDiagram\n  A-)B: fire")
        assert d.events[0].line_type == "solid"
        assert d.events[0].arrow_type == "async"

    def test_dotted_async_arrow(self):
        d = parse_sequence_diagram("sequenceDiagram\n  A--)B: fire")
        assert d.events[0].line_type == "dotted"
        assert d.events[0].arrow_type == "async"

    def test_bidirectional_arrow(self):
        d = parse_sequence_diagram("sequenceDiagram\n  A<<->>B: sync")
        assert d.events[0].line_type == "solid"
        assert d.events[0].arrow_type == "bidirectional"

    def test_dotted_bidirectional_arrow(self):
        d = parse_sequence_diagram("sequenceDiagram\n  A<<-->>B: sync")
        assert d.events[0].line_type == "dotted"
        assert d.events[0].arrow_type == "bidirectional"

    def test_database_participant(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  database DB as Database\n"
            "  DB->>A: data"
        )
        assert d.participants[0].kind == "database"
        assert d.participants[0].label == "Database"

    def test_queue_participant(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n  queue Q as MessageQueue"
        )
        assert d.participants[0].kind == "queue"

    def test_boundary_participant(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n  boundary B as Boundary"
        )
        assert d.participants[0].kind == "boundary"

    def test_control_participant(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n  control C as Controller"
        )
        assert d.participants[0].kind == "control"

    def test_entity_participant(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n  entity E as Entity"
        )
        assert d.participants[0].kind == "entity"

    def test_collections_participant(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n  collections C as Items"
        )
        assert d.participants[0].kind == "collections"

    def test_note_rightof(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  A->>B: msg\n"
            "  Note right of A: hello"
        )
        from termaid.model.sequence import Note
        notes = [e for e in d.events if isinstance(e, Note)]
        assert len(notes) == 1
        assert notes[0].position == "rightof"
        assert notes[0].text == "hello"

    def test_note_leftof(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  A->>B: msg\n"
            "  Note left of B: bye"
        )
        from termaid.model.sequence import Note
        notes = [e for e in d.events if isinstance(e, Note)]
        assert len(notes) == 1
        assert notes[0].position == "leftof"

    def test_note_over_single(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  A->>B: msg\n"
            "  Note over A: thinking"
        )
        from termaid.model.sequence import Note
        notes = [e for e in d.events if isinstance(e, Note)]
        assert notes[0].position == "over"
        assert notes[0].participants == ["A"]

    def test_note_over_two_participants(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  A->>B: msg\n"
            "  Note over A,B: shared note"
        )
        from termaid.model.sequence import Note
        notes = [e for e in d.events if isinstance(e, Note)]
        assert notes[0].participants == ["A", "B"]

    def test_note_br_tag_splits(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  A->>B: msg\n"
            "  Note right of A: line1<br/>line2"
        )
        notes = [e for e in d.events if isinstance(e, Note)]
        assert notes[0].text == "line1\nline2"

    def test_note_br_case_insensitive(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  A->>B: msg\n"
            "  Note right of A: a<BR>b<br >c"
        )
        notes = [e for e in d.events if isinstance(e, Note)]
        assert notes[0].text == "a\nb\nc"

    def test_create_participant(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  create participant C as Charlie\n"
            "  A->>C: hello"
        )
        charlie = [p for p in d.participants if p.id == "C"]
        assert len(charlie) == 1
        assert charlie[0].label == "Charlie"


# ── Rendering tests ──────────────────────────────────────────────────────────


class TestSequenceRendering:
    def test_basic_renders(self):
        output = render("sequenceDiagram\n  Alice->>Bob: Hello")
        assert "Alice" in output
        assert "Bob" in output
        assert "Hello" in output

    def test_participants_in_boxes(self):
        output = render("sequenceDiagram\n  Alice->>Bob: Hi")
        assert "┌" in output, "Participant boxes should use ┌ corner"

    def test_solid_arrow_char(self):
        output = render("sequenceDiagram\n  A->>B: msg")
        assert "►" in output

    def test_dashed_arrow_char(self):
        output = render("sequenceDiagram\n  A-->>B: reply")
        assert "┄" in output, "Dashed arrow should use ┄ character"

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

    def test_note_rightof_rendered(self):
        output = render(
            "sequenceDiagram\n"
            "  A->>B: msg\n"
            "  Note right of A: thinking"
        )
        assert "thinking" in output

    def test_note_leftof_rendered(self):
        output = render(
            "sequenceDiagram\n"
            "  A->>B: msg\n"
            "  Note left of B: done"
        )
        assert "done" in output

    def test_note_over_rendered(self):
        output = render(
            "sequenceDiagram\n"
            "  A->>B: msg\n"
            "  Note over A,B: shared thought"
        )
        assert "shared thought" in output

    def test_cross_arrow_char(self):
        output = render("sequenceDiagram\n  A-xB: lost")
        assert "lost" in output
        assert "A" in output
        assert "B" in output

    def test_async_arrow_char(self):
        output = render("sequenceDiagram\n  A-)B: fire")
        assert "fire" in output
        assert "A" in output
        assert "B" in output

    def test_database_participant_rendered(self):
        output = render(
            "sequenceDiagram\n"
            "  database DB as Database\n"
            "  DB->>A: data"
        )
        assert "Database" in output

    def test_self_message(self):
        output = render(
            "sequenceDiagram\n"
            "  A->>A: think"
        )
        assert "think" in output
        assert "A" in output

    def test_autonumber_display(self):
        output = render(
            "sequenceDiagram\n"
            "  autonumber\n"
            "  A->>B: hello\n"
            "  B->>A: world"
        )
        assert "1:" in output
        assert "2:" in output


# ── Block and activation tests ────────────────────────────────────────────────


class TestSequenceBlockParser:
    def test_loop_parsed(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  Alice->>Bob: Hello\n"
            "  loop Every minute\n"
            "    Bob->>Alice: ping\n"
            "  end"
        )
        # First event is the message, second is the loop block
        blocks = [e for e in d.events if isinstance(e, Block)]
        assert len(blocks) == 1
        assert blocks[0].kind == "loop"
        assert blocks[0].label == "Every minute"
        # Loop should contain one message
        msgs = [e for e in blocks[0].events if isinstance(e, Message)]
        assert len(msgs) == 1
        assert msgs[0].source == "Bob"

    def test_alt_else_parsed(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  Alice->>Bob: Request\n"
            "  alt success\n"
            "    Bob-->>Alice: OK\n"
            "  else failure\n"
            "    Bob-->>Alice: Error\n"
            "  end"
        )
        blocks = [e for e in d.events if isinstance(e, Block)]
        assert len(blocks) == 1
        assert blocks[0].kind == "alt"
        assert blocks[0].label == "success"
        # Main block should have the OK message
        msgs = [e for e in blocks[0].events if isinstance(e, Message)]
        assert len(msgs) == 1
        assert msgs[0].label == "OK"
        # Else section
        assert len(blocks[0].sections) == 1
        assert blocks[0].sections[0].label == "failure"
        sec_msgs = [e for e in blocks[0].sections[0].events if isinstance(e, Message)]
        assert len(sec_msgs) == 1
        assert sec_msgs[0].label == "Error"

    def test_opt_parsed(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  opt Extra\n"
            "    A->>B: bonus\n"
            "  end"
        )
        blocks = [e for e in d.events if isinstance(e, Block)]
        assert len(blocks) == 1
        assert blocks[0].kind == "opt"

    def test_nested_blocks(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  loop Outer\n"
            "    A->>B: ping\n"
            "    alt check\n"
            "      B-->>A: ok\n"
            "    end\n"
            "  end"
        )
        blocks = [e for e in d.events if isinstance(e, Block)]
        assert len(blocks) == 1
        assert blocks[0].kind == "loop"
        inner_blocks = [e for e in blocks[0].events if isinstance(e, Block)]
        assert len(inner_blocks) == 1
        assert inner_blocks[0].kind == "alt"

    def test_par_and_parsed(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  par Task A\n"
            "    A->>B: req1\n"
            "  and Task B\n"
            "    A->>C: req2\n"
            "  end"
        )
        blocks = [e for e in d.events if isinstance(e, Block)]
        assert len(blocks) == 1
        assert blocks[0].kind == "par"
        assert blocks[0].label == "Task A"
        msgs = [e for e in blocks[0].events if isinstance(e, Message)]
        assert len(msgs) == 1
        assert msgs[0].target == "B"
        assert len(blocks[0].sections) == 1
        assert blocks[0].sections[0].label == "Task B"
        sec_msgs = [e for e in blocks[0].sections[0].events if isinstance(e, Message)]
        assert len(sec_msgs) == 1
        assert sec_msgs[0].target == "C"

    def test_critical_option_parsed(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  critical Establish connection\n"
            "    A->>B: connect\n"
            "  option Timeout\n"
            "    A->>A: retry\n"
            "  end"
        )
        blocks = [e for e in d.events if isinstance(e, Block)]
        assert len(blocks) == 1
        assert blocks[0].kind == "critical"
        assert blocks[0].label == "Establish connection"
        assert len(blocks[0].sections) == 1
        assert blocks[0].sections[0].label == "Timeout"

    def test_break_parsed(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  A->>B: req\n"
            "  break When error\n"
            "    B-->>A: err\n"
            "  end"
        )
        blocks = [e for e in d.events if isinstance(e, Block)]
        assert len(blocks) == 1
        assert blocks[0].kind == "break"
        assert blocks[0].label == "When error"

    def test_activate_deactivate_keywords(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  A->>B: msg\n"
            "  activate B\n"
            "  B-->>A: reply\n"
            "  deactivate B"
        )
        activations = [e for e in d.events if isinstance(e, ActivateEvent)]
        assert len(activations) == 2
        assert activations[0].participant == "B"
        assert activations[0].active is True
        assert activations[1].participant == "B"
        assert activations[1].active is False

    def test_inline_activation(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  Alice->>+Bob: Hello\n"
            "  Bob-->>-Alice: Hi"
        )
        activations = [e for e in d.events if isinstance(e, ActivateEvent)]
        assert len(activations) == 2
        # First: '+' activates the receiver (Bob)
        assert activations[0].participant == "Bob"
        assert activations[0].active is True
        # Second: '-' deactivates the sender (Bob), per Mermaid semantics
        assert activations[1].participant == "Bob"
        assert activations[1].active is False

    def test_inline_activation_stacked(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  Alice->>+John: a\n"
            "  Alice->>+John: b\n"
            "  John-->>-Alice: c\n"
            "  John-->>-Alice: d"
        )
        activations = [
            (e.participant, e.active)
            for e in d.events if isinstance(e, ActivateEvent)
        ]
        assert activations == [
            ("John", True), ("John", True), ("John", False), ("John", False),
        ]
        messages = [e for e in d.events if isinstance(e, Message)]
        assert all(m.source in ("Alice", "John") for m in messages)
        assert all(m.target in ("Alice", "John") for m in messages)


class TestSequenceDestroyAndRect:
    """Tests for destroy and rect features."""

    def test_destroy_parsed(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  Alice->>Bob: Hello\n"
            "  destroy Bob\n"
            "  Bob-->>Alice: Goodbye"
        )
        destroy_events = [e for e in d.events if isinstance(e, DestroyEvent)]
        assert len(destroy_events) == 1
        assert destroy_events[0].participant == "Bob"

    def test_destroy_rendered(self):
        output = render(
            "sequenceDiagram\n"
            "  Alice->>Bob: Hello\n"
            "  destroy Bob\n"
            "  Bob-->>Alice: Goodbye"
        )
        # X marker should appear on Bob's lifeline
        assert "╳" in output or "X" in output

    def test_rect_parsed_as_block(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  rect rgb(200,200,255)\n"
            "  Alice->>Bob: Hello\n"
            "  Bob-->>Alice: Hi\n"
            "  end"
        )
        blocks = [e for e in d.events if isinstance(e, Block)]
        assert len(blocks) == 1
        assert blocks[0].kind == "rect"

    def test_rect_rendered(self):
        output = render(
            "sequenceDiagram\n"
            "  rect rgb(200,200,255)\n"
            "  Alice->>Bob: Hello\n"
            "  Bob-->>Alice: Hi\n"
            "  end"
        )
        assert "[rect]" in output

    def test_destroy_no_warning(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  Alice->>Bob: Hello\n"
            "  destroy Bob"
        )
        assert d.warnings == []

    def test_rect_no_warning(self):
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  rect rgb(200,200,255)\n"
            "  Alice->>Bob: Hello\n"
            "  end"
        )
        assert d.warnings == []


class TestSequenceBlockRendering:
    def test_loop_frame_displayed(self):
        output = render(
            "sequenceDiagram\n"
            "  Alice->>Bob: Hello\n"
            "  loop Every minute\n"
            "    Bob->>Alice: ping\n"
            "  end"
        )
        assert "Alice" in output
        assert "Bob" in output
        assert "[loop]" in output
        assert "ping" in output

    def test_alt_else_sections_visible(self):
        output = render(
            "sequenceDiagram\n"
            "  Alice->>Bob: Request\n"
            "  alt success\n"
            "    Bob-->>Alice: OK\n"
            "  else failure\n"
            "    Bob-->>Alice: Error\n"
            "  end"
        )
        assert "[alt]" in output
        assert "OK" in output
        assert "Error" in output
        # Section divider uses dashed chars
        assert "┄" in output

    def test_activation_uses_active_char(self):
        output = render(
            "sequenceDiagram\n"
            "  A->>B: msg\n"
            "  activate B\n"
            "  B-->>A: reply\n"
            "  deactivate B"
        )
        assert "║" in output  # activated lifeline char

    def test_nested_blocks_render(self):
        output = render(
            "sequenceDiagram\n"
            "  loop Outer\n"
            "    A->>B: ping\n"
            "    alt check\n"
            "      B-->>A: ok\n"
            "    end\n"
            "  end"
        )
        assert "[loop]" in output
        assert "[alt]" in output
        assert "ping" in output
        assert "ok" in output

    def test_par_and_rendered(self):
        output = render(
            "sequenceDiagram\n"
            "  par Task A\n"
            "    A->>B: req1\n"
            "  and Task B\n"
            "    A->>C: req2\n"
            "  end"
        )
        assert "[par]" in output
        assert "req1" in output
        assert "req2" in output

    def test_critical_option_rendered(self):
        output = render(
            "sequenceDiagram\n"
            "  critical Establish connection\n"
            "    A->>B: connect\n"
            "  option Timeout\n"
            "    A->>A: retry\n"
            "  end"
        )
        assert "[critical]" in output
        assert "connect" in output
        assert "retry" in output

    def test_break_rendered(self):
        output = render(
            "sequenceDiagram\n"
            "  A->>B: req\n"
            "  break When error\n"
            "    B-->>A: err\n"
            "  end"
        )
        assert "[break]" in output
        assert "err" in output

    def test_alt_else_no_label_overlap(self):
        """Message label after else should not overlap with section label."""
        output = render(
            "sequenceDiagram\n"
            "  Alice->>Bob: Request\n"
            "  alt success\n"
            "    Bob-->>Alice: OK\n"
            "  else failure\n"
            "    Bob-->>Alice: Error\n"
            "  end"
        )
        assert "[failure]" in output
        assert "Error" in output
        # The labels should be on separate rows (no garbled overlap)
        for line in output.split("\n"):
            if "[failure]" in line:
                assert "Error" not in line, "Section label and message label overlap"

    def test_multiline_note_rendered(self):
        """Multi-line note should render as a taller box with all lines."""
        output = render(
            "sequenceDiagram\n"
            "  A->>B: msg\n"
            "  Note right of A: Line 1<br/>Line 2<br/>Line 3"
        )
        assert "Line 1" in output
        assert "Line 2" in output
        assert "Line 3" in output
        # <br/> should not appear literally
        assert "<br/>" not in output


class TestSelfMessageLayout:
    def test_next_label_does_not_overwrite_self_loop(self):
        output = render(
            "sequenceDiagram\n"
            "  A->>A: think\n"
            "  A->>B: hello"
        )
        assert "think" in output
        assert "hello" in output
        # The self-loop's return row (ends with the loop corner) must not
        # carry the next message's label
        for line in output.split("\n"):
            assert not ("hello" in line and "┘" in line)

    def test_cjk_message_label_fully_rendered(self):
        output = render(
            "sequenceDiagram\n"
            "  A->>B: 这是一个很长的中文标签测试"
        )
        assert "这是一个很长的中文标签测试" in output
