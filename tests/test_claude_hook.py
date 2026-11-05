"""The Claude Code MessageDisplay hook and the stream renderer behind it."""
from __future__ import annotations

import io
import json
import os
import stat

import pytest

from termaid.claude_hook import StreamRenderer, run_claude_hook


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


def _run(delta: str, **kw) -> str:
    out = io.StringIO()
    rc = run_claude_hook(io.StringIO(_event(delta, **kw)), out, width=60)
    assert rc == 0
    return json.loads(out.getvalue())["hookSpecificOutput"]["displayContent"]


def test_hook_keeps_fence_state_between_calls(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    mid = "11111111-2222-3333-4444-555555555555"
    assert _run("Flow:\n```mermaid\ngraph LR\n", message_id=mid, index=0, final=False) == "Flow:\n"
    assert len(list(tmp_path.glob(f"termaid-claude-hook*/{mid}.json"))) == 1
    drawn = _run("  A --> B\n```\nok\n", message_id=mid, index=1, final=False)
    assert drawn.startswith("```\n") and drawn.endswith("ok\n")
    assert list(tmp_path.glob(f"termaid-claude-hook*/{mid}.json")) == []
    assert _run("", message_id=mid, index=2, final=True) == ""


def test_hook_single_call_mode_draws_whole_message(tmp_path, monkeypatch):
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    out = _run("a\n" + FLOW + "b", message_id="m", index=0, final=True)
    assert out.startswith("a\n```\n") and out.endswith("```\nb")


def test_hook_ignores_bad_input():
    out = io.StringIO()
    assert run_claude_hook(io.StringIO("not json"), out) == 0
    assert out.getvalue() == ""


def test_cli_flag_runs_the_hook(monkeypatch, capsys):
    from termaid.cli import main

    monkeypatch.setattr("sys.stdin", io.StringIO(_event("x\n", message_id="c", index=0, final=True)))
    assert main(["--claude-hook"]) == 0
    assert json.loads(capsys.readouterr().out)["hookSpecificOutput"]["displayContent"] == "x\n"


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
    batches = ["```mermaid\n", "graph LR\n", "  A --> B\n", "```\nok\n"]
    shown = [_run(delta, message_id="m", index=i, final=i == 3) for i, delta in enumerate(batches)]
    assert "".join(shown) == "".join(batches)
    assert list(tmp_path.glob("termaid-claude-hook*/*")) == []


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
