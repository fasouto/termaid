"""Draw Mermaid blocks in Claude Code's responses as they stream.

Claude Code's ``MessageDisplay`` hook hands the assistant's text to a
command in batches of completed lines and shows the command's answer in
their place. This module is that command::

    termaid --claude-hook

The hard part is that a fence can straddle batches, so the diagram's
lines are held back until the closing fence arrives and the drawing is
then emitted in their place. Nothing changes in the transcript: Claude
keeps seeing the Mermaid source, only the screen shows the diagram.

:class:`StreamRenderer` knows nothing about Claude Code. It is a line
filter whose state can be saved between calls, so another tool with a
similar streaming display can wrap it the same way :func:`run_claude_hook`
does here.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import sys
import tempfile
from dataclasses import asdict, dataclass, field

from .markdown import _OPEN, _dedent
from .utils import display_width

_DEFAULT_WIDTH = 80
_MARGIN = 4  # Claude Code indents messages; keep diagrams clear of the edge


@dataclass
class StreamRenderer:
    """Line filter that replaces fenced Mermaid blocks with drawings.

    Feed it text with :meth:`feed` and print what comes back. Lines inside
    a Mermaid fence are held until the fence closes, so a call may return
    less text than it was given, and a later call returns the drawing.
    """

    width: int | None = None
    use_ascii: bool = False
    # Fence state, kept simple so it survives a round trip through JSON.
    fence: str = ""        # the opening fence's characters, "" when outside
    indent: str = ""
    held: list[str] = field(default_factory=list)   # original lines, fence included
    carry: str = ""        # a final batch may end mid-line

    def feed(self, text: str, final: bool = False) -> str:
        out: list[str] = []
        text = self.carry + text
        self.carry = ""
        lines = text.split("\n")
        tail = lines.pop()  # "" when the text ended on a newline
        if tail and not final:
            self.carry = tail
            tail = ""
        for line in lines:
            out.extend(self._line(line))
        shown = "".join(line + "\n" for line in out)
        if final:
            if tail:
                shown += "".join(line + "\n" for line in self._line(tail)).rstrip("\n")
            if self.fence:
                # Message ended inside a fence: show it as Claude wrote it
                shown += "".join(line + "\n" for line in self.held)
                if tail and self.held and self.held[-1] == tail:
                    shown = shown.rstrip("\n")
                self._reset()
        return shown

    def _line(self, line: str) -> list[str]:
        if self.fence:
            self.held.append(line)
            close = re.compile(
                r"^[ \t]*" + re.escape(self.fence[0]) + "{" + str(len(self.fence)) + r",}[ \t]*\r?$"
            )
            if not close.match(line):
                return []
            body = [_dedent(raw, len(self.indent)).rstrip("\r") for raw in self.held[1:-1]]
            drawn = self._draw("\n".join(body))
            held, self.held = self.held, []
            self._reset()
            return drawn if drawn is not None else held
        match = _OPEN.match(line)
        if match and not (match.group("fence")[0] == "`" and "`" in match.group("info")):
            words = match.group("info").split()
            if words and words[0].lower() == "mermaid":
                self.fence = match.group("fence")
                self.indent = match.group("indent")
                self.held = [line]
                return []
        return [line]

    def _reset(self) -> None:
        self.fence = ""
        self.indent = ""
        self.held = []

    def _draw(self, source: str) -> list[str] | None:
        """Render one diagram, or None when it cannot be drawn."""
        from . import render

        if not source.strip():
            return None
        width = self.width
        if width is None:
            width = max(shutil.get_terminal_size((_DEFAULT_WIDTH, 24)).columns - _MARGIN, 20)
        width = max(width - display_width(self.indent), 20)
        try:
            text = render(source, use_ascii=self.use_ascii)
            for gap, pad in ((2, 4), (1, 2), (1, 0)):
                if _widest(text) <= width:
                    break
                text = render(source, use_ascii=self.use_ascii, gap=gap, padding_x=pad)
        except Exception:
            return None
        if not text.strip():
            return None
        # A code fence keeps the box characters monospaced and unformatted
        # when the display renders Markdown.
        fence = "```"
        while fence in text:
            fence += "`"
        return [self.indent + fence] + [self.indent + ln for ln in text.split("\n")] + [self.indent + fence]

    def to_json(self) -> str:
        return json.dumps({k: v for k, v in asdict(self).items() if k in ("fence", "indent", "held", "carry")})

    def load(self, data: str) -> None:
        saved = json.loads(data)
        self.fence = saved.get("fence", "")
        self.indent = saved.get("indent", "")
        self.held = list(saved.get("held", []))
        self.carry = saved.get("carry", "")


def _widest(text: str) -> int:
    return max((display_width(line) for line in text.split("\n")), default=0)


def _state_dir() -> str | None:
    """Return the folder that holds hook state, or None when it is not private.

    The temp folder is shared between users on Linux, and anyone can create a
    folder there first, then read the state or swap a file for a symlink. So
    on POSIX the folder must be a real directory that this user owns and that
    no one else can open. Windows gives each user their own temp folder.
    """
    getuid = getattr(os, "getuid", None)
    if getuid is None:
        folder = os.path.join(tempfile.gettempdir(), "termaid-claude-hook")
        try:
            os.makedirs(folder, exist_ok=True)
        except OSError:
            return None
        return folder
    folder = os.path.join(tempfile.gettempdir(), f"termaid-claude-hook-{getuid()}")
    try:
        os.makedirs(folder, mode=0o700, exist_ok=True)
        info = os.lstat(folder)
    except OSError:
        return None
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != getuid() or info.st_mode & 0o077:
        return None
    return folder


def _state_path(folder: str, message_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", message_id)[:80]
    return os.path.join(folder, safe + ".json")


def _write_state(path: str, data: str) -> None:
    """Write through a temp file, so a later call never reads half a file."""
    tmp = f"{path}.{os.getpid()}.tmp"
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, path)


def run_claude_hook(stdin=None, stdout=None, *, width: int | None = None, use_ascii: bool = False) -> int:
    """Handle one MessageDisplay call: read the batch, print the replacement.

    State is kept per ``message_id`` in a private folder under the temp
    directory so a fence that spans several batches is still drawn. A batch
    that holds lines back returns an empty ``displayContent``; the drawing
    comes with the batch that closes the fence. Any failure prints nothing,
    and Claude Code then shows the original text. That includes a state
    folder that another user could read or write.
    """
    stdin = stdin or sys.stdin
    stdout = stdout or sys.stdout
    try:
        event = json.load(stdin)
    except (ValueError, OSError):
        return 0
    if event.get("hook_event_name") not in (None, "MessageDisplay"):
        return 0
    delta = event.get("delta") or ""
    final = bool(event.get("final", True))
    message_id = str(event.get("message_id") or "")

    renderer = StreamRenderer(width=width, use_ascii=use_ascii)
    path = None
    if message_id:
        folder = _state_dir()
        if folder is None:
            return 0
        path = _state_path(folder, message_id)
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                renderer.load(f.read())
        except (OSError, ValueError):
            pass

    shown = renderer.feed(delta, final=final)

    if path:
        if final or not (renderer.fence or renderer.carry):
            try:
                os.remove(path)
            except OSError:
                pass
        else:
            try:
                _write_state(path, renderer.to_json())
            except OSError:
                return 0

    json.dump({"hookSpecificOutput": {"hookEventName": "MessageDisplay", "displayContent": shown}}, stdout)
    stdout.write("\n")
    return 0
