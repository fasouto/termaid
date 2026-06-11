"""Tests for state diagram parsing and rendering.

Modeled after beautiful-mermaid's parser.test.ts state diagram section.
"""
from __future__ import annotations

import pytest

from termaid import parse, render
from termaid.parser.statediagram import parse_state_diagram
from termaid.graph.model import Direction, EdgeStyle
from termaid.graph.shapes import NodeShape


# ── Parser tests ──────────────────────────────────────────────────────────────

class TestStateDiagramParser:
    """Parser tests for state diagram syntax."""

    def test_basic_transition(self):
        g = parse_state_diagram("stateDiagram-v2\n  State1 --> State2")
        assert "State1" in g.nodes
        assert "State2" in g.nodes
        assert len(g.edges) == 1
        assert g.edges[0].source == "State1"
        assert g.edges[0].target == "State2"

    def test_transition_with_label(self):
        g = parse_state_diagram("stateDiagram-v2\n  State1 --> State2 : Click")
        assert g.edges[0].label == "Click"

    def test_default_direction_is_tb(self):
        g = parse_state_diagram("stateDiagram-v2\n  A --> B")
        assert g.direction == Direction.TB

    def test_direction_override(self):
        g = parse_state_diagram("stateDiagram-v2\n  direction LR\n  A --> B")
        assert g.direction == Direction.LR

    def test_start_state(self):
        g = parse_state_diagram("stateDiagram-v2\n  [*] --> Active")
        # Should create a start node with ● label
        start_nodes = [n for n in g.nodes.values() if n.label == "●"]
        assert len(start_nodes) == 1
        assert start_nodes[0].shape == NodeShape.CIRCLE

    def test_end_state(self):
        g = parse_state_diagram("stateDiagram-v2\n  Active --> [*]")
        end_nodes = [n for n in g.nodes.values() if n.label == "◉"]
        assert len(end_nodes) == 1
        assert end_nodes[0].shape == NodeShape.CIRCLE

    def test_start_and_end(self):
        g = parse_state_diagram(
            "stateDiagram-v2\n"
            "  [*] --> Active\n"
            "  Active --> [*]"
        )
        start_nodes = [n for n in g.nodes.values() if n.label == "●"]
        end_nodes = [n for n in g.nodes.values() if n.label == "◉"]
        assert len(start_nodes) == 1
        assert len(end_nodes) == 1

    def test_state_alias(self):
        g = parse_state_diagram(
            'stateDiagram-v2\n'
            '  state "Long Name" as s1\n'
            '  s1 --> s2'
        )
        assert g.nodes["s1"].label == "Long Name"

    def test_choice_stereotype(self):
        g = parse_state_diagram(
            "stateDiagram-v2\n"
            "  state check <<choice>>\n"
            "  A --> check"
        )
        assert g.nodes["check"].shape == NodeShape.DIAMOND

    def test_fork_stereotype(self):
        g = parse_state_diagram(
            "stateDiagram-v2\n"
            "  state fork1 <<fork>>\n"
            "  A --> fork1"
        )
        assert g.nodes["fork1"].shape == NodeShape.FORK_JOIN

    def test_join_stereotype(self):
        g = parse_state_diagram(
            "stateDiagram-v2\n"
            "  state join1 <<join>>\n"
            "  join1 --> B"
        )
        assert g.nodes["join1"].shape == NodeShape.FORK_JOIN

    def test_composite_state(self):
        g = parse_state_diagram(
            "stateDiagram-v2\n"
            '  state "Parent" {\n'
            "    A --> B\n"
            "  }"
        )
        assert len(g.subgraphs) == 1
        assert "A" in g.subgraphs[0].node_ids
        assert "B" in g.subgraphs[0].node_ids

    def test_multiple_transitions(self):
        g = parse_state_diagram(
            "stateDiagram-v2\n"
            "  A --> B\n"
            "  B --> C\n"
            "  C --> A"
        )
        assert len(g.edges) == 3

    def test_states_are_rounded(self):
        """Regular states should be ROUNDED shape."""
        g = parse_state_diagram("stateDiagram-v2\n  State1 --> State2")
        assert g.nodes["State1"].shape == NodeShape.ROUNDED
        assert g.nodes["State2"].shape == NodeShape.ROUNDED

    def test_comments_stripped(self):
        g = parse_state_diagram(
            "stateDiagram-v2\n"
            "  %% this is a comment\n"
            "  A --> B"
        )
        assert len(g.edges) == 1

    def test_statediagram_v1_header(self):
        g = parse_state_diagram("stateDiagram\n  A --> B")
        assert "A" in g.nodes
        assert "B" in g.nodes

    def test_multiple_start_states(self):
        g = parse_state_diagram(
            "stateDiagram-v2\n"
            "  [*] --> A\n"
            "  [*] --> B"
        )
        start_nodes = [n for n in g.nodes.values() if n.label == "●"]
        assert len(start_nodes) == 2

    def test_multiple_end_states(self):
        g = parse_state_diagram(
            "stateDiagram-v2\n"
            "  A --> [*]\n"
            "  B --> [*]"
        )
        end_nodes = [n for n in g.nodes.values() if n.label == "◉"]
        assert len(end_nodes) == 2

    def test_nested_composite_states(self):
        g = parse_state_diagram(
            "stateDiagram-v2\n"
            '  state "Outer" {\n'
            '    state "Inner" {\n'
            "      X --> Y\n"
            "    }\n"
            "  }"
        )
        assert len(g.subgraphs) == 1
        assert len(g.subgraphs[0].children) == 1

    def test_notes_parsed(self):
        g = parse_state_diagram(
            "stateDiagram-v2\n"
            "  A --> B\n"
            '  note right of A : some note'
        )
        assert len(g.edges) == 1
        assert "A" in g.nodes
        assert len(g.notes) == 1
        assert g.notes[0].text == "some note"
        assert g.notes[0].position == "rightof"
        assert g.notes[0].target == "A"

    def test_note_left_of(self):
        g = parse_state_diagram(
            "stateDiagram-v2\n"
            "  A --> B\n"
            '  note left of B : left note'
        )
        assert len(g.notes) == 1
        assert g.notes[0].position == "leftof"
        assert g.notes[0].target == "B"

    def test_note_rendered(self):
        output = render(
            "stateDiagram-v2\n"
            "  A --> B\n"
            '  note right of A : This is a note'
        )
        assert "This is a note" in output


# ── Auto-detection tests ─────────────────────────────────────────────────────

class TestAutoDetect:
    """Test that parse() auto-detects diagram type."""

    def test_flowchart_detected(self):
        g = parse("graph LR\n  A --> B")
        assert g.direction == Direction.LR

    def test_state_diagram_detected(self):
        g = parse("stateDiagram-v2\n  A --> B")
        assert g.direction == Direction.TB  # state diagrams default to TB
        assert g.nodes["A"].shape == NodeShape.ROUNDED

    def test_flowchart_keyword_detected(self):
        g = parse("flowchart TD\n  A --> B")
        assert g.direction == Direction.TD


# ── Rendering tests ──────────────────────────────────────────────────────────

class TestStateDiagramRendering:
    """End-to-end rendering tests for state diagrams."""

    def test_basic_renders(self):
        output = render("stateDiagram-v2\n  State1 --> State2")
        assert "State1" in output
        assert "State2" in output
        assert len(output) > 0

    def test_start_end_renders(self):
        output = render(
            "stateDiagram-v2\n"
            "  [*] --> Active\n"
            "  Active --> [*]"
        )
        assert "Active" in output
        assert "●" in output, "Start state should show ●"
        assert "◉" in output, "End state should show ◉"

    def test_labeled_transition_renders(self):
        output = render(
            "stateDiagram-v2\n"
            "  direction LR\n"
            "  Idle --> Active : begin\n"
            "  Active --> Done : finish"
        )
        assert "Idle" in output
        assert "Active" in output
        assert "Done" in output
        assert "begin" in output
        assert "finish" in output

    def test_choice_renders(self):
        output = render(
            "stateDiagram-v2\n"
            "  state check <<choice>>\n"
            "  A --> check\n"
            "  check --> B\n"
            "  check --> C"
        )
        assert "A" in output
        assert "B" in output
        assert "C" in output

    def test_composite_state_renders(self):
        output = render(
            "stateDiagram-v2\n"
            '  state "Parent" {\n'
            "    A --> B\n"
            "  }"
        )
        assert "Parent" in output
        assert "A" in output
        assert "B" in output

    def test_fork_join_renders(self):
        output = render(
            "stateDiagram-v2\n"
            "  state fork1 <<fork>>\n"
            "  state join1 <<join>>\n"
            "  A --> fork1\n"
            "  fork1 --> B\n"
            "  fork1 --> C\n"
            "  B --> join1\n"
            "  C --> join1\n"
            "  join1 --> D"
        )
        for label in ["A", "B", "C", "D"]:
            assert label in output

    def test_complex_state_diagram(self):
        output = render(
            "stateDiagram-v2\n"
            "  [*] --> Idle\n"
            "  Idle --> Processing : submit\n"
            "  Processing --> Done : complete\n"
            "  Processing --> Error : fail\n"
            "  Error --> Idle : retry\n"
            "  Done --> [*]"
        )
        for label in ["Idle", "Processing", "Done", "Error"]:
            assert label in output
        assert "●" in output
        assert "◉" in output


class TestShapePreservation:
    def test_note_preserves_choice_shape(self):
        g = parse_state_diagram(
            "stateDiagram-v2\n"
            "    state if_state <<choice>>\n"
            "    note right of if_state : check\n"
            "    [*] --> if_state"
        )
        assert g.nodes["if_state"].shape == NodeShape.DIAMOND

    def test_plain_redeclaration_preserves_fork_shape(self):
        g = parse_state_diagram(
            "stateDiagram-v2\n"
            "    state f <<fork>>\n"
            "    f"
        )
        assert g.nodes["f"].shape == NodeShape.FORK_JOIN
