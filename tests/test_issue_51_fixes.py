"""Fixes from issue #51 that came in as pull requests #55 to #59."""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import time

from termaid import claude_hook, render
from termaid.claude_hook import StreamRenderer, run_claude_hook
from termaid.parser.statediagram import parse_state_diagram

# A locale that cannot encode box-drawing characters, as on Windows.
LATIN1 = {**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "latin-1", "LC_ALL": "C", "LANG": "C"}


def run_termaid(args: list[str], data: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "termaid", *args], input=data.encode("utf-8"),
        capture_output=True, env=LATIN1, timeout=60,
    )


def hook(payload) -> str:
    out = io.StringIO()
    run_claude_hook(io.StringIO(payload) if isinstance(payload, str) else payload, out)
    return out.getvalue()


def shown(payload) -> str:
    return json.loads(hook(payload))["hookSpecificOutput"]["displayContent"]


class TestUtf8WhateverTheLocale:
    def test_the_hook_reads_its_event_as_utf8(self):
        event = json.dumps({"delta": "café → ok\n", "final": True}, ensure_ascii=False)
        result = run_termaid(["--claude-hook"], event)
        assert json.loads(result.stdout)["hookSpecificOutput"]["displayContent"] == "café → ok\n"

    def test_the_cli_reads_and_writes_utf8_through_a_pipe(self):
        result = run_termaid([], "graph LR\n  A[café] --> B\n")
        assert result.returncode == 0, result.stderr
        out = result.stdout.decode("utf-8")
        assert "café" in out and "┌" in out


class TestHookState:
    def test_a_mermaid_block_inside_another_code_block_is_left_alone(self):
        quoted = "````markdown\nExample:\n```mermaid\ngraph LR\n  A --> B\n```\n````\n"
        out = StreamRenderer(width=60).feed(quoted + "Real:\n```mermaid\ngraph LR\n  A --> B\n```\n", final=True)
        assert out.startswith(quoted + "Real:\n```\n┌")

    def test_an_open_block_of_another_language_is_remembered_across_batches(self):
        r = StreamRenderer(width=60)
        first = r.feed("````markdown\n```mermaid\n", final=False)
        saved = r.to_json()
        r = StreamRenderer(width=60)
        r.load(saved)
        rest = r.feed("graph LR\n  A --> B\n```\n````\n", final=True)
        assert first + rest == "````markdown\n```mermaid\ngraph LR\n  A --> B\n```\n````\n"

    def test_a_batch_with_no_message_id_shows_its_lines_instead_of_dropping_them(self):
        assert shown(json.dumps({"delta": "text\n```mermaid\ngraph LR\n", "final": False})) == "text\n```mermaid\ngraph LR\n"

    def test_a_malformed_event_prints_nothing(self):
        for payload in ("[]", "null", json.dumps({"delta": 5}), "[" * 100_000):
            assert hook(payload) == ""

    def test_a_saved_state_of_the_wrong_shape_is_replaced(self, tmp_path, monkeypatch):
        monkeypatch.setattr(claude_hook, "_state_dir", lambda: str(tmp_path))
        path = claude_hook._state_path(str(tmp_path), "m1")
        for bad in ("[]", "null", '{"held": 5}'):
            with open(path, "w", encoding="utf-8") as f:
                f.write(bad)
            assert shown(json.dumps({"message_id": "m1", "delta": "plain\n", "final": False})) == "plain\n"
            assert not os.path.exists(path)

    def test_state_files_left_by_interrupted_messages_are_removed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(claude_hook, "_state_dir", lambda: str(tmp_path))
        old, recent = tmp_path / "old.json", tmp_path / "recent.json"
        old.write_text("{}")
        recent.write_text("{}")
        two_days_ago = time.time() - 2 * 24 * 60 * 60
        os.utime(old, (two_days_ago, two_days_ago))
        hook(json.dumps({"message_id": "m2", "delta": "done\n", "final": True}))
        assert not old.exists() and recent.exists()


class TestSequence:
    def test_an_activation_bar_starts_and_ends_with_its_own_messages(self):
        out = render("sequenceDiagram\n  A->>+B: req\n  B->>+C: sub\n  C-->>-B: resp\n  B-->>-A: done").split("\n")
        row = {name: next(i for i, line in enumerate(out) if f" {name}" in line) for name in ("sub", "resp", "done")}
        b_col, c_col = out[1].index("B"), out[1].index("C")
        assert out[row["sub"]][b_col] == "║"            # B is active once `req` has arrived
        assert out[row["resp"]][c_col] == "║"           # C is active until it replies
        assert out[row["done"]][c_col] == "┆"           # and not after
        assert out[row["done"] + 2][b_col] == "┆"       # B's bar ends with `done`

    def test_a_long_self_message_keeps_clear_of_the_next_lifeline(self):
        out = render("sequenceDiagram\n  A->>A: a very long self message label here\n  A->>B: hi").split("\n")
        b_col = out[1].index("B")
        label_row = next(line for line in out if "a very long" in line)
        assert label_row[b_col] == "┆" and label_row.rstrip().endswith("┆")

    def test_a_destroyed_participant_lives_until_the_message_that_destroys_it(self):
        out = render("sequenceDiagram\n  A->>B: work\n  destroy B\n  B-->>A: bye\n  A->>A: after")
        assert out.index("bye") < out.index("╳")

    def test_autonumber_takes_a_start_and_a_step(self):
        out = render("sequenceDiagram\n  autonumber 10 5\n  A->>B: one\n  B->>A: two\n  A->>B: three")
        assert "10: one" in out and "15: two" in out and "20: three" in out
        assert "1: one" in render("sequenceDiagram\n  autonumber\n  A->>B: one")


class TestStateDiagram:
    def test_a_composite_state_with_a_display_name_gets_its_frame(self):
        graph = parse_state_diagram('stateDiagram-v2\n  state "Long Name" as S1 {\n    a --> b\n  }\n  [*] --> S1')
        (composite,) = graph.subgraphs
        assert (composite.id, composite.label) == ("S1", "Long Name")
        assert set(composite.node_ids) == {"a", "b"}
        assert "│ Long Name" in render('stateDiagram-v2\n  state "Long Name" as S1 {\n    a --> b\n  }\n  [*] --> S1')

    def test_a_display_name_without_a_body_is_still_a_plain_state(self):
        graph = parse_state_diagram('stateDiagram-v2\n  state "Waiting for input" as W\n  [*] --> W')
        assert not graph.subgraphs and graph.nodes["W"].label == "Waiting for input"

    def test_a_class_suffix_on_a_transition_is_not_part_of_the_state_or_label(self):
        graph = parse_state_diagram("stateDiagram-v2\n  [*] --> X:::bad\n  Y:::bad --> [*]\n  X --> Y : go: now")
        assert {n for n in graph.nodes if not n.startswith("[*]")} == {"X", "Y"}
        assert [e.label for e in graph.edges] == ["", "", "go: now"]


class TestCommentsInBodies:
    def test_a_comment_line_in_a_class_body_is_not_a_member(self):
        out = render("classDiagram\n  class A {\n    %% a comment\n    +int x\n    +run() %% trailing\n  }")
        assert "a comment" not in out and "+int x" in out and "+run() %% trailing" in out

    def test_a_comment_line_in_an_entity_body_is_not_an_attribute(self):
        out = render('erDiagram\n  USER {\n    %% owner\n    string name "100%% sure"\n  }')
        assert "owner" not in out and "100%% sure" in out
