"""Parser for Mermaid state diagram syntax.

Supports: stateDiagram / stateDiagram-v2 header, transitions (-->),
labels, [*] start/end, state aliases, composite states (subgraphs),
<<choice>>, <<fork>>, <<join>> stereotypes.
"""
from __future__ import annotations

import re

from ..graph.model import Direction, Edge, EdgeStyle, Graph, GraphNote, Node, Subgraph
from ..graph.shapes import NodeShape


_START_ID = "[*]_start"
_END_ID = "[*]_end"


def parse_state_diagram(text: str) -> Graph:
    """Parse mermaid stateDiagram text into a Graph model."""
    parser = _StateDiagramParser(text)
    return parser.parse()


class _StateDiagramParser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.graph = Graph()
        self._aliases: dict[str, str] = {}  # alias -> display label
        self._subgraph_stack: list[Subgraph] = []
        self._start_count = 0
        self._end_count = 0

    def parse(self) -> Graph:
        lines = self._preprocess(self.text)
        if not lines:
            return self.graph

        # Header
        header = lines[0].strip()
        if header.startswith("stateDiagram"):
            self.graph.direction = Direction.TB
        lines = lines[1:]

        for line in lines:
            self._parse_line(line)

        return self.graph

    def _preprocess(self, text: str) -> list[str]:
        """Split into lines, strip comments."""
        result: list[str] = []
        for line in text.split("\n"):
            # Remove %% comments
            idx = line.find("%%")
            if idx >= 0:
                line = line[:idx]
            stripped = line.strip()
            if stripped:
                result.append(stripped)
        return result

    def _parse_line(self, line: str) -> None:
        lower = line.strip().lower()

        # direction override
        if lower.startswith("direction "):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    self.graph.direction = Direction(parts[1].upper())
                except ValueError:
                    pass
            return

        # End of composite state
        if lower == "}":
            if self._subgraph_stack:
                self._subgraph_stack.pop()
            return

        # Note: note right of A : text  OR  note left of A : text
        note_match = re.match(
            r'note\s+(right\s+of|left\s+of)\s+(\S+)\s*:\s*(.*)',
            line, re.IGNORECASE
        )
        if note_match:
            position = note_match.group(1).lower().replace(" ", "")  # "rightof"/"leftof"
            target = note_match.group(2)
            text = re.sub(r'<br\s*/?>', '\n', note_match.group(3).strip(), flags=re.IGNORECASE)
            if target not in self.graph.nodes:
                self._ensure_node(target, self._aliases.get(target, target), NodeShape.ROUNDED)
            self.graph.notes.append(GraphNote(text=text, position=position, target=target))
            return
        # Skip other note variants we don't handle yet
        if lower.startswith("note "):
            return

        # State declaration with stereotype: state "name" as id <<stereotype>>
        # or: state "name" as id
        # or: state id <<stereotype>>
        # or: state Parent { (composite)
        state_match = re.match(
            r'state\s+"([^"]+)"\s+as\s+(\S+)\s*(<<\w+>>)?',
            line,
        )
        if state_match:
            label = state_match.group(1)
            alias = state_match.group(2)
            stereotype = state_match.group(3)
            self._aliases[alias] = label
            shape = self._stereotype_to_shape(stereotype)
            self._ensure_node(alias, label, shape)
            return

        # state id <<stereotype>>
        stereo_match = re.match(r'state\s+(\S+)\s+(<<\w+>>)', line)
        if stereo_match:
            state_id = stereo_match.group(1)
            stereotype = stereo_match.group(2)
            shape = self._stereotype_to_shape(stereotype)
            self._ensure_node(state_id, state_id, shape)
            return

        # Composite state: state Parent {
        composite_match = re.match(r'state\s+"?([^"{}]+)"?\s*\{', line)
        if composite_match:
            sg_label = composite_match.group(1).strip()
            sg_id = sg_label.replace(" ", "_")
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
            return

        # Transition: State1 --> State2 or State1 --> State2 : label
        trans_match = re.match(r'(.+?)\s*-->\s*(.+?)(?:\s*:\s*(.+))?$', line)
        if trans_match:
            src_raw = trans_match.group(1).strip()
            tgt_raw = trans_match.group(2).strip()
            label = (trans_match.group(3) or "").strip()

            src_id = self._resolve_state(src_raw, is_source=True)
            tgt_id = self._resolve_state(tgt_raw, is_source=False)

            self.graph.add_edge(Edge(
                source=src_id,
                target=tgt_id,
                label=label,
                style=EdgeStyle.SOLID,
                has_arrow_end=True,
            ))
            return

        # Plain state declaration (just a name on a line)
        if re.match(r'^[a-zA-Z_]\w*$', line.strip()):
            state_id = line.strip()
            if state_id not in self.graph.nodes:
                self._ensure_node(state_id, state_id, NodeShape.ROUNDED)

    def _resolve_state(self, raw: str, is_source: bool) -> str:
        """Resolve [*] to start/end nodes, or ensure a regular state exists."""
        if raw == "[*]":
            if is_source:
                self._start_count += 1
                node_id = f"{_START_ID}_{self._start_count}"
                self._ensure_node(node_id, "●", NodeShape.CIRCLE)
                return node_id
            else:
                self._end_count += 1
                node_id = f"{_END_ID}_{self._end_count}"
                self._ensure_node(node_id, "◉", NodeShape.CIRCLE)
                return node_id

        # Only set shape if node is new (don't override stereotype shapes)
        if raw not in self.graph.nodes:
            label = self._aliases.get(raw, raw)
            self._ensure_node(raw, label, NodeShape.ROUNDED)
        return raw

    def _ensure_node(self, node_id: str, label: str, shape: NodeShape) -> None:
        """Add a node if it doesn't exist yet."""
        node = Node(id=node_id, label=label, shape=shape)
        self.graph.add_node(node)
        # Register in current subgraph
        if self._subgraph_stack:
            sg = self._subgraph_stack[-1]
            if node_id not in sg.node_ids:
                sg.node_ids.append(node_id)

    def _stereotype_to_shape(self, stereotype: str | None) -> NodeShape:
        if not stereotype:
            return NodeShape.ROUNDED
        s = stereotype.lower()
        if "choice" in s:
            return NodeShape.DIAMOND
        if "fork" in s or "join" in s:
            return NodeShape.FORK_JOIN
        return NodeShape.ROUNDED
