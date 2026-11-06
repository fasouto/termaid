"""Draw a diagram from the start of its source, while the rest is still arriving.

When Mermaid source is streamed (an LLM writing a reply, a file being typed), the
last line is usually unfinished: ``C[Send sess`` or ``B -->|ye``. Parsed as is, such
a line turns into nodes made of raw syntax. ``complete_partial()`` makes the
unfinished line safe to draw: it closes open brackets and quotes, so a label shows
the text so far, and it holds back an edge whose target hasn't arrived yet.

Only the text after the last newline is treated as unfinished.
"""
from __future__ import annotations

import re

_CLOSERS = {"[": "]", "(": ")", "{": "}"}

# A link operator outside brackets: -->, ---, -.->, ==>, ~~~, --x, <-->, and the
# openers of a text link (A -- text --> B): --, ==, -.
_LINK_RE = re.compile(r"[<xo]?(?:-{2,}|={2,}|-\.+-?|~{3,})[->xo]?")
# Operators that only start a text link, and so never end an edge on their own.
_TEXT_LINK_OPENERS = {"--", "==", "-."}

_SEQUENCE_ARROW_RE = re.compile(r"(?:<<)?--?(?:>>|>|x|\))")
# The start of a link or arrow being typed, at the end of a line: "A -", "A--",
# "x-axis Low --", and other syntax that is only ever followed by more: "A <" (<-->),
# "A &" (parallel links), "A:" (:::class), "%" (a %% comment).
_TRAILING_OPERATOR_RE = re.compile(r"(?:\s|(?<=\w))[<xo]?[-=.~]+[->xo]?\s*$|\s*(?:<|&|:{1,2}|%)\s*$")
# The same for other diagram types, where "." and "-" may also belong to a number
# ("[0.3, 0.", "-5"): only whole arrow fragments after a space, or "--" after a word.
_TRAILING_ARROW_RE = re.compile(r"(?:\s[<xo]?[-=~]+|(?<=\w)[-=~]{2,})[->xo]?\s*$|\s*%\s*$")
# A target that so far is only an opening bracket or quote: "Done --> [", 'A --> "'
_BARE_OPENER_RE = re.compile(r"\s*[\[({\"]+\s*$")
# Diagram types whose half-typed lines are simply held back until they're finished
_HOLD_BACK_KINDS = ("erDiagram", "classDiagram")

_GRAPH_KINDS = ("graph", "flowchart", "stateDiagram")


def _diagram_kind(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("%%") and stripped != "---":
            return stripped.split()[0]
    return ""


def _outside_and_stack(line: str) -> tuple[str, list[str]]:
    """The line with bracketed and quoted text blanked, and the openers left unclosed."""
    outside: list[str] = []
    stack: list[str] = []
    for ch in line:
        if stack and stack[-1] == '"':
            if ch == '"':
                stack.pop()
            outside.append(" ")
            continue
        if ch == '"':
            stack.append('"')
            outside.append(" ")
        elif ch in _CLOSERS:
            stack.append(ch)
            outside.append(" ")
        elif stack and ch == _CLOSERS.get(stack[-1]):
            stack.pop()
            outside.append(" ")
        else:
            outside.append(" " if stack else ch)
    return "".join(outside), stack


def _complete_graph_line(line: str) -> str:
    """Flowchart and state lines: hold back a dangling edge, close open brackets.

    Trimming one unfinished piece can expose another ("B -- Yes --" is a text
    link still being typed twice over), so it repeats until nothing changes.
    """
    while True:
        before = line
        line = _BARE_OPENER_RE.sub("", line)
        outside, _ = _outside_and_stack(line)
        trailing = _TRAILING_OPERATOR_RE.search(outside)
        if trailing and not _LINK_RE.fullmatch(trailing.group().strip()):
            # Something still being typed ("A -", "A <", "A:"): not there yet.
            line = line[: trailing.start()].rstrip()
            outside, _ = _outside_and_stack(line)
        links = list(_LINK_RE.finditer(outside))
        if links:
            last = links[-1]
            rest = outside[last.end():].strip()
            if rest.startswith("|"):
                # A -->|label  or  A -->|label|  : the target hasn't arrived.
                closing = rest.find("|", 1)
                dangling = closing == -1 or not rest[closing + 1 :].strip()
            else:
                # A -->  (no target yet)  or  A -- te  (a text link's opener)
                dangling = not rest or last.group() in _TEXT_LINK_OPENERS
            if dangling:
                line = line[: last.start()].rstrip()
        if line == before:
            break
    _, stack = _outside_and_stack(line)
    return line + "".join('"' if o == '"' else _CLOSERS[o] for o in reversed(stack))


def _complete_sequence_line(line: str) -> str:
    """Sequence lines: wait for a whole keyword, and for a message's target and colon."""
    if re.fullmatch(r"\s*\S+", line):
        # One word still being typed may be the start of any keyword: "par" could
        # become "participant", "a" could become "alt" or "autonumber".
        return ""
    if _SEQUENCE_ARROW_RE.search(line) and ":" not in line:
        return ""
    return line


def _complete_line(kind: str, line: str) -> str:
    if kind == "sequenceDiagram":
        return _complete_sequence_line(line)
    if kind in _GRAPH_KINDS:
        return _complete_graph_line(line)
    if kind in _HOLD_BACK_KINDS:
        # Relationship syntax ("||--o{", "<|--") uses brackets as markers, so a
        # half-typed line can't be completed safely: wait for the rest of it.
        return ""
    # Other types: drop a half-typed arrow, close brackets and quotes.
    line = _TRAILING_ARROW_RE.sub("", _BARE_OPENER_RE.sub("", line))
    _, stack = _outside_and_stack(line)
    return line + "".join('"' if o == '"' else _CLOSERS[o] for o in reversed(stack))


def complete_partial(source: str) -> str:
    """Make the unfinished last line of streamed Mermaid source safe to draw.

    Source that ends with a newline is complete and is returned unchanged.
    """
    text = source.replace("\r\n", "\n").replace("\r", "\n")
    if not text or text.endswith("\n"):
        return text
    head, _, last = text.rpartition("\n")
    if not head:  # still on the header line
        return text
    kind = _diagram_kind(head)
    completed = _complete_line(kind, last)
    return f"{head}\n{completed}" if completed.strip() else head
