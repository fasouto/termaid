"""The shared test set that other implementations of termaid are checked against."""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures"

# One fixture folder per diagram type termaid draws.
DIAGRAM_TYPES = {
    "flowcharts", "statediagram", "sequence", "classdiagram", "erdiagram", "blockdiagram",
    "gitgraph", "gantt", "xychart", "pie", "mindmap", "timeline", "kanban", "journey",
    "quadrant", "packet", "treemap", "architecture",
}


def _export(tmp_path):
    out = tmp_path / "corpus.jsonl"
    subprocess.run([sys.executable, str(REPO / "scripts" / "export_corpus.py"), str(out)], check=True)
    return [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]


def test_every_diagram_type_has_fixtures():
    folders = {p.name for p in FIXTURES.iterdir() if p.is_dir() and p.name != "expected"}
    assert folders == DIAGRAM_TYPES


def test_export_covers_every_fixture_and_matches_the_snapshots(tmp_path):
    cases = _export(tmp_path)
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids))
    assert {c["type"] for c in cases} == DIAGRAM_TYPES
    defaults = [c for c in cases if c["id"].endswith("@default")]
    assert len(defaults) == len([p for p in FIXTURES.rglob("*.mmd") if "expected" not in p.parts])
    for case in defaults:
        name = case["id"].rsplit("@", 1)[0]
        snapshot = FIXTURES / "expected" / (name.split("/", 1)[1] if name.startswith("flowcharts/") else name)
        assert case["expected"] == snapshot.with_suffix(".txt").read_text(encoding="utf-8").rstrip("\n"), name
    assert all(c["expected"].strip() for c in cases)
