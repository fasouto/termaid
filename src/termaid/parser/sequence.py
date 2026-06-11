"""Parser for Mermaid sequence diagram syntax."""
from __future__ import annotations

import re

from ..model.sequence import (
    ActivateEvent,
    Block,
    BlockSection,
    DestroyEvent,
    Message,
    Note,
    Participant,
    SequenceDiagram,
)

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

# Block start: loop, alt, opt, par, critical, break, rect (with optional label)
_BLOCK_START_RE = re.compile(
    r"^\s*(loop|alt|opt|par|critical|break|rect)\b\s*(.*?)\s*$",
    re.IGNORECASE,
)

# Block section: else, and, option (with optional label)
_BLOCK_SECTION_RE = re.compile(
    r"^\s*(else|and|option)\b\s*(.*?)\s*$",
    re.IGNORECASE,
)

# Block end
_BLOCK_END_RE = re.compile(r"^\s*end\s*$", re.IGNORECASE)

# Activate/deactivate keywords
_ACTIVATE_RE = re.compile(
    r"^\s*(activate|deactivate)\s+(\S+)\s*$",
    re.IGNORECASE,
)

# Lines to skip silently
_SKIP_RE = re.compile(
    r"^\s*(?:_NOTHING_MATCHES_THIS_)",
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

    # Stack-based parsing for nested blocks
    # event_stack[0] is the top-level events list
    event_stack: list[list] = [diagram.events]
    block_stack: list[Block] = []

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

        # Skip purely visual constructs
        if _SKIP_RE.match(stripped):
            continue

        # Block end
        if _BLOCK_END_RE.match(stripped):
            if block_stack:
                block_stack.pop()
                event_stack.pop()
            continue

        # Block section (else / and)
        m = _BLOCK_SECTION_RE.match(stripped)
        if m and block_stack:
            section_keyword = m.group(1).lower()
            section_label = m.group(2).strip()
            section = BlockSection(label=section_label, events=[])
            block_stack[-1].sections.append(section)
            # Switch current event target to this section's events
            event_stack[-1] = section.events
            continue

        # Block start (loop, alt, opt, par, critical, break)
        m = _BLOCK_START_RE.match(stripped)
        if m:
            kind = m.group(1).lower()
            label = m.group(2).strip()
            block = Block(kind=kind, label=label)
            event_stack[-1].append(block)
            block_stack.append(block)
            event_stack.append(block.events)
            continue

        # Activate/deactivate keywords
        m = _ACTIVATE_RE.match(stripped)
        if m:
            keyword = m.group(1).lower()
            pid = m.group(2)
            _ensure_participant(diagram, pid)
            event_stack[-1].append(ActivateEvent(
                participant=pid,
                active=(keyword == "activate"),
            ))
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
            note_text = re.sub(r'<br\s*/?>', '\n', note_text.strip(), flags=re.IGNORECASE)
            event_stack[-1].append(Note(
                text=note_text,
                position=position,
                participants=participants,
            ))
            continue

        # Destroy keyword
        m = re.match(r'^\s*destroy\s+(\S+)\s*$', stripped, re.IGNORECASE)
        if m:
            pid = m.group(1)
            _ensure_participant(diagram, pid)
            event_stack[-1].append(DestroyEvent(participant=pid))
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
            raw_source, arrow, raw_target, label = m.group(1), m.group(2), m.group(3), m.group(4)

            # Detect inline activation markers (+/-) after the arrow
            source = raw_source
            source_marker = ""
            if source[:1] in ("+", "-"):
                source_marker = source[0]
                source = source[1:]
            target = raw_target
            target_marker = ""
            if target[:1] in ("+", "-"):
                target_marker = target[0]
                target = target[1:]

            _ensure_participant(diagram, source)
            _ensure_participant(diagram, target)
            line_type, arrow_type = _lookup_arrow(arrow)
            event_stack[-1].append(Message(
                source=source,
                target=target,
                label=label.strip() if label else "",
                line_type=line_type,
                arrow_type=arrow_type,
            ))

            # Emit ActivateEvents for inline markers. Mermaid semantics:
            # '+' activates the receiver, '-' deactivates the sender.
            if source_marker:
                event_stack[-1].append(ActivateEvent(
                    participant=source, active=source_marker == "+",
                ))
            if target_marker == "+":
                event_stack[-1].append(ActivateEvent(
                    participant=target, active=True,
                ))
            elif target_marker == "-":
                event_stack[-1].append(ActivateEvent(
                    participant=source, active=False,
                ))
            continue

        # Unrecognized line
        diagram.warnings.append(f"Unrecognized line: {stripped!r}")

    return diagram
