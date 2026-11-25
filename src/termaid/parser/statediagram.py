"""Parser for Mermaid state diagram syntax.

Supports: stateDiagram / stateDiagram-v2 header, transitions (-->),
labels, [*] start/end, state aliases, composite states (subgraphs),
<<choice>>, <<fork>>, <<join>> stereotypes.
"""
from __future__ import annotations

import re

from ..graph.model import Direction, Edge, EdgeStyle, Graph, GraphNote, Node, Subgraph
from ..graph.shapes import NodeShape
from ..utils import line_breaks


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
        self._descriptions: dict[str, list[str]] = {}  # state id -> `id : text` lines
        self._open_note: GraphNote | None = None  # a note whose `end note` hasn't come
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
            if self._open_note is not None:
                self._note_line(self._open_note, line)
            else:
                self._parse_line(line)

        self._apply_descriptions()
        self._resolve_composite_edges()
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

    def _note_line(self, note: GraphNote, line: str) -> None:
        if line.lower() == "end note":
            self._open_note = None
        else:
            note.text = "\n".join(filter(None, [note.text, line_breaks(line)]))

    def _parse_line(self, line: str) -> None:
        lower = line.strip().lower()

        # direction override: inside `{ }` it is the composite's own direction
        if lower.startswith("direction "):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    direction = Direction(parts[1].upper())
                except ValueError:
                    return
                if self._subgraph_stack:
                    self._subgraph_stack[-1].direction = direction
                else:
                    self.graph.direction = direction
            return

        # End of composite state
        if lower == "}":
            if self._subgraph_stack:
                self._subgraph_stack.pop()
            return

        # Note: `note right of A : text`, or `note left of A` with its text
        # on the lines up to `end note`
        note_match = re.match(
            r'note\s+(right|left)\s+of\s+([^\s:]+)\s*(?::\s*(.*))?$',
            line, re.IGNORECASE
        )
        if note_match:
            target = note_match.group(2)
            if target not in self.graph.nodes:
                self._ensure_node(target, self._aliases.get(target, target), NodeShape.ROUNDED)
            note = GraphNote(
                text=line_breaks((note_match.group(3) or "").strip()),
                position=note_match.group(1).lower() + "of",
                target=target,
            )
            self.graph.notes.append(note)
            if note_match.group(3) is None:
                self._open_note = note
            return
        # Skip other note variants we don't handle yet
        if lower.startswith("note "):
            return

        # State declaration with stereotype: state "name" as id <<stereotype>>
        # or: state "name" as id
        # or: state "name" as id { (composite with a display name)
        # or: state id <<stereotype>>
        # or: state Parent { (composite)
        state_match = re.match(
            r'state\s+"([^"]+)"\s+as\s+([^\s{]+)\s*(<<\w+>>)?\s*(\{)?',
            line,
        )
        if state_match:
            alias = state_match.group(2)
            if state_match.group(4):
                self._open_composite(alias, state_match.group(1))
                return
            label = line_breaks(state_match.group(1), "\\n")  # node labels break on a backslash-n
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
            self._open_composite(sg_label.replace(" ", "_"), sg_label)
            return

        # Transition: State1 --> State2 or State1 --> State2 : label
        # A `:::class` suffix on either end is a style, not part of the id or label
        trans_match = re.match(
            r'(.+?)(?::::[\w-]+)?\s*-->\s*(.+?)(?::::[\w-]+)?(?:\s*:\s*(.+))?$', line,
        )
        if trans_match:
            src_raw = trans_match.group(1).strip()
            tgt_raw = trans_match.group(2).strip()
            label = line_breaks((trans_match.group(3) or "").strip())

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

        # State description: `s1 : text`
        desc_match = re.match(r'([^\s:]+)\s*:\s*(.+)$', line)
        if desc_match:
            state_id = desc_match.group(1)
            self._resolve_state(state_id, is_source=True)
            self._descriptions.setdefault(state_id, []).append(
                line_breaks(desc_match.group(2).strip())
            )
            return

        # Plain state declaration (just a name on a line)
        if re.match(r'^[a-zA-Z_]\w*$', line.strip()):
            state_id = line.strip()
            if state_id not in self.graph.nodes:
                self._ensure_node(state_id, state_id, NodeShape.ROUNDED)

    def _open_composite(self, sg_id: str, sg_label: str) -> None:
        sg = Subgraph(
            id=sg_id,
            label=line_breaks(sg_label, " "),  # a title has one row
            parent=self._subgraph_stack[-1] if self._subgraph_stack else None,
        )
        if self._subgraph_stack:
            self._subgraph_stack[-1].children.append(sg)
        else:
            self.graph.subgraphs.append(sg)
        self._subgraph_stack.append(sg)

    def _apply_descriptions(self) -> None:
        """Label each described state, as Mermaid does.

        One description replaces the name; with more, the name stays as a
        title over them. On a composite state it is the title.
        """
        titles: dict[str, str] = {}
        for state_id, descriptions in self._descriptions.items():
            alias = self._aliases.get(state_id)
            if alias is not None:
                descriptions = [alias, *descriptions]
            if len(descriptions) == 1:
                titles[state_id] = descriptions[0]
            else:
                titles[state_id] = "\n".join([state_id, *descriptions])
            node = self.graph.nodes.get(state_id)
            if node is not None:
                node.label = titles[state_id]

        def _title(subs: list[Subgraph]) -> None:
            for sg in subs:
                if sg.id in titles:
                    sg.label = titles[sg.id].replace("\n", " ")
                _title(sg.children)

        if titles:
            _title(self.graph.subgraphs)

    def _resolve_composite_edges(self) -> None:
        """Point transitions at composite states to the subgraph itself.

        A transition like `Idle --> Processing` may be parsed before or after
        `state Processing { ... }`, so `_resolve_state` creates a plain node for
        it, as does a description line. Once parsing is done, swap those nodes
        for the subgraph so the edge attaches to the composite's border instead
        of a duplicate box.
        """
        sg_ids: set[str] = set()
        all_subgraphs: list[Subgraph] = []

        def _collect(subs: list[Subgraph]) -> None:
            for sg in subs:
                sg_ids.add(sg.id)
                all_subgraphs.append(sg)
                _collect(sg.children)

        _collect(self.graph.subgraphs)
        if not sg_ids:
            return

        for edge in self.graph.edges:
            if edge.source in sg_ids:
                edge.source_is_subgraph = True
            if edge.target in sg_ids:
                edge.target_is_subgraph = True

        for nid in sg_ids & self.graph.nodes.keys():
            self.graph.nodes.pop(nid, None)
            if nid in self.graph.node_order:
                self.graph.node_order.remove(nid)
            for sg in all_subgraphs:
                if nid in sg.node_ids:
                    sg.node_ids.remove(nid)

    def _resolve_state(self, raw: str, is_source: bool) -> str:
        """Resolve [*] to start/end nodes, or ensure a regular state exists."""
        if raw == "[*]":
            if is_source:
                self._start_count += 1
                node_id = f"{_START_ID}_{self._start_count}"
                self._ensure_node(node_id, "●", NodeShape.START_STATE)
                return node_id
            else:
                self._end_count += 1
                node_id = f"{_END_ID}_{self._end_count}"
                self._ensure_node(node_id, "◉", NodeShape.END_STATE)
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
