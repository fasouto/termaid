"""Parser for Mermaid sequence diagram syntax."""
from __future__ import annotations

import re

from ..model.sequence import Message, Note, Participant, SequenceDiagram

# Arrow patterns ordered by specificity (longest match first)
_ARROW_PATTERNS: list[tuple[str, str, str]] = [
    ("<<-->>", "dotted", "bidirectional"),
    ("<<->>",  "solid",  "bidirectional"),
    ("-->>", "dotted", "arrow"),
    ("->>",  "solid",  "arrow"),
    ("--x",  "dotted", "cross"),
    ("-x",   "solid",  "cross"),
    ("--)",  "dotted", "async"),
    ("-)",   "solid",  "async"),
    ("-->",  "dotted", "open"),
    ("->",   "solid",  "open"),
]

# Regex for message lines: Source<arrow>Target: Label
# Build one big alternation from the arrow patterns
_ARROW_RE_PART = "|".join(re.escape(a) for a, _, _ in _ARROW_PATTERNS)
_MESSAGE_RE = re.compile(
    rf"^\s*(\S+?)\s*({_ARROW_RE_PART})\s*(\S+?)\s*(?::\s*(.*?))?\s*$"
)

# Combined regex for all participant types (with optional "create" prefix)
_PARTICIPANT_KIND_RE = re.compile(
    r"^\s*(?:create\s+)?(participant|actor|database|queue|boundary|control|entity|collections)"
    r"\s+(\S+)(?:\s+as\s+(.+?))?\s*$", re.IGNORECASE)

# Note regex: Note right of A: text, Note left of A: text, Note over A: text, Note over A,B: text
_NOTE_RE = re.compile(
    r"^\s*Note\s+(right\s+of|left\s+of|over)\s+(\S+?)(?:\s*,\s*(\S+?))?\s*:\s*(.*?)\s*$",
    re.IGNORECASE)

# Lines to skip silently (control blocks, etc.)
_SKIP_RE = re.compile(
    r"^\s*(?:alt\s|else\s|end\b|loop\s|opt\s|par\s|and\s|critical\s|break\s|rect\s|activate\s|deactivate\s|destroy\s)",
    re.IGNORECASE,
)


def _lookup_arrow(arrow_str: str) -> tuple[str, str]:
    """Return (line_type, arrow_type) for an arrow string."""
    for pattern, line_type, arrow_type in _ARROW_PATTERNS:
        if arrow_str == pattern:
            return line_type, arrow_type
    return "solid", "open"


def _ensure_participant(diagram: SequenceDiagram, pid: str) -> None:
    """Add participant if not already present (auto-create on first mention)."""
    for p in diagram.participants:
        if p.id == pid:
            return
    diagram.participants.append(Participant(id=pid, label=pid))


def parse_sequence_diagram(text: str) -> SequenceDiagram:
    """Parse a Mermaid sequence diagram source into a SequenceDiagram model."""
    diagram = SequenceDiagram()

    lines = text.split("\n")
    for line in lines:
        stripped = line.strip()

        # Skip empty lines, header, and comments
        if not stripped or stripped.startswith("sequenceDiagram") or stripped.startswith("%%"):
            continue

        # Autonumber keyword
        if stripped.lower() == "autonumber":
            diagram.autonumber = True
            continue

        # Skip control blocks and other unsupported constructs
        if _SKIP_RE.match(stripped):
            continue

        # Note declarations
        m = _NOTE_RE.match(stripped)
        if m:
            position_raw, p1, p2, note_text = m.group(1), m.group(2), m.group(3), m.group(4)
            position = position_raw.lower().replace(" ", "")  # "rightof", "leftof", "over"
            participants = [p1]
            if p2:
                participants.append(p2)
            _ensure_participant(diagram, p1)
            if p2:
                _ensure_participant(diagram, p2)
            diagram.events.append(Note(
                text=note_text.strip(),
                position=position,
                participants=participants,
            ))
            continue

        # Participant kind declarations (participant, actor, database, etc.)
        m = _PARTICIPANT_KIND_RE.match(stripped)
        if m:
            kind, pid, label = m.group(1).lower(), m.group(2), m.group(3)
            label = label.strip() if label else pid
            found = False
            for p in diagram.participants:
                if p.id == pid:
                    p.label = label
                    p.kind = kind
                    found = True
                    break
            if not found:
                diagram.participants.append(Participant(id=pid, label=label, kind=kind))
            continue

        # message lines
        m = _MESSAGE_RE.match(stripped)
        if m:
            source, arrow, target, label = m.group(1), m.group(2), m.group(3), m.group(4)
            # Strip activation/deactivation markers (+/-) from participant IDs
            source = source.lstrip("+-")
            target = target.lstrip("+-")
            _ensure_participant(diagram, source)
            _ensure_participant(diagram, target)
            line_type, arrow_type = _lookup_arrow(arrow)
            diagram.events.append(Message(
                source=source,
                target=target,
                label=label.strip() if label else "",
                line_type=line_type,
                arrow_type=arrow_type,
            ))
            continue

    return diagram
