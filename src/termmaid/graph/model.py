from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

from .shapes import NodeShape


@dataclass
class GraphNote:
    """A note attached to a node in the graph."""
    text: str
    position: str  # "rightof" or "leftof"
    target: str    # node id


@dataclass
class LabelSegment:
    """A segment of a node label with optional bold/italic styling."""
    text: str
    bold: bool = False
    italic: bool = False


class ArrowType(Enum):
    ARROW = auto()    # --> (filled triangle ►▼◄▲)
    CIRCLE = auto()   # --o (○)
    CROSS = auto()    # --x (×)


class EdgeStyle(Enum):
    SOLID = auto()       # -->
    DOTTED = auto()      # -.->
    THICK = auto()       # ==>
    INVISIBLE = auto()   # ~~~


class Direction(Enum):
    TB = "TB"
    TD = "TD"
    LR = "LR"
    BT = "BT"
    RL = "RL"

    @property
    def is_vertical(self) -> bool:
        return self in (Direction.TB, Direction.TD, Direction.BT)

    @property
    def is_horizontal(self) -> bool:
        return self in (Direction.LR, Direction.RL)

    @property
    def is_reversed(self) -> bool:
        return self in (Direction.BT, Direction.RL)

    def normalized(self) -> Direction:
        """Return the non-reversed equivalent (BT->TB, RL->LR)."""
        if self == Direction.BT:
            return Direction.TB
        if self == Direction.RL:
            return Direction.LR
        if self == Direction.TD:
            return Direction.TB
        return self


@dataclass
class Node:
    id: str
    label: str
    shape: NodeShape = NodeShape.RECTANGLE
    style_class: str | None = None
    label_segments: list[LabelSegment] | None = None

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Node):
            return self.id == other.id
        return NotImplemented


@dataclass
class Edge:
    source: str
    target: str
    label: str = ""
    style: EdgeStyle = EdgeStyle.SOLID
    has_arrow_start: bool = False
    has_arrow_end: bool = True
    arrow_type_start: ArrowType = ArrowType.ARROW
    arrow_type_end: ArrowType = ArrowType.ARROW
    min_length: int = 1
    source_is_subgraph: bool = False
    target_is_subgraph: bool = False

    @property
    def is_bidirectional(self) -> bool:
        return self.has_arrow_start and self.has_arrow_end

    @property
    def is_self_reference(self) -> bool:
        return self.source == self.target


@dataclass
class Subgraph:
    id: str
    label: str
    node_ids: list[str] = field(default_factory=list)
    children: list[Subgraph] = field(default_factory=list)
    direction: Direction | None = None
    parent: Subgraph | None = field(default=None, repr=False)


@dataclass
class Graph:
    direction: Direction = Direction.TB
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    subgraphs: list[Subgraph] = field(default_factory=list)
    node_order: list[str] = field(default_factory=list)
    class_defs: dict[str, dict[str, str]] = field(default_factory=dict)
    node_styles: dict[str, dict[str, str]] = field(default_factory=dict)
    link_styles: dict[int, dict[str, str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    notes: list[GraphNote] = field(default_factory=list)

    def add_node(self, node: Node) -> None:
        if node.id not in self.nodes:
            self.nodes[node.id] = node
            self.node_order.append(node.id)
        else:
            existing = self.nodes[node.id]
            if node.label != node.id and existing.label == existing.id:
                existing.label = node.label
            if node.shape != NodeShape.RECTANGLE:
                existing.shape = node.shape
            if node.style_class:
                existing.style_class = node.style_class

    def add_edge(self, edge: Edge) -> None:
        self.edges.append(edge)

    def get_roots(self) -> list[str]:
        """Nodes with no incoming edges, in definition order."""
        targets = {e.target for e in self.edges}
        roots = [nid for nid in self.node_order if nid not in targets]
        return roots if roots else [self.node_order[0]] if self.node_order else []

    def get_children(self, node_id: str) -> list[str]:
        """Get target nodes of outgoing edges from node_id, in order."""
        seen: set[str] = set()
        children: list[str] = []
        for e in self.edges:
            if e.source == node_id and e.target != node_id and e.target not in seen:
                seen.add(e.target)
                children.append(e.target)
        return children

    def find_subgraph_by_id(self, sg_id: str) -> Subgraph | None:
        """Find a subgraph by its ID (recursive search)."""
        def _search(subs: list[Subgraph]) -> Subgraph | None:
            for sg in subs:
                if sg.id == sg_id:
                    return sg
                result = _search(sg.children)
                if result:
                    return result
            return None
        return _search(self.subgraphs)

    def find_subgraph_for_node(self, node_id: str) -> Subgraph | None:
        """Find the innermost subgraph containing a node."""
        def _search(subs: list[Subgraph]) -> Subgraph | None:
            for sg in subs:
                result = _search(sg.children)
                if result:
                    return result
                if node_id in sg.node_ids:
                    return sg
            return None
        return _search(self.subgraphs)
