

def test_a_note_with_nothing_beside_it_does_not_widen_other_rows():
    """Room for a note is kept only where a box sits beside it; a note at
    the end of its row takes blank cells and pushes nothing else apart."""
    from termaid import render
    src = "stateDiagram-v2\n  Idle --> Busy\n  state Busy {\n    direction LR\n    Load --> Run\n  }\n"
    plain = render(src)
    noted = render(src + "  note right of Idle : waits for a job\n")
    assert "waits for a job" in noted
    width = lambda text: max(map(len, text.split("\n")))
    assert width(noted) <= width(plain)
    load_to_run = lambda text: next(line for line in text.split("\n") if "Load" in line and "Run" in line)
    assert load_to_run(noted).strip() == load_to_run(plain).strip()
