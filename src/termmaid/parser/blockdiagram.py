"""Parser for Mermaid block-beta / block diagram syntax."""
from __future__ import annotations

import re

from ..model.blockdiagram import Block, BlockDiagram, BlockLink

# Shape patterns: (open_delim, close_delim, shape_name)
# Longest delimiters first to avoid ambiguity
_SHAPE_PATTERNS: list[tuple[str, str, str]] = [
    ("(((", ")))", "double_circle"),
    ("((", "))", "circle"),
    ("([", "])", "stadium"),
    ("[(", ")]", "cylinder"),
    ("[[", "]]", "subroutine"),
    ("[/", "\\]", "trapezoid"),
    ("[\\", "/]", "trapezoid_alt"),
    ("[/", "/]", "parallelogram"),
    ("[\\", "\\]", "parallelogram_alt"),
    ("{{", "}}", "hexagon"),
    ("{", "}", "diamond"),
    ("(", ")", "rounded"),
    (">", "]", "asymmetric"),
    ("[", "]", "rectangle"),
]

# Link: A-->B, A --> B, A-- "label" -->B
_LINK_LABEL_RE = re.compile(
    r"^(\S+)\s*--\s*\"([^\"]*)\"\s*-->\s*(\S+)$"
)
_LINK_SIMPLE_RE = re.compile(
    r"^(\S+)\s*-->\s*(\S+)$"
)

# Counter for anonymous group IDs
_anon_counter = 0


def parse_block_diagram(text: str) -> BlockDiagram:
    """Parse a block-beta or block diagram source into a BlockDiagram."""
    global _anon_counter
    _anon_counter = 0
    lines = _preprocess(text)
    blocks, links, columns, _ = _parse_group(lines, 0)
    return BlockDiagram(blocks=blocks, links=links, columns=columns)


def _preprocess(text: str) -> list[str]:
    """Strip header, comments, blank lines; return cleaned lines."""
    raw = text.strip().split("\n")
    result: list[str] = []
    for line in raw:
        stripped = line.strip()
        if not stripped:
            continue
        # Strip comments
        idx = stripped.find("%%")
        if idx >= 0:
            stripped = stripped[:idx].strip()
            if not stripped:
                continue
        result.append(stripped)
    # Remove header line (block-beta or block)
    if result and re.match(r"^block(-beta)?$", result[0], re.IGNORECASE):
        result = result[1:]
    return result


def _next_anon_id() -> str:
    global _anon_counter
    _anon_counter += 1
    return f"_anon_group_{_anon_counter}"


def _parse_group(lines: list[str], i: int) -> tuple[list[Block], list[BlockLink], int, int]:
    """Parse a group of lines into blocks, links, column count, and next line index.

    Handles nested block:ID ... end and anonymous block ... end groups recursively.
    """
    blocks: list[Block] = []
    links: list[BlockLink] = []
    columns = 0

    while i < len(lines):
        line = lines[i]
        lower = line.lower().strip()

        # End of group
        if lower == "end":
            return blocks, links, columns, i + 1

        # Skip directives
        if lower.startswith("classdef ") or lower.startswith("style ") or lower.startswith("class "):
            i += 1
            continue

        # Columns directive
        m = re.match(r"columns\s+(\d+)", line, re.IGNORECASE)
        if m:
            columns = int(m.group(1))
            i += 1
            continue

        # Named nested group: block:ID or block:ID:N
        m = re.match(r"block\s*:\s*(\w+)(?:\s*:\s*(\d+))?$", line, re.IGNORECASE)
        if m:
            group_id = m.group(1)
            col_span = int(m.group(2)) if m.group(2) else 1
            children, child_links, child_cols, i = _parse_group(lines, i + 1)
            blocks.append(Block(
                id=group_id,
                label=group_id,
                shape="rectangle",
                col_span=col_span,
                children=children,
                columns=child_cols,
            ))
            links.extend(child_links)
            continue

        # Anonymous nested group: bare "block" on its own line
        if lower == "block":
            group_id = _next_anon_id()
            children, child_links, child_cols, i = _parse_group(lines, i + 1)
            blocks.append(Block(
                id=group_id,
                label="",
                shape="rectangle",
                children=children,
                columns=child_cols,
            ))
            links.extend(child_links)
            continue

        # Try to parse link
        link_result = _try_parse_link(line)
        if link_result:
            link, src_token, tgt_token = link_result
            # Register or update block definitions from link endpoints
            all_blocks = _collect_all_blocks(blocks)
            for token in (src_token, tgt_token):
                parsed = _parse_block_token(token)
                if not parsed:
                    continue
                existing = all_blocks.get(parsed.id)
                if existing:
                    # Update shape/label if the link provides more detail
                    if parsed.shape != "rectangle" or parsed.label != parsed.id:
                        existing.shape = parsed.shape
                        existing.label = parsed.label
                else:
                    blocks.append(parsed)
                    all_blocks[parsed.id] = parsed
            links.append(link)
            i += 1
            continue

        # Parse space-separated block tokens on one line
        tokens = _tokenize_line(line)
        for token in tokens:
            block = _parse_block_token(token)
            if block:
                blocks.append(block)

        i += 1

    return blocks, links, columns, i


def _collect_all_blocks(blocks: list[Block]) -> dict[str, Block]:
    """Recursively collect all blocks (including children) into a dict by ID."""
    result: dict[str, Block] = {}
    for b in blocks:
        result[b.id] = b
        if b.children:
            result.update(_collect_all_blocks(b.children))
    return result


def _try_parse_link(line: str) -> tuple[BlockLink, str, str] | None:
    """Try to parse a line as a link: A-->B, A --> B, or A-- "label" -->B.

    Returns (link, source_token, target_token) so callers can also register
    block definitions from the endpoints.
    """
    m = _LINK_LABEL_RE.match(line)
    if m:
        src_token, tgt_token = m.group(1), m.group(3)
        src_id = _extract_block_id(src_token)
        tgt_id = _extract_block_id(tgt_token)
        return BlockLink(source=src_id, target=tgt_id, label=m.group(2)), src_token, tgt_token
    m = _LINK_SIMPLE_RE.match(line)
    if m:
        src_token, tgt_token = m.group(1), m.group(2)
        src_id = _extract_block_id(src_token)
        tgt_id = _extract_block_id(tgt_token)
        return BlockLink(source=src_id, target=tgt_id, label=""), src_token, tgt_token
    return None


def _extract_block_id(token: str) -> str:
    """Extract just the block ID from a token that may include shape syntax."""
    for open_delim, _, _ in _SHAPE_PATTERNS:
        idx = token.find(open_delim)
        if idx > 0:
            return token[:idx].strip()
    return token.strip()


def _tokenize_line(line: str) -> list[str]:
    """Split a line into block tokens, respecting bracket nesting."""
    tokens: list[str] = []
    current: list[str] = []
    depth = 0

    for ch in line:
        if ch in "([{":
            depth += 1
            current.append(ch)
        elif ch in ")]}":
            depth = max(0, depth - 1)
            current.append(ch)
        elif ch == "<":
            depth += 1
            current.append(ch)
        elif ch == ">" and depth > 0:
            depth -= 1
            current.append(ch)
        elif ch == " " and depth == 0:
            tok = "".join(current).strip()
            if tok:
                tokens.append(tok)
            current = []
        else:
            current.append(ch)

    tok = "".join(current).strip()
    if tok:
        tokens.append(tok)
    return tokens


def _parse_block_token(token: str) -> Block | None:
    """Parse a single block token like 'a', 'a:3', 'space', 'A["label"]', etc."""
    if not token:
        return None

    # Space block: space or space:N
    m = re.match(r"^space(?::(\d+))?$", token, re.IGNORECASE)
    if m:
        span = int(m.group(1)) if m.group(1) else 1
        return Block(id=f"_space_{id(token)}", is_space=True, col_span=span)

    # blockArrow syntax: id<["label"]>(dir) or id<["label"]>(dir, dir)
    # Treated as space when the label is whitespace-only (visual connector in Mermaid)
    m = re.match(r"^(\w+)<\[\"([^\"]*)\"\]>\([^)]+\)$", token)
    if m:
        label = _unescape_html(m.group(2))
        if not label.strip():
            return Block(id=m.group(1), is_space=True, col_span=1)
        return Block(id=m.group(1), label=label, shape="rectangle")

    # Check for col_span suffix: id:N or id["label"]:N
    col_span = 1
    span_match = re.search(r":(\d+)$", token)
    if span_match:
        col_span = int(span_match.group(1))
        token = token[:span_match.start()]

    # Try shape patterns
    for open_delim, close_delim, shape in _SHAPE_PATTERNS:
        idx = token.find(open_delim)
        if idx > 0:
            rest = token[idx + len(open_delim):]
            if rest.endswith(close_delim):
                block_id = token[:idx].strip()
                label = rest[:-len(close_delim)].strip()
                label = _strip_quotes(label)
                if block_id:
                    return Block(id=block_id, label=label, shape=shape, col_span=col_span)

    # Bare ID
    block_id = token.strip()
    if block_id and re.match(r"^[\w][\w.-]*$", block_id):
        return Block(id=block_id, label=block_id, shape="rectangle", col_span=col_span)

    return None


def _strip_quotes(text: str) -> str:
    """Remove surrounding quotes."""
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1]
    return text


def _unescape_html(text: str) -> str:
    """Unescape common HTML entities."""
    return text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
