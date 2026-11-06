#!/usr/bin/env python3
"""Run the copy of termaid bundled in this plugin's lib/ folder.

Keep this file parseable by old Pythons: it must reach the version check.
"""
import os
import sys

LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
hook = "--claude-hook" in sys.argv[1:]

if sys.version_info < (3, 9):
    if hook:
        sys.exit(0)
    sys.stderr.write("termaid: this plugin needs Python 3.9 or later\n")
    sys.exit(1)

if not os.path.isdir(os.path.join(LIB, "termaid")):
    if hook:
        sys.exit(0)
    sys.stderr.write(
        "termaid: the bundled copy is missing (no lib/termaid). "
        "Build the plugin with scripts/build_claude_plugin.py\n"
    )
    sys.exit(1)

sys.path.insert(0, LIB)
from termaid.cli import main  # noqa: E402

sys.exit(main(sys.argv[1:]))
