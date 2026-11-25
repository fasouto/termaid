"""Sequence diagrams wrap their labels when render() gets max_label_width."""
from __future__ import annotations

from pathlib import Path

import pytest

from termaid import render
from termaid.utils import display_width

FIXTURES = Path(__file__).parent / "fixtures"
SEQUENCE_FIXTURES = sorted((FIXTURES / "sequence").glob("*.mmd"))
# Glyphs that would mean a label or arrow was merged into a lifeline.
BOX_JUNCTIONS = set("┼┬┴├┤")


def _widest(text: str) -> int:
    return max(display_width(line) for line in text.splitlines())


def _row_of(text: str, needle: str, start: int = 0) -> int:
    return next(i for i, line in enumerate(text.splitlines()) if i >= start and needle in line)


def _lifeline_columns(text: str) -> set[int]:
    """Columns that carry a lifeline glyph on at least two rows."""
    seen: dict[int, int] = {}
    for line in text.splitlines():
        for col, ch in enumerate(line):
            if ch in "┆║":
                seen[col] = seen.get(col, 0) + 1
    return {col for col, count in seen.items() if count >= 2}


@pytest.mark.parametrize("kind", ["participant", "actor", "database", "queue", "boundary", "control", "entity", "collections"])
def test_participant_label_wraps_and_header_grows(kind):
    source = f"sequenceDiagram\n  {kind} A as Customer Support Agent\n  A->>A: ping"
    plain = render(source)
    wrapped = render(source, max_label_width=8)
    rows = wrapped.splitlines()
    assert "Customer Support Agent" in plain
    assert _row_of(wrapped, "Customer") < _row_of(wrapped, "Support") < _row_of(wrapped, "Agent")
    assert len(rows) == len(plain.splitlines()) + 2
    assert _widest(wrapped) < _widest(plain)


def test_message_label_wraps_and_arrow_moves_down():
    source = "sequenceDiagram\n  A->>B: one two three four five six"
    plain = render(source)
    wrapped = render(source, max_label_width=9)
    rows = wrapped.splitlines()
    label_col = plain.splitlines()[_row_of(plain, "one two")].index("one two")
    arrow_row = _row_of(wrapped, "►")
    assert arrow_row == _row_of(plain, "►") + 3
    for offset, line in enumerate(["one two", "three", "four five", "six"]):
        row = rows[arrow_row - 4 + offset]
        assert row[label_col:label_col + len(line)] == line
    assert _widest(wrapped) < _widest(plain)


def test_self_message_label_wraps_above_its_loop():
    source = "sequenceDiagram\n  A->>A: alpha beta gamma delta"
    wrapped = render(source, max_label_width=11)
    label_row = _row_of(wrapped, "gamma delta")
    assert label_row == _row_of(wrapped, "alpha beta") + 1
    assert _row_of(wrapped, "┐", start=label_row) == label_row + 1


def test_note_wraps():
    source = "sequenceDiagram\n  A->>B: hi\n  Note over A,B: alpha beta gamma delta"
    plain = render(source)
    wrapped = render(source, max_label_width=11)
    assert "alpha beta gamma delta" in plain
    assert _row_of(wrapped, "gamma delta") == _row_of(wrapped, "alpha beta") + 1
    assert len(wrapped.splitlines()) == len(plain.splitlines()) + 1


def test_frame_title_and_section_wrap_without_widening_the_frame():
    body = "    A->>B: hi\n  else {section}\n    B-->>A: no\n  end"
    long_labels = "sequenceDiagram\n  alt the customer exists and has an order on file\n" + body.format(
        section="no such customer in the primary database")
    short_labels = "sequenceDiagram\n  alt ok\n" + body.format(section="no")
    wrapped = render(long_labels, max_label_width=10)
    reference = render(short_labels, max_label_width=10)
    assert _widest(wrapped) == _widest(reference)
    assert wrapped.splitlines()[_row_of(wrapped, "┐")] == reference.splitlines()[_row_of(reference, "┐")]
    assert "[alt] the customer" in wrapped
    assert "[no such" in wrapped
    assert "database]" in wrapped
    assert "".join(wrapped.split()).count("order") == 1


def test_autonumber_prefix_stays_on_the_first_line():
    source = "sequenceDiagram\n  autonumber\n  A->>B: alpha beta gamma"
    wrapped = render(source, max_label_width=10)
    assert "1: alpha" in wrapped
    assert wrapped.count("1:") == 1
    assert _row_of(wrapped, "beta") == _row_of(wrapped, "1: alpha") + 1


@pytest.mark.parametrize("width", [6, 10, 14])
@pytest.mark.parametrize("path", SEQUENCE_FIXTURES, ids=[p.stem for p in SEQUENCE_FIXTURES])
def test_wrapping_never_merges_labels_into_lifelines(path, width):
    source = path.read_text(encoding="utf-8").strip()
    wrapped = render(source, max_label_width=width)
    rows = wrapped.splitlines()
    columns = _lifeline_columns(wrapped)
    assert columns
    for row in rows:
        for col in columns:
            if col < len(row):
                assert row[col] not in BOX_JUNCTIONS, f"{row[col]!r} at column {col} of {row!r}"


@pytest.mark.parametrize("width", range(4, 24, 3))
def test_wrapped_labels_crossing_lifelines_draw_no_markers(width):
    source = (
        "sequenceDiagram\n"
        "  autonumber\n"
        "  participant Gateway\n  participant Auth\n  participant Orders\n"
        "  Gateway->>Orders: please fetch the complete order history for this customer\n"
        "  Orders-->>Gateway: the rows, or an empty list when nothing matched\n"
        "  alt the customer has at least one order on file\n"
        "    Auth->>Orders: validate the token and the session\n"
        "  else nothing was found\n"
        "    Orders->>Orders: log the miss and emit a metric\n"
        "  end\n"
        "  Note over Gateway,Orders: the query runs against the replica under load\n"
    )
    wrapped = render(source, max_label_width=width)
    assert "x" not in wrapped
    rows = wrapped.splitlines()
    for row in rows:
        for col in _lifeline_columns(wrapped):
            if col < len(row):
                assert row[col] not in BOX_JUNCTIONS


@pytest.mark.parametrize("path", SEQUENCE_FIXTURES, ids=[p.stem for p in SEQUENCE_FIXTURES])
def test_no_max_label_width_matches_snapshot(path):
    expected = (FIXTURES / "expected" / "sequence" / f"{path.stem}.txt").read_text(encoding="utf-8").rstrip("\n")
    assert render(path.read_text(encoding="utf-8").strip(), max_label_width=None) == expected


def test_identifier_labels_keep_member_name_together():
    output = render("sequenceDiagram\nparticipant A as metadata_shard[s].mutex\nA->>A: work", max_label_width=20)
    assert "metadata_shard[s]" in output and ".mutex" in output
    assert "metadata_shard[s].mu" not in output


@pytest.mark.parametrize("note", [
    "Note right of Database: row written to the orders table",
    "Note left of Client: the client keeps the order id for later",
    "Note over Database: the row is written to the orders table",
])
def test_fitting_to_a_width_wraps_an_edge_note_before_participant_names(tmp_path, capsys, note):
    from termaid.cli import main
    mmd = tmp_path / "seq.mmd"
    mmd.write_text(
        "sequenceDiagram\n  Client->>Server: POST /orders\n  Server->>Database: INSERT order\n  " + note
    )
    assert main([str(mmd), "--width", "40", "--strict-width"]) == 0
    out = capsys.readouterr().out
    assert all(name in out for name in ("Client", "Server", "Database", "/orders", "INSERT"))
    note_rows = [line[line.index("│") + 1:line.rindex("│")] for line in out.splitlines()[3:] if line.count("│") >= 2]
    assert "".join(note.split(": ", 1)[1].split()) in "".join("".join(note_rows).split())
