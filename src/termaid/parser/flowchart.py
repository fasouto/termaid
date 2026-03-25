"""Recursive descent parser for Mermaid flowchart syntax.

Supports: graph/flowchart directives, all directions (TB/TD/LR/BT/RL),
node shapes ([], (), {}, ([]), [[]], (()), ((())) etc.), edge types
(-->, -.->, ==>, <-->, ---), edge labels, subgraphs, classDef, comments,
chained arrows, & operator.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..graph.model import ArrowType, Direction, Edge, EdgeStyle, Graph, LabelSegment, Node, Subgraph
from ..graph.shapes import NodeShape


# Arrow patterns ordered by specificity (longest match first)
_ARROW_PATTERNS: list[tuple[str, EdgeStyle, bool, bool]] = [
    # (pattern, style, has_arrow_start, has_arrow_end)
    # Bidirectional
    (r"<-\.->", EdgeStyle.DOTTED, True, True),
    (r"<==>", EdgeStyle.THICK, True, True),
    (r"<-->", EdgeStyle.SOLID, True, True),
    (r"<-+->", EdgeStyle.SOLID, True, True),
    (r"o--o", EdgeStyle.SOLID, True, True),
    (r"x--x", EdgeStyle.SOLID, True, True),
    # Dotted with arrow
    (r"-\.+->\|", EdgeStyle.DOTTED, False, True),  # will be handled separately
    (r"-\.+->", EdgeStyle.DOTTED, False, True),
    # Thick with arrow
    (r"=+=>", EdgeStyle.THICK, False, True),
    # Solid with arrow
    (r"-+->", EdgeStyle.SOLID, False, True),
    # Cross/circle endpoints
    (r"-+x", EdgeStyle.SOLID, False, True),
    (r"-+o", EdgeStyle.SOLID, False, True),
    # Open (no arrow)
    (r"-\.-", EdgeStyle.DOTTED, False, False),
    (r"=+", EdgeStyle.THICK, False, False),
    (r"-{3,}", EdgeStyle.SOLID, False, False),
    # Invisible
    (r"~~~", EdgeStyle.INVISIBLE, False, False),
]

# Node shape patterns: (open_delim, close_delim, shape)
# Order matters: most specific first
_SHAPE_PATTERNS: list[tuple[str, str, NodeShape]] = [
    ("(((", ")))", NodeShape.DOUBLE_CIRCLE),
    ("((", "))", NodeShape.CIRCLE),
    ("([", "])", NodeShape.STADIUM),
    ("[(", ")]", NodeShape.CYLINDER),
    ("[[", "]]", NodeShape.SUBROUTINE),
    ("[/", "\\]", NodeShape.TRAPEZOID),
    ("[\\", "/]", NodeShape.TRAPEZOID_ALT),
    ("[/", "/]", NodeShape.PARALLELOGRAM),
    ("[\\", "\\]", NodeShape.PARALLELOGRAM_ALT),
    ("{{", "}}", NodeShape.HEXAGON),
    ("{", "}", NodeShape.DIAMOND),
    ("(", ")", NodeShape.ROUNDED),
    (">", "]", NodeShape.ASYMMETRIC),
    ("[", "]", NodeShape.RECTANGLE),
]


# Map @{shape: name} values to NodeShape
_AT_SHAPE_MAP: dict[str, NodeShape] = {
    "rect": NodeShape.RECTANGLE,
    "rectangle": NodeShape.RECTANGLE,
    "rounded": NodeShape.ROUNDED,
    "circle": NodeShape.CIRCLE,
    "circ": NodeShape.CIRCLE,
    "diam": NodeShape.DIAMOND,
    "diamond": NodeShape.DIAMOND,
    "hex": NodeShape.HEXAGON,
    "hexagon": NodeShape.HEXAGON,
    "stadium": NodeShape.STADIUM,
    "terminal": NodeShape.STADIUM,
    "cyl": NodeShape.CYLINDER,
    "cylinder": NodeShape.CYLINDER,
    "db": NodeShape.CYLINDER,
    "subroutine": NodeShape.SUBROUTINE,
    "lean-r": NodeShape.PARALLELOGRAM,
    "lean-l": NodeShape.PARALLELOGRAM_ALT,
    "trap-t": NodeShape.TRAPEZOID,
    "trap-b": NodeShape.TRAPEZOID_ALT,
    "dbl-circ": NodeShape.DOUBLE_CIRCLE,
}


def _compute_arrow_length(arrow_text: str, style: EdgeStyle) -> int:
    """Compute the min_length from the number of repeating chars in an arrow.

    Base forms (length 1): -->, ==>, -.->, ---, ===, -.-
    Each extra repeating character adds 1 to the length.
    """
    has_head = arrow_text.rstrip().endswith(">") or arrow_text.lstrip().startswith("<")
    # Strip directional markers for counting
    s = arrow_text.lstrip("<ox").rstrip(">ox")
    if style == EdgeStyle.DOTTED:
        dots = s.count(".")
        # Base: -..-> has 1 dot (with head), -.- has 1 dot (no head)
        return max(1, dots)
    elif style == EdgeStyle.THICK:
        eqs = s.count("=")
        # Base: ==> has 2 eq (with head), === has 3 eq (no head)
        base = 2 if has_head else 3
        return max(1, eqs - base + 1)
    elif style == EdgeStyle.SOLID:
        dashes = s.count("-")
        # Base: --> has 2 dashes (with head), --- has 3 dashes (no head)
        base = 2 if has_head else 3
        return max(1, dashes - base + 1)
    return 1


def _parse_at_shape_props(body: str) -> dict[str, str]:
    """Parse key: value pairs from @{...} body, handling quoted strings."""
    props: dict[str, str] = {}
    # Split by commas, but respect quoted strings
    parts: list[str] = []
    current: list[str] = []
    in_quote = False
    for ch in body:
        if ch == '"' and not in_quote:
            in_quote = True
        elif ch == '"' and in_quote:
            in_quote = False
        elif ch == ',' and not in_quote:
            parts.append("".join(current))
            current = []
            continue
        current.append(ch)
    if current:
        parts.append("".join(current))

    for part in parts:
        part = part.strip()
        if ":" in part:
            k, v = part.split(":", 1)
            k = k.strip()
            v = v.strip().strip('"')
            props[k] = v
    return props


def parse_flowchart(text: str) -> Graph:
    """Parse mermaid flowchart/graph text into a Graph model."""
    parser = _FlowchartParser(text)
    return parser.parse()


def _strip_comments(line: str) -> str:
    """Remove %% comments from a line."""
    idx = line.find("%%")
    if idx >= 0:
        return line[:idx]
    return line


def _parse_markdown_label(text: str) -> tuple[str, list[LabelSegment]] | None:
    """Detect and parse a markdown label: "`**bold** and *italic*`".

    Returns (plain_text, segments) or None if not a markdown label.
    """
    # Check for backtick-quoted markdown: "`...`"
    stripped = text.strip()
    if not (stripped.startswith('"`') and stripped.endswith('`"')):
        return None

    md = stripped[2:-2]  # strip "` and `"
    segments: list[LabelSegment] = []
    plain_parts: list[str] = []
    i = 0
    while i < len(md):
        # Bold: **text**
        if md[i:i+2] == "**":
            end = md.find("**", i + 2)
            if end != -1:
                inner = md[i+2:end]
                segments.append(LabelSegment(text=inner, bold=True))
                plain_parts.append(inner)
                i = end + 2
                continue
        # Italic: *text*
        if md[i] == "*":
            end = md.find("*", i + 1)
            if end != -1:
                inner = md[i+1:end]
                segments.append(LabelSegment(text=inner, italic=True))
                plain_parts.append(inner)
                i = end + 1
                continue
        # Plain text: collect until next *
        j = i
        while j < len(md) and md[j] != "*":
            j += 1
        segments.append(LabelSegment(text=md[i:j]))
        plain_parts.append(md[i:j])
        i = j

    plain = "".join(plain_parts)
    return plain, segments


def _parse_css_props(text: str) -> dict[str, str]:
    """Parse CSS-like property string 'prop1:val1,prop2:val2' into a dict."""
    props: dict[str, str] = {}
    for prop in text.split(","):
        if ":" in prop:
            k, v = prop.split(":", 1)
            props[k.strip()] = v.strip()
    return props


def _inside_quotes(text: str, pos: int) -> bool:
    """Check if a position in text is inside a double-quoted string."""
    in_quote = False
    for i in range(pos):
        if text[i] == '"':
            in_quote = not in_quote
    return in_quote


def _strip_quotes(text: str) -> str:
    """Remove surrounding quotes from text."""
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1]
    return text


class _FlowchartParser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.graph = Graph()
        self._subgraph_stack: list[Subgraph] = []
        self._shaped_node_ids: set[str] = set()  # nodes with explicit shapes

    def parse(self) -> Graph:
        lines = self._preprocess(self.text)
        if not lines:
            return self.graph

        # Parse header
        header_line = lines[0]
        self._parse_header(header_line)

        # Parse body
        for line in lines[1:]:
            self._parse_line(line)

        # Post-processing: resolve edges to/from subgraph IDs
        self._resolve_subgraph_edges()

        return self.graph

    def _preprocess(self, text: str) -> list[str]:
        """Split into lines, handle semicolons, strip comments."""
        raw_lines: list[str] = []
        for line in text.split("\n"):
            # Expand semicolons into separate lines
            parts = line.split(";")
            for part in parts:
                raw_lines.append(part)

        result: list[str] = []
        for line in raw_lines:
            stripped = _strip_comments(line).strip()
            if stripped:
                result.append(stripped)
        return result

    def _parse_header(self, line: str) -> None:
        """Parse 'graph LR' or 'flowchart TD' etc."""
        parts = line.split()
        keyword = parts[0].lower()
        if keyword not in ("graph", "flowchart"):
            return

        if len(parts) >= 2:
            dir_str = parts[1].upper()
            try:
                self.graph.direction = Direction(dir_str)
            except ValueError:
                self.graph.direction = Direction.TB
        else:
            self.graph.direction = Direction.TB

    def _parse_line(self, line: str) -> None:
        """Parse a single body line."""
        lower = line.lower().strip()

        # Subgraph start
        if lower.startswith("subgraph"):
            self._parse_subgraph(line)
            return

        # Subgraph end
        if lower == "end":
            self._close_subgraph()
            return

        # Direction override inside subgraph
        if lower.startswith("direction "):
            self._parse_direction_override(line)
            return

        # classDef
        if lower.startswith("classdef "):
            self._parse_classdef(line)
            return

        # class assignment
        if lower.startswith("class "):
            self._parse_class_assignment(line)
            return

        # linkStyle directive
        if lower.startswith("linkstyle "):
            self._parse_linkstyle(line)
            return

        # style statement
        if lower.startswith("style "):
            self._parse_style(line)
            return

        # click statement (ignore)
        if lower.startswith("click "):
            return

        # Parse node/edge declarations
        self._parse_statement(line)

    def _parse_subgraph(self, line: str) -> None:
        """Parse 'subgraph [id] [label]'."""
        rest = line[len("subgraph"):].strip()

        # Handle 'subgraph id [label]' syntax
        sg_id = rest
        sg_label = rest

        # Check for 'id [label]' pattern
        bracket_match = re.match(r'(\S+)\s+\[(.+)\]', rest)
        if bracket_match:
            sg_id = bracket_match.group(1)
            sg_label = bracket_match.group(2)
        elif " " in rest:
            # Could be 'subgraph title text'
            # In mermaid, 'subgraph id' is the simple case
            sg_id = rest.split()[0]
            sg_label = rest

        sg_id = _strip_quotes(sg_id)
        sg_label = _strip_quotes(sg_label)

        sg = Subgraph(
            id=sg_id,
            label=sg_label,
            parent=self._subgraph_stack[-1] if self._subgraph_stack else None,
        )

        if self._subgraph_stack:
            self._subgraph_stack[-1].children.append(sg)
        else:
            self.graph.subgraphs.append(sg)

        self._subgraph_stack.append(sg)

    def _close_subgraph(self) -> None:
        if self._subgraph_stack:
            self._subgraph_stack.pop()

    def _parse_direction_override(self, line: str) -> None:
        parts = line.split()
        if len(parts) >= 2 and self._subgraph_stack:
            try:
                self._subgraph_stack[-1].direction = Direction(parts[1].upper())
            except ValueError:
                pass

    def _parse_classdef(self, line: str) -> None:
        """Parse 'classDef name prop1:val1,prop2:val2'."""
        parts = line.split(None, 2)
        if len(parts) < 3:
            return
        name = parts[1]
        props_str = parts[2]
        props: dict[str, str] = {}
        for prop in props_str.split(","):
            if ":" in prop:
                k, v = prop.split(":", 1)
                props[k.strip()] = v.strip()
        self.graph.class_defs[name] = props

    def _parse_class_assignment(self, line: str) -> None:
        """Parse 'class nodeId className'."""
        parts = line.split()
        if len(parts) >= 3:
            node_id = parts[1]
            class_name = parts[2]
            if node_id in self.graph.nodes:
                self.graph.nodes[node_id].style_class = class_name

    def _parse_style(self, line: str) -> None:
        """Parse 'style nodeId prop1:val1,prop2:val2'."""
        parts = line.split(None, 2)
        if len(parts) >= 3:
            node_id = parts[1]
            props = _parse_css_props(parts[2])
            self.graph.node_styles[node_id] = props

    def _parse_linkstyle(self, line: str) -> None:
        """Parse 'linkStyle 0 stroke:#ff3' or 'linkStyle default stroke:#ff3'.

        Supports comma-separated indices: 'linkStyle 0,1,2 stroke:#ff3'.
        Uses index -1 for 'default'.
        """
        parts = line.split(None, 2)
        if len(parts) < 3:
            return
        indices_str = parts[1]
        props = _parse_css_props(parts[2])

        if indices_str.lower() == "default":
            self.graph.link_styles[-1] = props
        else:
            for idx_str in indices_str.split(","):
                idx_str = idx_str.strip()
                if idx_str.isdigit():
                    self.graph.link_styles[int(idx_str)] = props

    def _parse_statement(self, line: str) -> None:
        """Parse a node/edge statement, handling chained arrows and & operator."""
        # Split by & at the top level to handle 'A & B --> C & D'
        # But we need to handle arrows first

        # Try to find arrows in the line
        segments = self._split_by_arrows(line)

        if len(segments) == 1:
            # No arrows found - just node declarations (possibly with &)
            node_groups = self._split_ampersand(segments[0].text)
            for node_text in node_groups:
                node = self._parse_node(node_text.strip())
                if node:
                    self.graph.add_node(node)
                    self._register_in_subgraph(node.id)
            return

        # Process chained arrow segments
        # segments alternate: [node_group, arrow, node_group, arrow, node_group, ...]
        prev_nodes: list[str] = []
        i = 0
        while i < len(segments):
            seg = segments[i]
            if seg.is_arrow:
                i += 1
                continue

            # Parse node group (handles &)
            node_group = self._split_ampersand(seg.text)
            current_nodes: list[str] = []
            for node_text in node_group:
                node = self._parse_node(node_text.strip())
                if node:
                    self.graph.add_node(node)
                    self._register_in_subgraph(node.id)
                    current_nodes.append(node.id)

            # If there's a previous group, create edges
            if prev_nodes and i > 0:
                arrow_seg = segments[i - 1]
                for src in prev_nodes:
                    for tgt in current_nodes:
                        edge = Edge(
                            source=src,
                            target=tgt,
                            label=arrow_seg.label,
                            style=arrow_seg.edge_style,
                            has_arrow_start=arrow_seg.has_arrow_start,
                            has_arrow_end=arrow_seg.has_arrow_end,
                            arrow_type_start=arrow_seg.arrow_type_start,
                            arrow_type_end=arrow_seg.arrow_type_end,
                            min_length=arrow_seg.min_length,
                        )
                        self.graph.add_edge(edge)

            prev_nodes = current_nodes
            i += 1

    def _register_in_subgraph(self, node_id: str) -> None:
        """Register a node in the current subgraph if inside one."""
        if self._subgraph_stack:
            sg = self._subgraph_stack[-1]
            if node_id not in sg.node_ids:
                sg.node_ids.append(node_id)

    def _resolve_subgraph_edges(self) -> None:
        """Resolve edges that reference subgraph IDs as source/target.

        If a node was auto-created (plain ID, never explicitly shaped) and
        matches a subgraph ID, mark the edge and remove the spurious node.
        """
        # Collect all subgraph IDs
        sg_ids: set[str] = set()
        def _collect(subs: list[Subgraph]) -> None:
            for sg in subs:
                sg_ids.add(sg.id)
                _collect(sg.children)
        _collect(self.graph.subgraphs)

        if not sg_ids:
            return

        # Find nodes that are actually subgraph references
        to_remove: set[str] = set()
        for edge in self.graph.edges:
            if edge.source in sg_ids and edge.source not in self._shaped_node_ids:
                edge.source_is_subgraph = True
                to_remove.add(edge.source)
            if edge.target in sg_ids and edge.target not in self._shaped_node_ids:
                edge.target_is_subgraph = True
                to_remove.add(edge.target)

        # Remove spurious nodes
        for nid in to_remove:
            self.graph.nodes.pop(nid, None)
            if nid in self.graph.node_order:
                self.graph.node_order.remove(nid)
            # Also remove from subgraph node_ids
            def _remove_from_sg(subs: list[Subgraph]) -> None:
                for sg in subs:
                    if nid in sg.node_ids:
                        sg.node_ids.remove(nid)
                    _remove_from_sg(sg.children)
            _remove_from_sg(self.graph.subgraphs)

    def _split_ampersand(self, text: str) -> list[str]:
        """Split 'A & B & C' into ['A', 'B', 'C'].

        Only splits on & outside of bracket/brace/paren delimiters,
        so 'D[Fix & Retry]' is NOT split.
        """
        parts: list[str] = []
        depth = 0
        current: list[str] = []
        i = 0
        while i < len(text):
            ch = text[i]
            if ch in "([{":
                depth += 1
                current.append(ch)
            elif ch in ")]}":
                depth = max(0, depth - 1)
                current.append(ch)
            elif depth == 0 and ch == "&" and i > 0 and text[i - 1] == " ":
                # Check for ' & ' pattern
                if i + 1 < len(text) and text[i + 1] == " ":
                    part = "".join(current).rstrip()
                    if part:
                        parts.append(part)
                    current = []
                    i += 2  # skip '& '
                    continue
                else:
                    current.append(ch)
            else:
                current.append(ch)
            i += 1
        part = "".join(current).strip()
        if part:
            parts.append(part)
        return parts

    @staticmethod
    def _mask_quotes(text: str) -> str:
        """Replace content inside quotes with spaces so arrow regex doesn't match inside labels."""
        result = list(text)
        in_quote = False
        quote_char = ""
        for i, ch in enumerate(result):
            if not in_quote and ch == '"':
                in_quote = True
                quote_char = ch
            elif in_quote and ch == quote_char:
                in_quote = False
            elif in_quote:
                result[i] = " "
        return "".join(result)

    def _split_by_arrows(self, line: str) -> list[_Segment]:
        """Split a line into alternating node and arrow segments."""
        segments: list[_Segment] = []
        remaining = line.strip()

        while remaining:
            # Mask quoted strings so arrows inside "..." aren't matched
            masked = self._mask_quotes(remaining)

            # Try to find the earliest arrow match
            best_match: tuple[int, int, EdgeStyle, bool, bool, str, int, ArrowType, ArrowType] | None = None

            # First check for labeled arrows: -->|text| or -- text -->
            label_match = self._find_labeled_arrow(masked)
            if label_match:
                pos, end, style, arr_start, arr_end, label, length, type_start, type_end = label_match
                if best_match is None or pos < best_match[0]:
                    best_match = (pos, end, style, arr_start, arr_end, label, length, type_start, type_end)

            # Then check for plain arrows
            plain_match = self._find_plain_arrow(masked)
            if plain_match:
                pos, end, style, arr_start, arr_end, length, type_start, type_end = plain_match
                if best_match is None or pos < best_match[0]:
                    best_match = (pos, end, style, arr_start, arr_end, "", length, type_start, type_end)

            if best_match is None:
                # No more arrows - rest is a node group
                text = remaining.strip()
                if text:
                    segments.append(_Segment(text=text))
                break

            pos, end, style, arr_start, arr_end, label, length, type_start, type_end = best_match

            # Text before the arrow is a node group
            before = remaining[:pos].strip()
            if before:
                segments.append(_Segment(text=before))

            # The arrow itself
            segments.append(_Segment(
                text=remaining[pos:end],
                is_arrow=True,
                edge_style=style,
                has_arrow_start=arr_start,
                has_arrow_end=arr_end,
                arrow_type_start=type_start,
                arrow_type_end=type_end,
                label=label,
                min_length=length,
            ))

            remaining = remaining[end:].strip()

        return segments if segments else [_Segment(text=line.strip())]

    def _find_labeled_arrow(self, text: str) -> tuple[int, int, EdgeStyle, bool, bool, str, int, ArrowType, ArrowType] | None:
        """Find arrows with labels: -->|text| or -- text --> or == text ==>.
        Returns (start, end, style, arr_start, arr_end, label, min_length, type_start, type_end)."""
        # Pattern: -->|text|
        m = re.search(r'(<--|<-\.|-\.|-+|=+|<)([-=.]+)(>?)(\|)([^|]*)(\|)', text)
        if m:
            label = m.group(5).strip()
            # Parse the arrow part (everything before the first |)
            arrow_part = text[m.start():m.start() + m.group(0).index("|")]
            style, arr_start, arr_end, type_start, type_end = self._classify_arrow(arrow_part + ">")
            length = _compute_arrow_length(arrow_part, style)
            return (m.start(), m.end(), style, arr_start, arr_end, label, length, type_start, type_end)

        # Pattern: -- text --> or == text ==> or -. text .->
        patterns = [
            (r'(--)(\s+.+?\s+)(-->)', EdgeStyle.SOLID, False, True),
            (r'(==)(\s+.+?\s+)(==>)', EdgeStyle.THICK, False, True),
            (r'(-\.)(\s+.+?\s+)(\.+->)', EdgeStyle.DOTTED, False, True),
        ]
        for pat, style, arr_start, arr_end in patterns:
            m = re.search(pat, text)
            if m:
                label_text = m.group(2).strip()
                arrow_portion = m.group(1) + m.group(3)
                length = _compute_arrow_length(arrow_portion, style)
                return (m.start(), m.end(), style, arr_start, arr_end, label_text, length, ArrowType.ARROW, ArrowType.ARROW)

        return None

    def _find_plain_arrow(self, text: str) -> tuple[int, int, EdgeStyle, bool, bool, int, ArrowType, ArrowType] | None:
        """Find the first plain arrow in text. Returns (start, end, style, arr_start, arr_end, min_length, type_start, type_end)."""
        # Try patterns in order of specificity
        # (pattern, style, arr_start, arr_end, type_start, type_end)
        patterns: list[tuple[str, EdgeStyle, bool, bool, ArrowType, ArrowType]] = [
            (r'<-\.+->',  EdgeStyle.DOTTED, True, True, ArrowType.ARROW, ArrowType.ARROW),
            (r'<=+=>',     EdgeStyle.THICK, True, True, ArrowType.ARROW, ArrowType.ARROW),
            (r'<-+->',     EdgeStyle.SOLID, True, True, ArrowType.ARROW, ArrowType.ARROW),
            (r'o-+o',      EdgeStyle.SOLID, True, True, ArrowType.CIRCLE, ArrowType.CIRCLE),
            (r'x-+x',      EdgeStyle.SOLID, True, True, ArrowType.CROSS, ArrowType.CROSS),
            (r'-\.+->',    EdgeStyle.DOTTED, False, True, ArrowType.ARROW, ArrowType.ARROW),
            (r'=+=>',      EdgeStyle.THICK, False, True, ArrowType.ARROW, ArrowType.ARROW),
            (r'-+->',      EdgeStyle.SOLID, False, True, ArrowType.ARROW, ArrowType.ARROW),
            (r'-+o(?=\s|$)', EdgeStyle.SOLID, False, True, ArrowType.ARROW, ArrowType.CIRCLE),
            (r'-+x(?=\s|$)', EdgeStyle.SOLID, False, True, ArrowType.ARROW, ArrowType.CROSS),
            (r'~~~',       EdgeStyle.INVISIBLE, False, False, ArrowType.ARROW, ArrowType.ARROW),
            (r'-\.-',      EdgeStyle.DOTTED, False, False, ArrowType.ARROW, ArrowType.ARROW),
            (r'={3,}',     EdgeStyle.THICK, False, False, ArrowType.ARROW, ArrowType.ARROW),
            (r'-{3,}',     EdgeStyle.SOLID, False, False, ArrowType.ARROW, ArrowType.ARROW),
        ]
        best: tuple[int, int, EdgeStyle, bool, bool, ArrowType, ArrowType] | None = None
        for pat, style, arr_start, arr_end, type_start, type_end in patterns:
            m = re.search(pat, text)
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), m.end(), style, arr_start, arr_end, type_start, type_end)
        if best is None:
            return None
        pos, end, style, arr_start, arr_end, type_start, type_end = best
        arrow_text = text[pos:end]
        length = _compute_arrow_length(arrow_text, style)
        return (pos, end, style, arr_start, arr_end, length, type_start, type_end)

    def _classify_arrow(self, arrow: str) -> tuple[EdgeStyle, bool, bool, ArrowType, ArrowType]:
        """Classify an arrow string into style, direction, and endpoint types."""
        s = arrow.strip()
        has_start = s.startswith("<") or s.startswith("o") or s.startswith("x")
        has_end = s.endswith(">") or s.endswith("x") or s.endswith("o")

        # Determine endpoint types
        type_start = ArrowType.ARROW
        type_end = ArrowType.ARROW
        if s.startswith("o"):
            type_start = ArrowType.CIRCLE
        elif s.startswith("x"):
            type_start = ArrowType.CROSS
        if s.endswith("o"):
            type_end = ArrowType.CIRCLE
        elif s.endswith("x"):
            type_end = ArrowType.CROSS

        if "." in s:
            return (EdgeStyle.DOTTED, has_start, has_end, type_start, type_end)
        if "=" in s:
            return (EdgeStyle.THICK, has_start, has_end, type_start, type_end)
        if "~" in s:
            return (EdgeStyle.INVISIBLE, has_start, has_end, type_start, type_end)
        return (EdgeStyle.SOLID, has_start, has_end, type_start, type_end)

    def _parse_node(self, text: str) -> Node | None:
        """Parse a single node declaration like 'A', 'A[label]', 'A{label}', etc."""
        if not text:
            return None

        text = text.strip().rstrip(";")

        # Handle :::className suffix
        style_class: str | None = None
        if ":::" in text:
            text, style_class = text.rsplit(":::", 1)
            text = text.strip()
            style_class = style_class.strip()

        # Try @{...} syntax: ID@{ shape: diamond, label: "text" }
        at_match = re.match(r'^([a-zA-Z_]\w*)\s*@\{(.+)\}$', text, re.DOTALL)
        if at_match:
            node_id = at_match.group(1)
            body = at_match.group(2)
            props = _parse_at_shape_props(body)
            shape_name = props.get("shape", "rect")
            label = props.get("label", node_id)
            shape = _AT_SHAPE_MAP.get(shape_name, NodeShape.RECTANGLE)
            self._shaped_node_ids.add(node_id)
            return Node(
                id=node_id,
                label=label,
                shape=shape,
                style_class=style_class,
            )

        # Try each shape pattern
        for open_delim, close_delim, shape in _SHAPE_PATTERNS:
            idx = text.find(open_delim)
            if idx > 0:
                # Skip if the delimiter is inside a quoted string
                if _inside_quotes(text, idx):
                    continue
                # Check if it ends with close_delim
                rest = text[idx + len(open_delim):]
                if rest.endswith(close_delim):
                    node_id = text[:idx].strip()
                    raw_label = rest[:-len(close_delim)].strip()
                    if not node_id:
                        continue
                    self._shaped_node_ids.add(node_id)
                    # Check for markdown label
                    md = _parse_markdown_label(raw_label)
                    if md:
                        plain, segments = md
                        return Node(
                            id=node_id,
                            label=plain,
                            shape=shape,
                            style_class=style_class,
                            label_segments=segments,
                        )
                    label = _strip_quotes(raw_label)
                    return Node(
                        id=node_id,
                        label=label,
                        shape=shape,
                        style_class=style_class,
                    )

        # Plain node ID (no shape delimiters)
        node_id = text.strip()
        if not node_id or not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', node_id):
            # Try with quotes
            node_id = _strip_quotes(node_id)
            if not node_id:
                return None

        return Node(
            id=node_id,
            label=node_id,
            shape=NodeShape.RECTANGLE,
            style_class=style_class,
        )


@dataclass
class _Segment:
    """A piece of a parsed line: either a node group or an arrow."""
    text: str = ""
    is_arrow: bool = False
    edge_style: EdgeStyle = EdgeStyle.SOLID
    has_arrow_start: bool = False
    has_arrow_end: bool = True
    arrow_type_start: ArrowType = ArrowType.ARROW
    arrow_type_end: ArrowType = ArrowType.ARROW
    label: str = ""
    min_length: int = 1
