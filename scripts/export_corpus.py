#!/usr/bin/env python3
"""Write the shared test set: every fixture drawn by this (Python) termaid.

Usage: python scripts/export_corpus.py OUT.jsonl

Each line is one case: a fixture's source, the options it is drawn with, and
the exact text termaid draws. Another implementation, such as the TypeScript
port, passes when it draws the same text for every case.
"""
import json
import sys
from functools import partial
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from termaid import render  # noqa: E402
from termaid.utils import fit_to_width  # noqa: E402

FIXTURES = REPO / "tests" / "fixtures"

# Option sets passed to render(), by name.
OPTION_SETS = {
    "default": {},
    "ascii": {"use_ascii": True},
    "compact": {"padding_x": 1, "padding_y": 0, "gap": 2},
    "sharp": {"rounded_edges": False},
}

# Widths the Claude Code hook fits default drawings to, as fit_to_width does.
FIT_WIDTHS = (60, 100)


def fixtures():
    for path in sorted(FIXTURES.rglob("*.mmd")):
        if "expected" in path.parts:
            continue
        yield path.relative_to(FIXTURES).with_suffix("").as_posix(), path.parent.name, path


def cases():
    for name, kind, path in fixtures():
        source = path.read_text(encoding="utf-8").strip()
        for set_name, options in OPTION_SETS.items():
            yield {
                "id": "%s@%s" % (name, set_name),
                "type": kind,
                "source": source,
                "options": options,
                "fit_width": None,
                "expected": render(source, **options),
            }
        draw = partial(render, source)
        for width in FIT_WIDTHS:
            yield {
                "id": "%s@fit%d" % (name, width),
                "type": kind,
                "source": source,
                "options": {},
                "fit_width": width,
                "expected": fit_to_width(draw, draw(), width),
            }


def main(out):
    with open(out, "w", encoding="utf-8") as f:
        for case in cases():
            f.write(json.dumps(case, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: export_corpus.py OUT.jsonl")
    main(sys.argv[1])
