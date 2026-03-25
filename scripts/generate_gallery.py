#!/usr/bin/env python3
"""Generate a markdown gallery of all diagram fixtures.

Renders each .mmd fixture file and writes the input + output to
docs/gallery.md as a visual reference and regression baseline.

Usage:
    python scripts/generate_gallery.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure the package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from termaid import render


FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
OUTPUT_FILE = Path(__file__).resolve().parent.parent / "docs" / "gallery.md"


def _collect_fixtures() -> list[tuple[str, Path]]:
    """Collect all .mmd fixture files, grouped by directory."""
    fixtures: list[tuple[str, Path]] = []
    for mmd in sorted(FIXTURES_DIR.rglob("*.mmd")):
        rel = mmd.relative_to(FIXTURES_DIR)
        category = rel.parent.name if rel.parent != Path(".") else "general"
        fixtures.append((category, mmd))
    return fixtures


def main() -> None:
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    fixtures = _collect_fixtures()
    if not fixtures:
        print("No fixtures found.", file=sys.stderr)
        return

    lines: list[str] = []
    lines.append("# termaid Gallery")
    lines.append("")
    lines.append("Auto-generated visual reference of all supported diagram fixtures.")
    lines.append(f"Total: {len(fixtures)} diagrams.")
    lines.append("")

    current_category = ""
    success = 0
    errors = 0

    for category, mmd_path in fixtures:
        if category != current_category:
            current_category = category
            lines.append(f"## {category}")
            lines.append("")

        name = mmd_path.stem
        source = mmd_path.read_text().strip()

        lines.append(f"### {name}")
        lines.append("")
        lines.append("**Input:**")
        lines.append("```mermaid")
        lines.append(source)
        lines.append("```")
        lines.append("")

        try:
            output = render(source)
            if output.startswith("[termaid] Failed"):
                lines.append(f"**Output:** _{output}_")
                errors += 1
            else:
                lines.append("**Output:**")
                lines.append("```")
                lines.append(output)
                lines.append("```")
                success += 1
        except Exception as e:
            lines.append(f"**Output:** _Error: {e}_")
            errors += 1

        lines.append("")

    OUTPUT_FILE.write_text("\n".join(lines) + "\n")
    print(f"Gallery written to {OUTPUT_FILE}")
    print(f"  {success} rendered, {errors} errors, {success + errors} total")


if __name__ == "__main__":
    main()
