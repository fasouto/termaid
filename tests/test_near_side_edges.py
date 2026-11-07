"""Back-edges whose target sits beside them attach on their near sides when
that makes the drawing better (shorter, without new crossings or merges)."""
from __future__ import annotations

from termaid.parser.flowchart import parse_flowchart
from termaid.routing.router import AttachDir, layout_and_route

SESSIONS = """flowchart TD
    start[Agent.run] --> init[initialize]
    init --> id{session id?}
    id -->|none| neu[session/new]
    id -->|set| recon{reconnect and resume?}
    recon -->|yes| quiet[session/resume, no note]
    recon -->|no| loadCap{loadSession?}
    loadCap -->|yes| load[session/load]
    loadCap -->|no| resumeCap{resume?}
    resumeCap -->|yes| resume[session/resume plus note]
    resumeCap -->|no| fail[Resume not supported]
    neu --> state[modes and config]
    load --> state
    quiet --> state
    resume --> state
    state --> ready[AgentReady]
"""


def _routed(source: str):
    graph = parse_flowchart(source)
    _, routed = layout_and_route(graph, 4, 2, 4, None)
    return {(re.edge.source, re.edge.target): re for re in routed}


def test_a_back_edge_to_a_box_on_its_left_leaves_from_its_left_side():
    edge = _routed(SESSIONS)[("resume", "state")]
    assert (edge.start_dir, edge.end_dir) == (AttachDir.LEFT, AttachDir.RIGHT)


def test_a_back_edge_straight_above_still_loops_round():
    edge = _routed("flowchart TD\n  A --> B\n  B --> C\n  C --> A\n")[("C", "A")]
    assert edge.start_dir == AttachDir.RIGHT


def test_lr_back_edge_to_a_box_above_leaves_from_its_top():
    source = """graph LR
  A[main] --> B[develop]
  B --> C[feature/auth]
  B --> D[feature/ui]
  C --> E{PR Review}
  D --> E
  E -->|approved| B
  B --> F[release/1.0]
  F --> G{Tests?}
  G -->|pass| A
  G -->|fail| F
"""
    edge = _routed(source)[("G", "A")]
    assert edge.start_dir == AttachDir.TOP
