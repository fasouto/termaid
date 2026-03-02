"""Parser for Mermaid class diagram syntax."""
from __future__ import annotations

import re

from ..model.classdiagram import ClassDef, ClassDiagram, Member, Note, Relationship

# Direction line
_DIRECTION_RE = re.compile(r"^\s*direction\s+(TB|LR|BT|RL|TD)\s*$", re.IGNORECASE)

# Class definition with brace body
_CLASS_BRACE_RE = re.compile(
    r"^\s*class\s+(\w+)(?:\s*~[^~]+~)?(?:\s*(<<\w+>>))?\s*\{\s*$"
)

# Class definition without brace body
_CLASS_SIMPLE_RE = re.compile(
    r"^\s*class\s+(\w+)(?:\s*~[^~]+~)?(?:\s*(<<\w+>>))?\s*$"
)

# Annotation inside brace body: <<interface>>
_ANNOTATION_RE = re.compile(r"^\s*<<(\w+)>>\s*$")

# Annotation on separate line: <<interface>> ClassName
_ANNOTATION_LINE_RE = re.compile(r"^\s*<<(\w+)>>\s+(\w+)\s*$")

# Colon member outside of brace body: ClassName : +memberName
_COLON_MEMBER_RE = re.compile(r"^\s*(\w+)\s*:\s*(.+?)\s*$")

# Relationship regex
# Left markers: <|, <, *, o  (longest first)
# Line types: --, ..
# Right markers: |>, >, *, o  (longest first)
_REL_RE = re.compile(
    r'^\s*(\w+)\s*'                          # source
    r'(?:"([^"]*)")?\s*'                     # optional source cardinality
    r'((?:<\||[<*o])?)'                      # left marker
    r'(--|\.\.|--\*|\.\.)'                   # line style
    r'((?:\|>|[>*o])?)'                      # right marker
    r'\s*(?:"([^"]*)")?\s*'                  # optional target cardinality
    r'(\w+)'                                 # target
    r'(?:\s*:\s*(.+?))?\s*$'                 # optional label
)

# Note for a specific class: note for Duck "can fly\ncan swim"
_NOTE_FOR_RE = re.compile(
    r'^\s*note\s+for\s+(\w+)\s+"([^"]*)"\s*$', re.IGNORECASE
)

# Floating note: note "From Duck till Zebra"
_NOTE_RE = re.compile(
    r'^\s*note\s+"([^"]*)"\s*$', re.IGNORECASE
)

# Lines to skip silently
_SKIP_RE = re.compile(
    r"^\s*(?:namespace\s|style\s|classDef\s|cssClass\s|click\s|callback\s|link\s)",
    re.IGNORECASE,
)


def _parse_member_text(text: str) -> Member:
    """Parse a member text line into a Member object."""
    text = text.strip()
    visibility = ""
    classifier = ""

    # Extract visibility prefix
    if text and text[0] in "+-#~":
        visibility = text[0]
        text = text[1:]

    # Extract classifier suffix
    if text.endswith("$") or text.endswith("*"):
        classifier = text[-1]
        text = text[:-1]

    text = text.strip()

    # Detect method (contains parentheses)
    is_method = "(" in text and ")" in text

    # Extract return type: look for type before name, or after ()
    return_type = ""
    if is_method:
        # Check for return type after closing paren: makeSound() void
        paren_end = text.rfind(")")
        after = text[paren_end + 1:].strip()
        if after:
            return_type = after
            text = text[:paren_end + 1]
    else:
        # For attributes: check "Type name" pattern
        parts = text.split(None, 1)
        if len(parts) == 2:
            # Could be "String name" or just "name"
            # Heuristic: if first part starts with uppercase, it's a type
            if parts[0][0].isupper() or parts[0] in ("int", "bool", "str", "float", "void", "string"):
                return_type = parts[0]
                text = parts[1]

    return Member(
        name=text.strip(),
        visibility=visibility,
        return_type=return_type,
        is_method=is_method,
        classifier=classifier,
    )


def _ensure_class(diagram: ClassDiagram, name: str) -> None:
    """Add class if not already present (auto-create on first mention)."""
    if name not in diagram.classes:
        diagram.classes[name] = ClassDef(name=name)


def parse_class_diagram(text: str) -> ClassDiagram:
    """Parse a Mermaid class diagram source into a ClassDiagram model."""
    # Strip YAML frontmatter
    import re as _re
    text = _re.sub(r"^---\s*\n.*?\n---\s*\n", "", text, flags=_re.DOTALL)

    diagram = ClassDiagram()
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()
        i += 1

        # Skip empty lines, header, comments, and frontmatter separators
        if not stripped or stripped.startswith("classDiagram") or stripped.startswith("%%") or stripped == "---":
            continue

        # Skip unsupported constructs
        if _SKIP_RE.match(stripped):
            continue

        # Closing brace (stray)
        if stripped == "}":
            continue

        # Note for a specific class
        m = _NOTE_FOR_RE.match(stripped)
        if m:
            target_cls = m.group(1)
            note_text = m.group(2)
            diagram.notes.append(Note(text=note_text, target=target_cls))
            continue

        # Floating note
        m = _NOTE_RE.match(stripped)
        if m:
            note_text = m.group(1)
            diagram.notes.append(Note(text=note_text))
            continue

        # Annotation on separate line: <<interface>> ClassName
        m = _ANNOTATION_LINE_RE.match(stripped)
        if m:
            annotation = m.group(1)
            class_name = m.group(2)
            _ensure_class(diagram, class_name)
            diagram.classes[class_name].annotation = annotation
            continue

        # Direction
        m = _DIRECTION_RE.match(stripped)
        if m:
            d = m.group(1).upper()
            if d == "TD":
                d = "TB"
            diagram.direction = d
            continue

        # Class with brace body
        m = _CLASS_BRACE_RE.match(stripped)
        if m:
            class_name = m.group(1)
            annotation = m.group(2)
            _ensure_class(diagram, class_name)
            cls = diagram.classes[class_name]
            if annotation:
                cls.annotation = annotation.strip("<>")

            # Read body lines until closing brace
            while i < len(lines):
                body_line = lines[i].strip()
                i += 1
                if body_line == "}" or body_line == "}\n":
                    break
                if not body_line:
                    continue
                # Check for annotation inside body
                am = _ANNOTATION_RE.match(body_line)
                if am:
                    cls.annotation = am.group(1)
                    continue
                # Parse as member
                cls.members.append(_parse_member_text(body_line))
            continue

        # Class without brace body
        m = _CLASS_SIMPLE_RE.match(stripped)
        if m:
            class_name = m.group(1)
            annotation = m.group(2)
            _ensure_class(diagram, class_name)
            if annotation:
                diagram.classes[class_name].annotation = annotation.strip("<>")
            continue

        # Relationship
        m = _REL_RE.match(stripped)
        if m:
            source = m.group(1)
            source_card = m.group(2) or ""
            left_marker = m.group(3) or ""
            line = m.group(4)
            right_marker = m.group(5) or ""
            target_card = m.group(6) or ""
            target = m.group(7)
            label = (m.group(8) or "").strip()

            _ensure_class(diagram, source)
            _ensure_class(diagram, target)

            line_style = "dashed" if ".." in line else "solid"

            diagram.relationships.append(Relationship(
                source=source,
                target=target,
                source_marker=left_marker,
                target_marker=right_marker,
                line_style=line_style,
                label=label,
                source_card=source_card,
                target_card=target_card,
            ))
            continue

        # Colon member: ClassName : member
        m = _COLON_MEMBER_RE.match(stripped)
        if m:
            class_name = m.group(1)
            member_text = m.group(2)
            _ensure_class(diagram, class_name)
            diagram.classes[class_name].members.append(_parse_member_text(member_text))
            continue

    return diagram
