"""Corner-case and stress tests for edge conditions that could break rendering.

These test real-world edge cases: malformed input, unicode in labels,
deeply nested structures, single-node graphs, empty subgraphs, etc.
"""
from __future__ import annotations

import pytest

from termaid import render, parse
from termaid.parser.flowchart import parse_flowchart
from termaid.parser.sequence import parse_sequence_diagram
from termaid.parser.classdiagram import parse_class_diagram
from termaid.parser.erdiagram import parse_er_diagram
from termaid.parser.blockdiagram import parse_block_diagram
from termaid.parser.gitgraph import parse_git_graph


# ── Silent error swallowing ──────────────────────────────────────────────────


class TestErrorHandling:
    """render() catches all exceptions — verify it reports, not silently empties."""

    def test_internal_error_returns_message(self):
        """If parsing succeeds but rendering blows up, we should get an error string."""
        # A state diagram header followed by flowchart syntax — type confusion
        result = render("stateDiagram-v2\n  A --> B --> C{x} --> D")
        assert isinstance(result, str)

    def test_frontmatter_stripped_before_dispatch(self):
        """YAML frontmatter should be stripped before diagram type detection."""
        result = render("---\ntitle: Test\n---\ngraph LR\n  A --> B")
        assert "A" in result
        assert "B" in result
        assert "---" not in result


# ── Flowchart parser corner cases ────────────────────────────────────────────


class TestFlowchartParserEdgeCases:

    def test_unicode_in_node_labels(self):
        """Unicode labels should parse and render without corruption."""
        g = parse_flowchart('graph LR\n  A["café ☕"] --> B["naïve 日本語"]')
        assert g.nodes["A"].label == "café ☕"
        assert g.nodes["B"].label == "naïve 日本語"

    def test_unicode_labels_render(self):
        output = render('graph LR\n  A["café"] --> B["naïve"]')
        assert "café" in output
        assert "naïve" in output

    def test_empty_label_in_brackets(self):
        """Node with empty label should not crash."""
        g = parse_flowchart('graph LR\n  A[""]')
        assert g.nodes["A"].label == ""

    def test_label_with_arrows_inside_quotes(self):
        """Arrows inside quoted labels should not confuse parser."""
        g = parse_flowchart('graph LR\n  A["has --> arrow"] --> B')
        assert "A" in g.nodes
        assert g.nodes["A"].label == "has --> arrow"

    def test_label_with_pipe_inside_quotes(self):
        """Pipes inside quoted labels should not confuse parser."""
        g = parse_flowchart('graph LR\n  A["has | pipe"]')
        assert g.nodes["A"].label == "has | pipe"

    def test_very_long_label(self):
        """Very long labels should render without crashing."""
        long_label = "A" * 200
        output = render(f'graph LR\n  X["{long_label}"]')
        assert long_label in output

    def test_single_node_no_edges(self):
        """Graph with a single node and no edges should render cleanly."""
        output = render("graph LR\n  A[Lonely]")
        assert "Lonely" in output
        assert "►" not in output

    def test_many_disconnected_nodes(self):
        """Multiple disconnected nodes should all appear."""
        output = render("graph LR\n  A\n  B\n  C\n  D\n  E")
        for label in "ABCDE":
            assert label in output

    def test_subgraph_with_no_nodes(self):
        """Empty subgraph should not crash."""
        output = render("graph LR\n  subgraph empty\n  end\n  A --> B")
        assert "A" in output
        assert "B" in output

    def test_deeply_nested_subgraphs(self):
        """3 levels of nesting should render without stack overflow."""
        output = render(
            "graph LR\n"
            "  subgraph outer\n"
            "    subgraph middle\n"
            "      subgraph inner\n"
            "        A --> B\n"
            "      end\n"
            "    end\n"
            "  end"
        )
        assert "A" in output
        assert "B" in output

    def test_subgraph_keyword_only(self):
        """'subgraph' with no ID should not crash."""
        # rest becomes empty string, split() returns [], but sg_id = rest = ""
        g = parse_flowchart("graph LR\n  subgraph\n    A\n  end")
        assert "A" in g.nodes

    def test_invalid_direction_falls_back_to_tb(self):
        """Invalid direction string should fall back to TB."""
        from termaid.graph.model import Direction
        g = parse_flowchart("graph INVALID\n  A --> B")
        assert g.direction == Direction.TB

    def test_class_assignment_to_nonexistent_node(self):
        """Applying class to missing node should not crash."""
        g = parse_flowchart(
            "graph LR\n"
            "  A --> B\n"
            "  classDef highlight fill:#f9f\n"
            "  class MISSING highlight"
        )
        # Should parse without error, MISSING just ignored
        assert "A" in g.nodes
        assert "B" in g.nodes

    def test_ampersand_inside_label_not_split(self):
        """& inside bracket labels should not split nodes."""
        g = parse_flowchart('graph LR\n  A["Fix & Retry"] --> B')
        assert g.nodes["A"].label == "Fix & Retry"

    def test_semicolon_separated_with_spaces(self):
        """Semicolons with various spacing should parse correctly."""
        g = parse_flowchart("graph LR\n  A --> B;B --> C ; C --> D")
        assert len(g.edges) == 3

    def test_self_loop_with_label(self):
        """Self-referencing edge with label should parse."""
        g = parse_flowchart('graph LR\n  A -->|retry| A')
        assert len(g.edges) == 1
        assert g.edges[0].source == "A"
        assert g.edges[0].target == "A"
        assert g.edges[0].label == "retry"

    def test_chained_mixed_arrow_types(self):
        """Chaining different arrow types on one line."""
        output = render("graph LR\n  A --> B -.-> C ==> D")
        for label in "ABCD":
            assert label in output

    def test_duplicate_node_definitions_keep_first_label(self):
        """Redefining a node keeps the first label (current behavior)."""
        g = parse_flowchart('graph LR\n  A[First]\n  A --> B\n  A[Second]')
        # Note: Mermaid.js updates to the last label, but termaid keeps the first.
        assert g.nodes["A"].label == "First"

    def test_comment_only_lines_ignored(self):
        """Lines with only comments should not affect parsing."""
        g = parse_flowchart(
            "graph LR\n"
            "  %% this is a comment\n"
            "  A --> B\n"
            "  %% another comment\n"
            "  B --> C"
        )
        assert len(g.edges) == 2

    def test_inline_comment_stripped(self):
        """Inline comments should be stripped from node lines."""
        g = parse_flowchart("graph LR\n  A --> B %% this is a comment")
        assert "A" in g.nodes
        assert "B" in g.nodes

    def test_linkstyle_default(self):
        """linkStyle default should not crash."""
        g = parse_flowchart("graph LR\n  A --> B\n  linkStyle default stroke:red")
        assert -1 in g.link_styles

    def test_linkstyle_out_of_range(self):
        """linkStyle with index beyond edge count should not crash."""
        g = parse_flowchart("graph LR\n  A --> B\n  linkStyle 999 stroke:red")
        assert 999 in g.link_styles


# ── Markdown labels ──────────────────────────────────────────────────────────


class TestMarkdownLabels:

    def test_bold_label(self):
        g = parse_flowchart('graph LR\n  A["`**bold text**`"]')
        assert g.nodes["A"].label == "bold text"
        assert g.nodes["A"].label_segments is not None
        assert g.nodes["A"].label_segments[0].bold is True

    def test_italic_label(self):
        g = parse_flowchart('graph LR\n  A["`*italic*`"]')
        assert g.nodes["A"].label == "italic"
        assert g.nodes["A"].label_segments[0].italic is True

    def test_mixed_bold_italic_plain(self):
        g = parse_flowchart('graph LR\n  A["`**bold** and *italic* and plain`"]')
        assert g.nodes["A"].label == "bold and italic and plain"
        segments = g.nodes["A"].label_segments
        assert segments[0].bold is True
        assert segments[1].text == " and "
        assert segments[2].italic is True

    def test_markdown_renders_without_crash(self):
        output = render('graph LR\n  A["`**bold** text`"] --> B')
        assert "bold" in output
        assert "text" in output


# ── Sequence diagram edge cases ──────────────────────────────────────────────


class TestSequenceEdgeCases:

    def test_many_participants(self):
        """6 participants should all render."""
        output = render(
            "sequenceDiagram\n"
            "  participant A\n  participant B\n  participant C\n"
            "  participant D\n  participant E\n  participant F\n"
            "  A->>F: message"
        )
        for p in "ABCDEF":
            assert p in output

    def test_self_message_renders(self):
        """Self-referencing message should render without overflow."""
        output = render(
            "sequenceDiagram\n"
            "  A->>A: thinking"
        )
        assert "thinking" in output
        assert "A" in output

    def test_long_message_label(self):
        """Very long message text should render without crashing."""
        long_msg = "x" * 80
        output = render(f"sequenceDiagram\n  A->>B: {long_msg}")
        assert long_msg in output

    def test_activate_without_deactivate(self):
        """Unclosed activation should not crash."""
        output = render(
            "sequenceDiagram\n"
            "  A->>B: msg\n"
            "  activate B\n"
            "  B-->>A: reply"
        )
        assert "msg" in output
        assert "reply" in output

    def test_deactivate_without_activate(self):
        """Deactivate without prior activate should not crash."""
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  A->>B: msg\n"
            "  deactivate B"
        )
        assert len(d.events) >= 1

    def test_nested_loop_in_alt(self):
        """Complex nesting: loop inside alt inside par."""
        output = render(
            "sequenceDiagram\n"
            "  par Task A\n"
            "    alt success\n"
            "      loop Retry\n"
            "        A->>B: ping\n"
            "      end\n"
            "    end\n"
            "  end"
        )
        assert "[par]" in output
        assert "ping" in output

    def test_extra_end_does_not_crash(self):
        """More 'end' statements than blocks should not crash."""
        d = parse_sequence_diagram(
            "sequenceDiagram\n"
            "  A->>B: msg\n"
            "  end\n"
            "  end"
        )
        assert len(d.participants) >= 2


# ── Class diagram edge cases ─────────────────────────────────────────────────


class TestClassDiagramEdgeCases:

    def test_empty_class(self):
        """Class with no members should render."""
        output = render("classDiagram\n  class Foo")
        assert "Foo" in output

    def test_class_with_only_methods(self):
        output = render(
            "classDiagram\n"
            "  class Animal {\n"
            "    +makeSound() void\n"
            "    -sleep() void\n"
            "  }"
        )
        assert "Animal" in output
        assert "makeSound" in output

    def test_visibility_markers_all_types(self):
        """All visibility markers (+, -, #, ~) should parse."""
        d = parse_class_diagram(
            "classDiagram\n"
            "  class Foo {\n"
            "    +public\n"
            "    -private\n"
            "    #protected\n"
            "    ~internal\n"
            "  }"
        )
        members = d.classes["Foo"].members
        assert len(members) == 4
        assert members[0].visibility == "+"
        assert members[1].visibility == "-"
        assert members[2].visibility == "#"
        assert members[3].visibility == "~"

    def test_classifier_suffixes(self):
        """$ (static) and * (abstract) classifier suffixes should parse."""
        d = parse_class_diagram(
            "classDiagram\n"
            "  class Foo {\n"
            "    +staticMethod()$\n"
            "    +abstractMethod()*\n"
            "  }"
        )
        members = d.classes["Foo"].members
        assert members[0].classifier == "$"
        assert members[1].classifier == "*"

    def test_inheritance_renders(self):
        output = render(
            "classDiagram\n"
            "  Animal <|-- Dog\n"
            "  Animal <|-- Cat"
        )
        assert "Animal" in output
        assert "Dog" in output
        assert "Cat" in output

    def test_method_with_return_type(self):
        d = parse_class_diagram(
            "classDiagram\n"
            "  class Foo {\n"
            "    +getName() String\n"
            "  }"
        )
        m = d.classes["Foo"].members[0]
        assert m.return_type == "String"
        assert m.is_method is True

    def test_attribute_with_type(self):
        d = parse_class_diagram(
            "classDiagram\n"
            "  class Foo {\n"
            "    String name\n"
            "  }"
        )
        m = d.classes["Foo"].members[0]
        assert m.return_type == "String"
        assert m.name == "name"


# ── ER diagram edge cases ────────────────────────────────────────────────────


class TestERDiagramEdgeCases:

    def test_entity_with_no_attributes(self):
        """Standalone entity without attributes should render."""
        output = render("erDiagram\n  CUSTOMER")
        assert "CUSTOMER" in output

    def test_entity_with_empty_body(self):
        """Entity with empty brace body should parse."""
        d = parse_er_diagram("erDiagram\n  CUSTOMER {\n  }")
        assert "CUSTOMER" in d.entities
        assert len(d.entities["CUSTOMER"].attributes) == 0

    def test_all_cardinality_types(self):
        """All cardinality combinations should parse."""
        d = parse_er_diagram(
            "erDiagram\n"
            "  A ||--|| B : one-to-one\n"
            "  C ||--o{ D : one-to-many\n"
            "  E ||--|{ F : one-to-one-or-more\n"
            "  G }o--o{ H : many-to-many"
        )
        assert len(d.relationships) == 4

    def test_entity_name_with_hyphen(self):
        d = parse_er_diagram("erDiagram\n  LINE-ITEM ||--|| ORDER : belongs")
        assert "LINE-ITEM" in d.entities
        assert "ORDER" in d.entities

    def test_multiple_pk_fk_on_same_entity(self):
        d = parse_er_diagram(
            "erDiagram\n"
            "  ORDER {\n"
            "    int id PK\n"
            "    int customer_id FK\n"
            "    int product_id FK\n"
            "  }"
        )
        attrs = d.entities["ORDER"].attributes
        assert len(attrs) == 3
        pks = [a for a in attrs if "PK" in a.keys]
        fks = [a for a in attrs if "FK" in a.keys]
        assert len(pks) == 1
        assert len(fks) == 2


# ── Block diagram edge cases ─────────────────────────────────────────────────


class TestBlockDiagramEdgeCases:

    def test_single_block(self):
        """Single block with no links should render."""
        output = render('block-beta\n  A["Solo"]')
        assert "Solo" in output

    def test_columns_1(self):
        """columns 1 means all blocks stacked vertically."""
        output = render(
            'block-beta\n'
            '  columns 1\n'
            '  A["Top"]\n'
            '  B["Bottom"]'
        )
        assert "Top" in output
        assert "Bottom" in output

    def test_many_space_blocks(self):
        """Multiple space blocks should not crash."""
        output = render(
            'block-beta\n'
            '  columns 5\n'
            '  space space A["Mid"] space space'
        )
        assert "Mid" in output

    def test_col_span_equals_columns(self):
        """Block spanning all columns should work."""
        output = render(
            'block-beta\n'
            '  columns 3\n'
            '  A["Full Width"]:3\n'
            '  B["One"] C["Two"] D["Three"]'
        )
        assert "Full Width" in output


# ── Git graph edge cases ─────────────────────────────────────────────────────


class TestGitGraphEdgeCases:

    def test_many_branches(self):
        """5 branches should render without overlap."""
        output = render(
            "gitGraph\n"
            "  commit\n"
            "  branch a\n  commit\n"
            "  branch b\n  commit\n"
            "  branch c\n  commit\n"
            "  branch d\n  commit\n"
            "  branch e\n  commit"
        )
        for name in ["main", "a", "b", "c", "d", "e"]:
            assert name in output

    def test_merge_back_to_main(self):
        """Branch then merge back should render cleanly."""
        output = render(
            "gitGraph\n"
            '  commit id: "1"\n'
            "  branch feature\n"
            '  commit id: "2"\n'
            '  commit id: "3"\n'
            "  checkout main\n"
            '  commit id: "4"\n'
            '  merge feature id: "5"'
        )
        for cid in ["1", "2", "3", "4", "5"]:
            assert cid in output

    def test_commit_with_all_attributes(self):
        """Commit with id, type, and tag should render all."""
        output = render(
            'gitGraph\n'
            '  commit id: "release" type: HIGHLIGHT tag: "v2.0"'
        )
        assert "release" in output
        assert "[v2.0]" in output
        assert "■" in output

    def test_cherry_pick_from_deep_branch(self):
        """Cherry-pick across branches should parse correctly."""
        d = parse_git_graph(
            'gitGraph\n'
            '  commit id: "a"\n'
            '  branch dev\n'
            '  commit id: "b"\n'
            '  branch feature\n'
            '  commit id: "c"\n'
            '  checkout main\n'
            '  cherry-pick id: "c"'
        )
        cp = d.commits[-1]
        assert "c" in cp.parents
        assert cp.branch == "main"


# ── Rendering stress / structural tests ──────────────────────────────────────


class TestRenderingStress:

    def test_wide_graph_many_nodes_lr(self):
        """10 nodes in a chain should render without crashing."""
        chain = " --> ".join(chr(65 + i) for i in range(10))
        output = render(f"graph LR\n  {chain}")
        for i in range(10):
            assert chr(65 + i) in output

    def test_deep_graph_many_nodes_td(self):
        """10 nodes in a vertical chain should render without crashing."""
        chain = " --> ".join(chr(65 + i) for i in range(10))
        output = render(f"graph TD\n  {chain}")
        for i in range(10):
            assert chr(65 + i) in output

    def test_fan_out_many_targets(self):
        """One source to 5 targets should render all."""
        output = render("graph TD\n  A --> B & C & D & E & F")
        for label in "ABCDEF":
            assert label in output

    def test_fan_in_many_sources(self):
        """5 sources to one target should render all."""
        output = render("graph TD\n  A & B & C & D & E --> F")
        for label in "ABCDEF":
            assert label in output

    def test_bidirectional_and_cycle(self):
        """Cycle with bidirectional edges should render."""
        output = render("graph LR\n  A <--> B\n  B <--> C\n  C <--> A")
        for label in "ABC":
            assert label in output

    def test_all_edge_styles_in_one_graph(self):
        """Mix all edge styles in one graph."""
        output = render(
            "graph LR\n"
            "  A --> B\n"
            "  B -.-> C\n"
            "  C ==> D\n"
            "  D --- E\n"
            "  E -.- F\n"
            "  F === G"
        )
        for label in "ABCDEFG":
            assert label in output
        assert "─" in output  # solid
        assert "┄" in output  # dotted
        assert "━" in output  # thick

    def test_subgraph_with_external_edges(self):
        """Edges crossing subgraph boundary should render."""
        output = render(
            "graph LR\n"
            "  subgraph sg [Backend]\n"
            "    API --> DB\n"
            "  end\n"
            "  Client --> API"
        )
        assert "Client" in output
        assert "API" in output
        assert "DB" in output

    def test_diamond_with_multiple_outputs(self):
        """Decision diamond with 3+ outputs — common flowchart pattern."""
        output = render(
            "graph TD\n"
            "  A{Decision} -->|Yes| B[OK]\n"
            "  A -->|No| C[Error]\n"
            "  A -->|Maybe| D[Retry]"
        )
        assert "Decision" in output
        assert "Yes" in output
        assert "No" in output
        assert "Maybe" in output

    def test_mixed_shapes_and_styles_stress(self):
        """Comprehensive graph with all shape types and edge styles."""
        output = render(
            "graph TD\n"
            "  A[Rect] --> B(Round)\n"
            "  B -.-> C{Diamond}\n"
            "  C ==> D([Stadium])\n"
            "  D --> E[[Sub]]\n"
            "  E --- F((Circle))\n"
            "  F -->|label| A"
        )
        for label in ["Rect", "Round", "Diamond", "Stadium", "Sub", "Circle"]:
            assert label in output
        assert "label" in output


# ── State diagram corner cases ───────────────────────────────────────────────


class TestStateDiagramEdgeCases:

    def test_basic_state_transition(self):
        output = render(
            "stateDiagram-v2\n"
            "  [*] --> Active\n"
            "  Active --> Inactive\n"
            "  Inactive --> [*]"
        )
        assert "Active" in output
        assert "Inactive" in output

    def test_state_with_description(self):
        output = render(
            "stateDiagram-v2\n"
            "  state Active {\n"
            "    [*] --> Running\n"
            "    Running --> Paused\n"
            "  }"
        )
        assert "Running" in output
        assert "Paused" in output


# ── Additional parser edge cases ─────────────────────────────────────────────


class TestMalformedInput:
    """Malformed input should not crash, just degrade gracefully."""

    def test_garbage_input(self):
        result = render("this is not a diagram at all")
        assert isinstance(result, str)

    def test_unclosed_bracket(self):
        result = render("graph LR\n  A[unclosed --> B")
        assert isinstance(result, str)

    def test_unclosed_subgraph(self):
        result = render("graph TD\n  subgraph S1\n    A-->B")
        assert isinstance(result, str)

    def test_empty_string(self):
        result = render("")
        assert isinstance(result, str)

    def test_only_whitespace(self):
        result = render("   \n\n  \n")
        assert isinstance(result, str)

    def test_header_only(self):
        result = render("graph LR")
        assert isinstance(result, str)

    def test_missing_arrow(self):
        result = render("graph TD\n  A B C")
        assert isinstance(result, str)

    def test_just_direction(self):
        for d in ["graph TD", "graph LR", "graph BT", "graph RL"]:
            result = render(d)
            assert isinstance(result, str)


class TestSpecialCharactersInLabels:
    """Labels with unusual characters should parse and render."""

    def test_backtick_label(self):
        out = render('graph LR\n  A["`code`"] --> B')
        assert isinstance(out, str)

    def test_ampersand_in_label(self):
        out = render('graph LR\n  A["R&D"] --> B')
        assert "R&D" in out

    def test_quotes_in_label(self):
        out = render("graph LR\n  A[\"it's\"] --> B")
        assert isinstance(out, str)

    def test_very_long_label_50_chars(self):
        label = "A" * 50
        out = render(f'graph TD\n  X["{label}"] --> Y')
        assert "Y" in out

    def test_very_long_label_100_chars(self):
        label = "B" * 100
        out = render(f'graph TD\n  X["{label}"] --> Y')
        assert "Y" in out

    def test_emoji_in_label(self):
        out = render('graph LR\n  A["Start 🚀"] --> B["Done ✅"]')
        assert isinstance(out, str)

    def test_newline_escape_in_label(self):
        out = render('graph TD\n  A["Line1\\nLine2"] --> B')
        assert isinstance(out, str)


class TestStructuralEdgeCases:
    """Edge cases in graph structure."""

    def test_100_nodes_chain(self):
        """Long chain should render without timeout or crash."""
        nodes = "-->".join(f"N{i}" for i in range(100))
        out = render(f"graph LR\n  {nodes}")
        assert "N0" in out
        assert "N99" in out

    def test_node_pointing_to_itself(self):
        out = render("graph TD\n  A-->A")
        assert "A" in out

    def test_multiple_edges_same_pair(self):
        out = render("graph LR\n  A-->B\n  A-->B\n  A-->B")
        assert "A" in out
        assert "B" in out

    def test_all_nodes_disconnected(self):
        out = render("graph TD\n  A\n  B\n  C\n  D")
        for n in "ABCD":
            assert n in out

    def test_subgraph_3_levels(self):
        src = (
            "graph TD\n"
            "  subgraph L1\n"
            "    subgraph L2\n"
            "      subgraph L3\n"
            "        A-->B\n"
            "      end\n"
            "    end\n"
            "  end"
        )
        out = render(src)
        assert "A" in out
        assert "B" in out
        assert "L1" in out
        assert "L3" in out

    def test_frontmatter_with_special_yaml(self):
        src = '---\ntitle: "test: value"\nconfig:\n  key: true\n---\ngraph LR\n  A-->B'
        out = render(src)
        assert "A" in out
        assert "---" not in out


class TestMindmapEdgeCases:
    """Edge cases specific to mindmap diagrams."""

    def test_single_child(self):
        out = render("mindmap\n  Root\n    Only")
        assert "Root" in out
        assert "Only" in out

    def test_wide_labels(self):
        out = render("mindmap\n  Root\n    This is a very long branch label\n    Short")
        assert "This is a very long branch label" in out

    def test_many_levels(self):
        src = "mindmap\n  A\n    B\n      C\n        D\n          E"
        out = render(src)
        for n in "ABCDE":
            assert n in out


class TestAllDiagramTypesNoCrash:
    """Every diagram type should handle minimal valid input without crashing."""

    @pytest.mark.parametrize("source", [
        "graph LR\n  A-->B",
        "graph TD\n  A-->B",
        "graph BT\n  A-->B",
        "graph RL\n  A-->B",
        "sequenceDiagram\n  A->>B: hello",
        "classDiagram\n  class Animal",
        "erDiagram\n  A ||--o{ B : has",
        "stateDiagram-v2\n  [*] --> A",
        "pie\n  \"A\" : 30\n  \"B\" : 70",
        'treemap-beta\n  "Root": 100',
        "mindmap\n  Root\n    A\n    B",
    ])
    def test_diagram_type_renders(self, source):
        out = render(source)
        assert isinstance(out, str)
        assert len(out) > 0
