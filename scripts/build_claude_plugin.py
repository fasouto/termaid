#!/usr/bin/env python3
"""Build the Claude Code plugin tree: the template plus a copy of termaid.

Usage: python3 scripts/build_claude_plugin.py OUT_DIR
"""
import json
import os
import re
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (source relative to the repo, destination relative to the plugin root)
COPIES = [
    ("claude-plugin/.claude-plugin/plugin.json", ".claude-plugin/plugin.json"),
    ("claude-plugin/hooks/hooks.json", "hooks/hooks.json"),
    ("claude-plugin/scripts/termaid.py", "scripts/termaid.py"),
    ("claude-plugin/skills/mermaid/SKILL.md", "skills/mermaid/SKILL.md"),
    ("claude-plugin/README.md", "README.md"),
    ("LICENSE", "LICENSE"),
    ("src/termaid", "lib/termaid"),
]

IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc")


def check_versions():
    with open(os.path.join(REPO, "claude-plugin/.claude-plugin/plugin.json")) as f:
        plugin_version = json.load(f)["version"]
    with open(os.path.join(REPO, "src/termaid/__init__.py")) as f:
        match = re.search(r'^__version__\s*=\s*"([^"]+)"', f.read(), re.M)
    if not match:
        sys.exit("build: no __version__ found in src/termaid/__init__.py")
    if match.group(1) != plugin_version:
        sys.exit(
            "build: plugin.json version %s differs from termaid __version__ %s"
            % (plugin_version, match.group(1))
        )


def clear(out):
    os.makedirs(out, exist_ok=True)
    for name in os.listdir(out):
        if name == ".git":
            continue
        path = os.path.join(out, name)
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)


def build(out):
    check_versions()
    clear(out)
    for src, dst in COPIES:
        src_path = os.path.join(REPO, src)
        dst_path = os.path.join(out, dst)
        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
        if os.path.isdir(src_path):
            shutil.copytree(src_path, dst_path, ignore=IGNORE)
        else:
            shutil.copy2(src_path, dst_path)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: build_claude_plugin.py OUT_DIR")
    build(os.path.abspath(sys.argv[1]))
