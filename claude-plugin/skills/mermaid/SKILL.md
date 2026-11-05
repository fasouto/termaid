---
name: mermaid
description: Render Mermaid diagrams that already exist, such as a .mmd file or the diagrams in a Markdown document, README or PR description, in the terminal with termaid, or check that a diagram draws. Not for a diagram you write in your own reply; the termaid hook already draws those.
---

# Render Mermaid with termaid

When you write a new diagram in your reply, put it in a ```mermaid code block
and stop there. The termaid hook draws the block in place, fitted to the
terminal. Running termaid on it as well shows the diagram twice.

For diagrams that live somewhere else, run termaid with the Bash tool and show
the output in a fenced code block so the box characters stay aligned. The Bash
tool is not a terminal, so termaid cannot see the screen width: pass
`--width 100`, or a smaller number if the user's terminal is narrow.

- One diagram, from a file: `termaid --width 100 path/to/diagram.mmd`
- One diagram, inline: `printf '%s\n' '<mermaid source>' | termaid --width 100`
- Every diagram in a Markdown document, in place: `termaid --width 100 --markdown README.md`
- A PR description: `gh pr view 42 | termaid --width 100 --markdown`
- Plain ASCII: add `--ascii`.

If termaid is not installed, tell the user: `brew install termaid` or
`uv tool install termaid`.

To check a diagram, run termaid on it. termaid exits non-zero and prints the
reason on stderr when it cannot draw anything. It parses leniently, so a
drawing does not prove the source is valid Mermaid. Compare the drawing with
the nodes and edges the user meant. Paste the drawing verbatim. Do not
describe it in words.
