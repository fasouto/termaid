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
import threading
import time
from dataclasses import asdict, dataclass, field
from functools import partial

from .markdown import _OPEN, _dedent
from .utils import display_width, fit_to_width, max_line_width

_DEFAULT_WIDTH = 80
_MARGIN = 4  # Claude Code indents messages; keep diagrams clear of the edge
# A fence that never closes would hide the rest of the reply until it ends,
# and every batch saves the held lines again, so past this many characters
# they are shown as written.
_MAX_HELD_CHARS = 8_192
_RENDER_SECONDS = 3
# Claude Code can start the hook for a batch before the one for the batch
# before it has saved its state. Wait this long for that state, then go on
# without it. Recorded waits were under 0.1 seconds; the limit stays short
# because the text of the batch is held back for all of it, and it adds to
# the render limit inside the 10 seconds Claude Code gives the hook.
_WAIT_SECONDS = 1
# A message that is interrupted never sends its final batch, so its state
# file stays behind; one untouched for this long belongs to no live message.
_STALE_STATE_SECONDS = 24 * 60 * 60


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
    other_fence: str = ""  # an open block of another language, passed through unsearched
    held_size: int = field(default=0, init=False, repr=False, compare=False)  # held's characters, line breaks included

    def __post_init__(self) -> None:
        self.held_size = sum(len(line) + 1 for line in self.held)

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
            self.other_fence = ""
        return shown

    def _line(self, line: str) -> list[str]:
        if self.fence:
            self.held.append(line)
            self.held_size += len(line) + 1
            close = re.compile(
                r"^[ \t]*" + re.escape(self.fence[0]) + "{" + str(len(self.fence)) + r",}[ \t]*\r?$"
            )
            if not close.match(line):
                if self.held_size > _MAX_HELD_CHARS:
                    held = self.held
                    self._reset()
                    return held
                return []
            body = [_dedent(raw, len(self.indent)).rstrip("\r") for raw in self.held[1:-1]]
            drawn = self._draw("\n".join(body))
            held, self.held = self.held, []
            self._reset()
            return drawn if drawn is not None else held
        if self.other_fence:
            close = re.compile(
                r"^[ \t]*" + re.escape(self.other_fence[0]) + "{" + str(len(self.other_fence)) + r",}[ \t]*\r?$"
            )
            if close.match(line):
                self.other_fence = ""
            return [line]
        match = _OPEN.match(line)
        if match and not (match.group("fence")[0] == "`" and "`" in match.group("info")):
            words = match.group("info").split()
            if words and words[0].lower() == "mermaid":
                self.fence = match.group("fence")
                self.indent = match.group("indent")
                self.held = [line]
                self.held_size = len(line) + 1
                return []
            self.other_fence = match.group("fence")
        return [line]

    def _reset(self) -> None:
        self.fence = ""
        self.indent = ""
        self.held = []
        self.held_size = 0

    def _draw(self, source: str) -> list[str] | None:
        """Render one diagram, or None when it cannot be drawn."""
        from . import _layout_width, render

        if not source.strip():
            return None
        width = self.width
        # Claude Code sets COLUMNS to the pane width; older versions did not.
        columns = os.environ.get("COLUMNS", "").strip()
        known = width is not None or (columns.isdigit() and int(columns) > 0)
        if width is None:
            width = max(shutil.get_terminal_size((_DEFAULT_WIDTH, 24)).columns - _MARGIN, 20)
        width = max(width - display_width(self.indent), 20)
        result: list[str] = []

        def run() -> None:
            try:
                draw = partial(render, source, use_ascii=self.use_ascii)
                measure = partial(_layout_width, source)
                result.append(fit_to_width(draw, draw(), width, measure=measure))
            except Exception:
                pass

        # Claude Code kills the hook after 10 seconds, before it saves its
        # state, so a slower render is shown as source instead.
        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(_RENDER_SECONDS)
        if not result:
            return None
        text = result[0]
        # A drawing wider than the pane wraps into a garble; the source reads better.
        if not text.strip() or (known and max_line_width(text) > width):
            return None
        # A code fence keeps the box characters monospaced and unformatted
        # when the display renders Markdown.
        fence = "```"
        while fence in text:
            fence += "`"
        return [self.indent + fence] + [self.indent + ln for ln in text.split("\n")] + [self.indent + fence]

    def to_json(self) -> str:
        return json.dumps({k: v for k, v in asdict(self).items() if k in ("fence", "indent", "held", "carry", "other_fence")})

    def load(self, data: str) -> None:
        saved = json.loads(data)
        if not isinstance(saved, dict):
            raise ValueError("saved state is not a JSON object")
        held = saved.get("held", [])
        texts = [saved.get(key, "") for key in ("fence", "indent", "carry", "other_fence")]
        if not isinstance(held, list) or not all(isinstance(text, str) for text in texts + held):
            raise ValueError("saved state has the wrong shape")
        self.fence = saved.get("fence", "")
        self.indent = saved.get("indent", "")
        self.held = list(saved.get("held", []))
        self.held_size = sum(len(line) + 1 for line in self.held)
        self.carry = saved.get("carry", "")
        self.other_fence = saved.get("other_fence", "")


def _state_dir() -> str | None:
    """Return the folder that holds hook state, or None when it is not private.

    The temp folder is shared between users on Linux, and anyone can create a
    folder there first, then read the state or swap a file for a symlink. So
    on POSIX the folder must be a real directory that this user owns and that
    no one else can open. Windows gives each user their own temp folder.
    """
    getuid = getattr(os, "getuid", None)
    try:
        base = tempfile.gettempdir()
        if getuid is None:
            folder = os.path.join(base, "termaid-claude-hook")
            os.makedirs(folder, exist_ok=True)
            return folder
        folder = os.path.join(base, f"termaid-claude-hook-{getuid()}")
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


def _remove_stale_state(folder: str) -> None:
    cutoff = time.time() - _STALE_STATE_SECONDS
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                if not entry.name.endswith((".json", ".tmp")) or not entry.is_file(follow_symlinks=False):
                    continue
                try:
                    if entry.stat(follow_symlinks=False).st_mtime < cutoff:
                        os.remove(entry.path)
                except OSError:
                    pass
    except OSError:
        pass


def _batch_index(event: dict) -> int | None:
    index = event.get("index")
    if isinstance(index, bool) or not isinstance(index, int) or index < 0:
        return None
    return index


def _saved_index(data: str) -> int | None:
    try:
        saved = json.loads(data)
    except ValueError:
        return None
    return saved.get("next_index") if isinstance(saved, dict) else None


def _read_state_after(path: str, index: int | None) -> str | None:
    """Return the saved state once the batch before ``index`` has written it."""
    deadline = time.monotonic() + _WAIT_SECONDS
    while True:
        try:
            with open(path, encoding="utf-8") as f:
                data = f.read()
        except OSError:
            data = None
        if index is None or (data is not None and _saved_index(data) == index) or time.monotonic() >= deadline:
            return data
        time.sleep(0.005)


def _write_state(path: str, data: str) -> None:
    """Write through a temp file, so a later call never reads half a file."""
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def run_claude_hook(stdin=None, stdout=None, *, width: int | None = None, use_ascii: bool = False) -> int:
    """Handle one MessageDisplay call: read the batch, print the replacement.

    State is kept per ``message_id`` in a private folder under the temp
    directory so a fence that spans several batches is still drawn. A batch
    that holds lines back returns an empty ``displayContent``; the drawing
    comes with the batch that closes the fence. Any failure prints nothing,
    and Claude Code then shows the original text. That includes a state
    folder that another user could read or write. When the state can't be
    saved, the lines held so far are shown as written.
    """
    # Claude Code sends UTF-8, but sys.stdin decodes with the locale
    # encoding, so read the bytes and let json detect the encoding.
    stdin = stdin or getattr(sys.stdin, "buffer", sys.stdin)
    stdout = stdout or sys.stdout
    try:
        event = json.load(stdin)
    except (ValueError, OSError, RecursionError):
        return 0
    if not isinstance(event, dict) or event.get("hook_event_name") not in (None, "MessageDisplay"):
        return 0
    delta = event.get("delta") or ""
    if not isinstance(delta, str):
        return 0
    message_id = str(event.get("message_id") or "")
    index = _batch_index(event)
    # Without a message_id there is nowhere to keep held lines for the next batch.
    final = bool(event.get("final", True)) or not message_id

    renderer = StreamRenderer(width=width, use_ascii=use_ascii)
    path = None
    if message_id:
        folder = _state_dir()
        if folder is None:
            return 0
        path = _state_path(folder, message_id)
    # A first batch starts afresh: a file already there belongs to an earlier
    # run of the same message id, after an interrupt or a resume.
    saved = _read_state_after(path, index) if path and index != 0 else None
    if saved is not None:
        try:
            renderer.load(saved)
        except ValueError:
            pass

    shown = renderer.feed(delta, final=final)

    if path:
        holding = renderer.fence or renderer.other_fence or renderer.carry
        # The next batch waits for this one's state, so it is saved even when nothing is held.
        if final or (index is None and not holding):
            try:
                os.remove(path)
            except OSError:
                pass
            if final:
                _remove_stale_state(folder)
        else:
            try:
                state = json.loads(renderer.to_json())
                if index is not None:
                    state["next_index"] = index + 1
                _write_state(path, json.dumps(state))
            except OSError:
                # The next batch would resume from an older saved state, so
                # show what is held as written and drop that state.
                shown += renderer.feed("", final=True)
                try:
                    os.remove(path)
                except OSError:
                    pass

    json.dump({"hookSpecificOutput": {"hookEventName": "MessageDisplay", "displayContent": shown}}, stdout)
    stdout.write("\n")
    return 0
