"""The Claude Code MessageDisplay hook and the stream renderer behind it."""
from __future__ import annotations

import io
import json
import os
import stat
import subprocess
import sys
import threading
import time

import pytest

from termaid.claude_hook import StreamRenderer, run_claude_hook
from termaid.utils import display_width


FLOW = "```mermaid\ngraph LR\n  A[Start] --> B[End]\n```\n"


def test_text_without_diagrams_passes_through_unchanged():
    r = StreamRenderer(width=60)
    assert r.feed("Hello\n\n- one\n- two\n") == "Hello\n\n- one\n- two\n"


def test_complete_fence_in_one_batch_is_drawn_in_a_code_block():
    out = StreamRenderer(width=60).feed("Before\n" + FLOW + "After\n")
    assert out.startswith("Before\n```\n")
    assert "Start" in out and "End" in out and "►" in out
    assert "graph LR" not in out
    assert out.endswith("```\nAfter\n")


def test_fence_spanning_batches_is_held_then_drawn():
    r = StreamRenderer(width=60)
    assert r.feed("Here:\n\n```mermaid\ngraph LR\n") == "Here:\n\n"
    assert r.fence == "```"
    second = r.feed("  A --> B\n```\n\nDone.\n")
    assert second.startswith("```\n") and "Done." in second
    assert r.fence == "" and r.held == []


def test_mid_line_batch_is_carried_until_the_line_completes():
    r = StreamRenderer(width=60)
    assert r.feed("```mer") == ""
    assert r.carry == "```mer"
    assert r.feed("maid\ngraph LR\n  A --> B\n```\n").startswith("```\n")


def test_final_batch_ending_mid_line_keeps_no_trailing_newline():
    r = StreamRenderer(width=60)
    assert r.feed("last words", final=True) == "last words"


def test_unclosed_fence_is_shown_as_written_on_final():
    r = StreamRenderer(width=60)
    r.feed("```mermaid\ngraph TD\n")
    assert r.feed("  X --> Y\n", final=True) == "```mermaid\ngraph TD\n  X --> Y\n"
    assert r.fence == ""


def test_indented_fence_keeps_its_indentation():
    out = StreamRenderer(width=60).feed("1. step\n\n   ```mermaid\n   graph LR\n     A --> B\n   ```\n")
    body = out.split("\n")[2:]
    assert body[0] == "   ```"
    assert all(line.startswith("   ") for line in body if line)


def test_other_code_fences_are_left_alone():
    text = "```python\nprint('graph LR')\n```\n"
    assert StreamRenderer(width=60).feed(text) == text


def test_block_that_cannot_be_drawn_is_shown_as_source():
    text = "```mermaid\nthis is not a diagram\n```\n"
    assert StreamRenderer(width=60).feed(text) == text


def test_state_round_trips_through_json():
    r = StreamRenderer(width=60)
    r.feed("```mermaid\ngraph LR\n")
    saved = r.to_json()
    fresh = StreamRenderer(width=60)
    fresh.load(saved)
    assert fresh.feed("  A --> B\n```\n").startswith("```\n")


def _event(delta: str, *, message_id: str, index: int, final: bool) -> str:
    return json.dumps({
        "session_id": "s", "transcript_path": "/t", "cwd": ".",
        "hook_event_name": "MessageDisplay", "turn_id": "t",
        "message_id": message_id, "index": index, "final": final, "delta": delta,
    })


def _run(delta: str, width: int | None = 60, **kw) -> str:
    out = io.StringIO()
    rc = run_claude_hook(io.StringIO(_event(delta, **kw)), out, width=width)
    assert rc == 0
    return json.loads(out.getvalue())["hookSpecificOutput"]["displayContent"]


def test_hook_keeps_fence_state_between_calls(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    mid = "11111111-2222-3333-4444-555555555555"
    assert _run("Flow:\n```mermaid\ngraph LR\n", message_id=mid, index=0, final=False) == "Flow:\n"
    assert len(list(tmp_path.glob(f"termaid-claude-hook*/{mid}.json"))) == 1
    drawn = _run("  A --> B\n```\nok\n", message_id=mid, index=1, final=False)
    assert drawn.startswith("```\n") and drawn.endswith("ok\n")
    assert _run("", message_id=mid, index=2, final=True) == ""
    assert list(tmp_path.glob(f"termaid-claude-hook*/{mid}.json")) == []


def test_hook_draws_a_fence_whose_batches_run_out_of_order(tmp_path, monkeypatch):
    # Claude Code can start the hook for batch 1 before the one for batch 0 saves its state.
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    mid = "out-of-order"
    later: list[str] = []
    second = threading.Thread(target=lambda: later.append(
        _run("  A --> B\n```\n", message_id=mid, index=1, final=True)))
    second.start()
    time.sleep(0.05)
    assert _run("```mermaid\ngraph LR\n", message_id=mid, index=0, final=False) == ""
    second.join()
    assert later[0].startswith("```\n") and "graph LR" not in later[0]


def test_hook_stops_waiting_for_a_batch_that_never_comes(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr("termaid.claude_hook._WAIT_SECONDS", 0.05)
    assert _run("tail\n", message_id="lost-batch", index=3, final=True) == "tail\n"


def test_a_replayed_message_starts_from_its_first_batch(tmp_path, monkeypatch):
    # Claude Code can send a message id again after an interrupt or a resume.
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    assert _run("```mermaid\ngraph LR\n", message_id="again", index=0, final=False) == ""
    assert _run("Hello\n", message_id="again", index=0, final=False) == "Hello\n"
    assert _run("Bye\n", message_id="again", index=1, final=True) == "Bye\n"


SPLIT_MESSAGES = [
    "Intro\n```mermaid\ngraph LR\n  A --> B\n```\nAfter.\n",
    "1. step\n\n   ```mermaid\n   graph TD\n     X --> Y\n   ```\nend",
    "```mermaid\ngraph LR\n  A --> B\n```\n```mermaid\ngraph LR\n  C --> D\n```\nok\n",
    "```python\n```mermaid\n```\n~~~mermaid\ngraph LR\n  E --> F\n~~~\n",
    "Open\n```mermaid\ngraph LR\n  A --> B\n",
]


@pytest.mark.parametrize("message", SPLIT_MESSAGES)
def test_a_message_split_anywhere_shows_as_if_it_came_whole(tmp_path, monkeypatch, message):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    whole = _run(message, message_id="whole", index=0, final=True)
    for cut in range(len(message) + 1):
        mid = f"cut-{cut}"
        shown = _run(message[:cut], message_id=mid, index=0, final=False)
        shown += _run(message[cut:], message_id=mid, index=1, final=True)
        assert shown == whole, f"split at {cut}"


@pytest.mark.parametrize("message", SPLIT_MESSAGES[:3])
def test_a_slow_drawing_does_not_hold_up_the_batches_after_it(tmp_path, monkeypatch, message):
    import termaid
    from termaid import claude_hook

    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    whole = _run(message, message_id="whole", index=0, final=True)
    real_render = termaid.render
    monkeypatch.setattr(termaid, "render", lambda *a, **k: time.sleep(0.3) or real_render(*a, **k))
    monkeypatch.setattr(claude_hook, "_WAIT_SECONDS", 0.15)
    batches = message.splitlines(keepends=True) + [""]
    shown: list[str] = [""] * len(batches)

    def run(i: int) -> None:
        shown[i] = _run(batches[i], message_id="slow", index=i, final=i == len(batches) - 1)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(len(batches))]
    # Batches 1, 0, 3, 2, ... start in that order, a little apart, as Claude Code can start them.
    for i in range(0, len(threads), 2):
        for thread in reversed(threads[i:i + 2]):
            thread.start()
            time.sleep(0.01)
    for thread in threads:
        thread.join()
    assert "".join(shown) == whole


def test_a_batch_that_runs_late_does_not_undo_the_batches_after_it(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr("termaid.claude_hook._WAIT_SECONDS", 0.05)
    shown = [_run("Intro\n", message_id="late", index=0, final=False)]
    # Batch 2 gives up waiting for batch 1, which only starts afterwards.
    shown.append(_run("B\n", message_id="late", index=2, final=False))
    shown.insert(1, _run("```mermaid\n", message_id="late", index=1, final=False))
    shown.append(_run("end\n", message_id="late", index=3, final=True))
    assert "".join(shown) == "Intro\n```mermaid\nB\nend\n"


def test_hook_single_call_mode_draws_whole_message(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    out = _run("a\n" + FLOW + "b", message_id="m", index=0, final=True)
    assert out.startswith("a\n```\n") and out.endswith("```\nb")


LONG_LABELS = (
    "sequenceDiagram\n"
    "  participant Gateway\n  participant Orders\n"
    "  Gateway->>Orders: please fetch the complete order history for this customer\n"
    "  Orders-->>Gateway: the rows, or an empty list when nothing matched\n"
)
TOO_WIDE = "graph LR\n  " + " --> ".join(f"N{i}" for i in range(30)) + "\n"


def _fenced(source: str) -> str:
    return "Before\n```mermaid\n" + source + "```\nAfter\n"


def _widest(text: str) -> int:
    return max(display_width(line) for line in text.split("\n"))


def test_hook_wraps_long_labels_to_fit_the_width(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    out = _run(_fenced(LONG_LABELS), message_id="m", index=0, final=True)
    assert "```mermaid" not in out and "history" in out
    assert _widest(out) <= 60


@pytest.mark.parametrize("env, width", [({"COLUMNS": "44"}, None), ({}, 40)])
def test_hook_leaves_a_diagram_too_wide_for_a_known_width_as_source(tmp_path, monkeypatch, env, width):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.delenv("COLUMNS", raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    text = _fenced(TOO_WIDE)
    assert _run(text, width=width, message_id="m", index=0, final=True) == text


def test_hook_still_draws_a_wide_diagram_when_the_width_is_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.delenv("COLUMNS", raising=False)
    out = _run(_fenced(TOO_WIDE), width=None, message_id="m", index=0, final=True)
    assert "```mermaid" not in out and "N29" in out
    assert _widest(out) > 80


LOOPS_BACK = """flowchart TD
    A[Push to main] --> B[Run tests]
    B --> C{Tests pass?}
    C -- no --> D[Notify author]
    D --> E[Fix and push]
    E --> B
    C -- yes --> F[Build image]
    F --> G[Deploy to staging]
    G --> H{Smoke test ok?}
    H -- no --> I[Roll back staging]
    I --> D
    H -- yes --> J{Needs approval?}
    J -- yes --> K[Wait for reviewer]
    K --> L{Approved?}
    L -- no --> D
    L -- yes --> M[Deploy to production]
    J -- no --> M
    M --> N{Healthy after 10 min?}
    N -- no --> O[Roll back production]
    O --> D
    N -- yes --> P[Done]
"""


def test_hook_routes_only_the_drawings_that_may_fit(tmp_path, monkeypatch):
    from functools import partial

    import termaid.routing.router as router
    from termaid import render
    from termaid.utils import fit_to_width

    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    passes = []
    route_edges = router.route_edges
    monkeypatch.setattr(router, "route_edges", lambda *a: passes.append(a) or route_edges(*a))
    out = _run(_fenced(LOOPS_BACK), width=100, message_id="m", index=0, final=True)
    # Drawing every candidate the fit tries routed this diagram 26 times.
    assert len(passes) <= 8
    draw = partial(render, LOOPS_BACK)
    assert out == "Before\n```\n" + fit_to_width(draw, draw(), 100) + "\n```\nAfter\n"


def test_hook_ignores_bad_input():
    out = io.StringIO()
    assert run_claude_hook(io.StringIO("not json"), out) == 0
    assert out.getvalue() == ""


def test_cli_flag_runs_the_hook(monkeypatch, capsys):
    from termaid.cli import main

    monkeypatch.setattr("sys.stdin", io.StringIO(_event("x\n", message_id="c", index=0, final=True)))
    assert main(["--claude-hook"]) == 0
    assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]["displayContent"] == "x\n"


def test_text_without_a_diagram_loads_none_of_the_drawing_code(tmp_path):
    # The hook starts for every batch of every reply, so its start-up is
    # paid even when there is nothing to draw.
    import termaid

    script = (
        "import sys\n"
        "from termaid.cli import main\n"
        "code = main(['--claude-hook'])\n"
        "sys.stderr.write(' '.join(sorted(sys.modules)))\n"
        "sys.exit(code)\n"
    )
    env = dict(os.environ, PYTHONPATH=os.path.dirname(os.path.dirname(termaid.__file__)), TMPDIR=str(tmp_path))
    done = subprocess.run(
        [sys.executable, "-c", script],
        input=_event("Plain text.\n", message_id="lean", index=0, final=False),
        capture_output=True, text=True, env=env, check=True,
    )
    assert json.loads(done.stdout)["hookSpecificOutput"]["displayContent"] == "Plain text.\n"
    heavy = ("termaid.graph", "termaid.parser", "termaid.renderer", "termaid.layout",
             "termaid.routing", "termaid.output", "rich", "importlib.metadata", "dataclasses")
    assert [name for name in done.stderr.split() if name.startswith(heavy)] == []


posix_only = pytest.mark.skipif(not hasattr(os, "getuid"), reason="POSIX permissions")


def _open_fence(mid: str = "m1") -> str:
    out = io.StringIO()
    run_claude_hook(io.StringIO(_event("```mermaid\ngraph LR\n", message_id=mid, index=0, final=False)), out)
    return out.getvalue()


@posix_only
def test_state_is_private_to_the_user(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    old_umask = os.umask(0)
    try:
        assert json.loads(_open_fence())["hookSpecificOutput"]["displayContent"] == ""
    finally:
        os.umask(old_umask)
    folder = tmp_path / f"termaid-claude-hook-{os.getuid()}"
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    assert stat.S_IMODE((folder / "m1.json").stat().st_mode) == 0o600
    assert sorted(p.name for p in folder.iterdir()) == ["m1.json"]


@posix_only
def test_a_folder_others_can_open_is_not_used(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    folder = tmp_path / f"termaid-claude-hook-{os.getuid()}"
    folder.mkdir(mode=0o755)
    folder.chmod(0o755)
    assert _open_fence() == ""
    assert list(folder.iterdir()) == []


@posix_only
def test_a_symlinked_folder_is_not_used(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    target = tmp_path / "elsewhere"
    target.mkdir(mode=0o700)
    (tmp_path / f"termaid-claude-hook-{os.getuid()}").symlink_to(target)
    assert _open_fence() == ""
    assert list(target.iterdir()) == []



@posix_only
@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root ignores modes")
def test_a_state_folder_it_cannot_write_shows_the_reply_as_written(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    folder = tmp_path / f"termaid-claude-hook-{os.getuid()}"
    folder.mkdir(mode=0o500)
    folder.chmod(0o500)
    try:
        assert json.loads(_open_fence())["hookSpecificOutput"]["displayContent"] == "```mermaid\ngraph LR\n"
    finally:
        folder.chmod(0o700)


@posix_only
def test_a_folder_owned_by_another_user_is_not_used(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    other = os.getuid() + 1
    monkeypatch.setattr(os, "getuid", lambda: other)
    assert _open_fence() == ""
    assert list(tmp_path.glob("termaid-claude-hook*/*")) == []


@posix_only
def test_a_folder_the_group_can_open_is_not_used(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    folder = tmp_path / f"termaid-claude-hook-{os.getuid()}"
    folder.mkdir()
    folder.chmod(0o770)
    assert _open_fence() == ""
    assert list(folder.iterdir()) == []


@posix_only
def test_a_private_symlink_is_not_used_as_the_folder(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    target = tmp_path / "elsewhere"
    target.mkdir(mode=0o700)
    old_umask = os.umask(0o077)
    try:
        (tmp_path / f"termaid-claude-hook-{os.getuid()}").symlink_to(target)
    finally:
        os.umask(old_umask)
    assert _open_fence() == ""
    assert list(target.iterdir()) == []


@posix_only
def test_a_failed_save_leaves_no_temp_file(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    def fail(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail)
    assert json.loads(_open_fence())["hookSpecificOutput"]["displayContent"] == "```mermaid\ngraph LR\n"
    assert list(tmp_path.glob("termaid-claude-hook*/*")) == []


@posix_only
def test_a_failed_save_mid_message_shows_the_reply_as_written(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    real_replace = os.replace
    saves = []

    def fail_second_save(src, dst):
        saves.append(dst)
        if len(saves) == 2:
            raise OSError("disk full")
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_second_save)
    # The batch after the failed save waits for state that never comes.
    monkeypatch.setattr("termaid.claude_hook._WAIT_SECONDS", 0.05)
    batches = ["```mermaid\n", "graph LR\n", "  A --> B\n", "```\nok\n"]
    shown = [_run(delta, message_id="m", index=i, final=i == 3) for i, delta in enumerate(batches)]
    assert "".join(shown) == "".join(batches)
    assert list(tmp_path.glob("termaid-claude-hook*/*")) == []


def test_a_save_retries_while_another_batch_has_the_file_open(tmp_path, monkeypatch):
    # Windows refuses to replace a file that a waiting batch has open for reading.
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    real_replace = os.replace
    refusals = []

    def busy_once(src, dst):
        if not refusals:
            refusals.append(dst)
            raise PermissionError(13, "The process cannot access the file")
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", busy_once)
    assert json.loads(_open_fence())["hookSpecificOutput"]["displayContent"] == ""
    assert refusals and len(list(tmp_path.glob("termaid-claude-hook*/m1.json"))) == 1


def test_no_usable_temp_folder_shows_the_reply_as_written(monkeypatch):
    def no_temp_folder():
        raise FileNotFoundError("No usable temporary directory")

    monkeypatch.setattr("tempfile.gettempdir", no_temp_folder)
    assert _open_fence() == ""

def test_state_folder_without_getuid(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.delattr(os, "getuid", raising=False)
    assert json.loads(_open_fence())["hookSpecificOutput"]["displayContent"] == ""
    assert (tmp_path / "termaid-claude-hook" / "m1.json").exists()


def _feed_lines(renderer: StreamRenderer, lines: list[str]) -> list[str]:
    return [renderer.feed(line + "\n") for line in lines]


LONG_LINES = [f"  line {i:04d} " + "x" * 60 for i in range(200)]


def test_unclosed_fence_is_shown_once_it_passes_the_limit():
    r = StreamRenderer(width=80)
    shown = _feed_lines(r, ["```mermaid", *LONG_LINES])
    first = next(i for i, out in enumerate(shown) if out)
    assert 100 < first < 130
    assert "".join(shown) == "".join(line + "\n" for line in ["```mermaid", *LONG_LINES])
    assert not r.fence


def test_saved_state_stays_under_the_limit():
    r = StreamRenderer(width=80)
    for line in ["```mermaid", *LONG_LINES]:
        r.feed(line + "\n")
        assert len(r.to_json()) < 10_000


def test_one_line_past_the_limit_is_shown_at_once():
    r = StreamRenderer(width=80)
    assert r.feed("```mermaid\n") == ""
    long_line = "x" * 10_000
    assert r.feed(long_line + "\n") == "```mermaid\n" + long_line + "\n"


def test_a_large_closed_diagram_under_the_limit_is_drawn():
    padding = [f"%% {'pad ' * 15}{i}" for i in range(110)]
    source = ["```mermaid", "graph LR", *padding, "  A --> B", "```"]
    assert sum(len(line) for line in source) > 7_000
    out = "".join(_feed_lines(StreamRenderer(width=80), source))
    assert "```mermaid" not in out and "─" in out


def test_a_fence_after_a_released_one_is_still_drawn():
    r = StreamRenderer(width=80)
    _feed_lines(r, ["```mermaid", *LONG_LINES, "text"])
    out = r.feed(FLOW + "after\n", final=True)
    assert "```mermaid" not in out and "─" in out and out.endswith("after\n")


def test_blank_lines_count_toward_the_limit():
    r = StreamRenderer(width=80)
    lines = ["```mermaid", *[""] * 9_000]
    shown = _feed_lines(r, lines)
    assert any(shown[:-100]), "a fence of blank lines should be released before it ends"
    assert "".join(shown) == "".join(line + "\n" for line in lines)


def test_hook_shows_an_unclosed_fence_before_the_message_ends(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    batches = ["```mermaid\n", *(line + "\n" for line in LONG_LINES), "end\n"]
    shown = [_run(delta, message_id="long", index=i, final=i == len(batches) - 1) for i, delta in enumerate(batches)]
    assert any(shown[:150])
    assert "".join(shown) == "".join(batches)
    assert list(tmp_path.glob("termaid-claude-hook*/long.json")) == []


def test_a_renderer_built_with_held_lines_counts_them():
    r = StreamRenderer(width=80, fence="```", held=["```mermaid", *LONG_LINES[:112]])
    assert r.feed(LONG_LINES[112] + "\n").startswith("```mermaid\n")


def test_a_render_that_outlasts_the_limit_is_shown_as_source(monkeypatch):
    """Claude Code kills the hook at 10 s; a slow render must not leave the fence open."""
    import time

    import termaid
    from termaid import claude_hook

    monkeypatch.setattr(claude_hook, "_RENDER_SECONDS", 0.05)
    monkeypatch.setattr(termaid, "render", lambda *a, **k: time.sleep(1) or "late")
    r = StreamRenderer(width=60)
    assert r.feed("Before\n```mermaid\ngraph LR\n", final=False) == "Before\n"
    assert r.feed("  A --> B\n```\nAfter\n", final=False) == "```mermaid\ngraph LR\n  A --> B\n```\nAfter\n"
    assert not r.fence
    assert r.feed("More\n", final=True) == "More\n"


def test_the_render_limit_covers_every_diagram_in_a_batch(tmp_path, monkeypatch):
    """Three diagrams that each fit the limit must not add up to more than it."""
    import termaid
    from termaid import claude_hook

    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    real_render = termaid.render
    monkeypatch.setattr(termaid, "render", lambda *a, **k: time.sleep(0.2) or real_render(*a, **k))
    monkeypatch.setattr(claude_hook, "_RENDER_SECONDS", 0.3)
    blocks = [f"```mermaid\ngraph LR\n  A{i} --> B{i}\n```\n" for i in range(3)]
    start = time.monotonic()
    out = _run("".join(blocks), message_id="three", index=0, final=False)
    assert time.monotonic() - start < 0.45
    assert "A0" in out and "graph LR" not in out.split("A0")[0]
    assert out.endswith(blocks[1] + blocks[2])
