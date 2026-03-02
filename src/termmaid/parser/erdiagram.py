"""Parser for Mermaid ER diagram syntax."""
from __future__ import annotations

import re

from ..model.erdiagram import Attribute, Entity, ERDiagram, Relationship

# Direction line
_DIRECTION_RE = re.compile(r"^\s*direction\s+(TB|LR|BT|RL|TD)\s*$", re.IGNORECASE)

# Entity with brace body: CUSTOMER { or p[Person] {
_ENTITY_BRACE_RE = re.compile(
    r'^\s*(\w+(?:-\w+)*)(?:\[("[^"]*"|\w+)\])?\s*\{\s*$'
)

# Standalone entity (just a name, no braces): CUSTOMER
_ENTITY_STANDALONE_RE = re.compile(
    r'^\s*(\w+(?:-\w+)*)(?:\[("[^"]*"|\w+)\])?\s*$'
)

# Quoted entity name in relationship: "DELIVERY ADDRESS"
_QUOTED_ENTITY = r'(?:"([^"]+)"|(\w+(?:-\w+)*))'

# Attribute inside entity body: type name [PK|FK|UK[, PK|FK|UK]] ["comment"]
_ATTR_RE = re.compile(
    r'^\s*(\S+)\s+(\S+)'
    r'(?:\s+((?:PK|FK|UK)(?:\s*,\s*(?:PK|FK|UK))*))?'
    r'(?:\s+"([^"]*)")?\s*$'
)

# Relationship regex (symbol-based)
# Left cardinality: || |o }| }o
# Line: -- or ..
# Right cardinality: || o| |{ o{
_REL_RE = re.compile(
    r'^\s*' + _QUOTED_ENTITY + r'\s+'
    r'([|}][|o])'            # left cardinality
    r'(--|\.\.)' +           # line style
    r'([o|][|{])'            # right cardinality
    r'\s+' + _QUOTED_ENTITY +
    r'\s*:\s*(.+?)\s*$'
)

# Word-based cardinality aliases → (left_symbol, right_symbol)
_CARD_ALIASES: list[tuple[str, str, str]] = [
    ("zero or one", "|o", "o|"),
    ("one or zero", "|o", "o|"),
    ("zero or more", "}o", "o{"),
    ("zero or many", "}o", "o{"),
    ("many(0)", "}o", "o{"),
    ("0+", "}o", "o{"),
    ("one or more", "}|", "|{"),
    ("one or many", "}|", "|{"),
    ("many(1)", "}|", "|{"),
    ("1+", "}|", "|{"),
    ("only one", "||", "||"),
    ("1", "||", "||"),
]

# Line aliases
_LINE_ALIASES: dict[str, str] = {
    "to": "--",
    "optionally to": "..",
}

# Word-based relationship regex:
# ENTITY1 <card-words> <line-word> <card-words> ENTITY2 : label
_REL_WORD_RE = re.compile(
    r'^\s*' + _QUOTED_ENTITY + r'\s+'
    r'(.+?)\s+'
    r'(to|optionally\s+to)\s+'
    r'(.+?)\s+'
    + _QUOTED_ENTITY +
    r'\s*:\s*(.+?)\s*$',
    re.IGNORECASE,
)

# Lines to skip
_SKIP_RE = re.compile(
    r"^\s*(?:style\s|classDef\s|%%)",
    re.IGNORECASE,
)


def _resolve_card_alias(text: str, side: str) -> str:
    """Resolve a word-based cardinality alias to its symbol form.

    side: "left" or "right" — determines which symbol variant to return.
    """
    t = text.strip().lower()
    for alias, left_sym, right_sym in _CARD_ALIASES:
        if t == alias:
            return left_sym if side == "left" else right_sym
    return ""


def _entity_name(quoted: str | None, unquoted: str | None) -> str:
    """Extract entity name from regex groups (quoted or unquoted)."""
    return (quoted or unquoted or "").strip()


def _ensure_entity(diagram: ERDiagram, name: str) -> None:
    """Add entity if not already present."""
    if name not in diagram.entities:
        diagram.entities[name] = Entity(name=name)


def parse_er_diagram(text: str) -> ERDiagram:
    """Parse a Mermaid ER diagram source into an ERDiagram model."""
    # Strip YAML frontmatter
    text = re.sub(r"^---\s*\n.*?\n---\s*\n", "", text, flags=re.DOTALL)

    diagram = ERDiagram()
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()
        i += 1

        # Skip empty lines, header, comments
        if not stripped or stripped.startswith("erDiagram") or stripped.startswith("%%") or stripped == "---":
            continue

        # Skip unsupported constructs
        if _SKIP_RE.match(stripped):
            continue

        # Closing brace (stray)
        if stripped == "}":
            continue

        # Direction
        m = _DIRECTION_RE.match(stripped)
        if m:
            d = m.group(1).upper()
            if d == "TD":
                d = "TB"
            diagram.direction = d
            continue

        # Relationship - symbol-based (must check before entity to avoid false positive)
        m = _REL_RE.match(stripped)
        if m:
            e1 = _entity_name(m.group(1), m.group(2))
            card1 = m.group(3)
            line = m.group(4)
            card2 = m.group(5)
            e2 = _entity_name(m.group(6), m.group(7))
            label = m.group(8).strip().strip('"')

            _ensure_entity(diagram, e1)
            _ensure_entity(diagram, e2)

            line_style = "dashed" if line == ".." else "solid"

            diagram.relationships.append(Relationship(
                entity1=e1,
                entity2=e2,
                card1=card1,
                card2=card2,
                line_style=line_style,
                label=label,
            ))
            continue

        # Relationship - word-based aliases
        m = _REL_WORD_RE.match(stripped)
        if m:
            e1 = _entity_name(m.group(1), m.group(2))
            card1_text = m.group(3)
            line_text = m.group(4).strip().lower()
            card2_text = m.group(5)
            e2 = _entity_name(m.group(6), m.group(7))
            label = m.group(8).strip().strip('"')

            card1 = _resolve_card_alias(card1_text, "left")
            card2 = _resolve_card_alias(card2_text, "right")
            line = _LINE_ALIASES.get(line_text, "--")

            if card1 and card2:
                _ensure_entity(diagram, e1)
                _ensure_entity(diagram, e2)

                line_style = "dashed" if line == ".." else "solid"

                diagram.relationships.append(Relationship(
                    entity1=e1,
                    entity2=e2,
                    card1=card1,
                    card2=card2,
                    line_style=line_style,
                    label=label,
                ))
                continue

        # Entity with brace body
        m = _ENTITY_BRACE_RE.match(stripped)
        if m:
            entity_name = m.group(1)
            alias = (m.group(2) or "").strip('"')
            _ensure_entity(diagram, entity_name)
            entity = diagram.entities[entity_name]
            if alias:
                entity.alias = alias

            # Read body lines until closing brace
            while i < len(lines):
                body_line = lines[i].strip()
                i += 1
                if body_line == "}" or body_line == "}\n":
                    break
                if not body_line:
                    continue
                # Parse attribute
                am = _ATTR_RE.match(body_line)
                if am:
                    attr_type = am.group(1)
                    attr_name = am.group(2)
                    keys_str = am.group(3) or ""
                    comment = am.group(4) or ""
                    keys = [k.strip() for k in keys_str.split(",") if k.strip()] if keys_str else []
                    entity.attributes.append(Attribute(
                        type=attr_type,
                        name=attr_name,
                        keys=keys,
                        comment=comment,
                    ))
            continue

        # Standalone entity (just a name on its own line, possibly with alias)
        m = _ENTITY_STANDALONE_RE.match(stripped)
        if m:
            entity_name = m.group(1)
            alias = (m.group(2) or "").strip('"')
            # Don't match keywords
            if entity_name.lower() not in ("erdiagram", "direction"):
                _ensure_entity(diagram, entity_name)
                if alias:
                    diagram.entities[entity_name].alias = alias
            continue

    return diagram
