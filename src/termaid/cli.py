"""CLI entry point for termaid."""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from .utils import display_width


def _get_version() -> str:
    """Get version from package metadata, with hardcoded fallback."""
    try:
        from importlib.metadata import version
        return version("termaid")
    except Exception:
        return "0.2.1"


def _max_line_width(text: str) -> int:
    """Return the width of the longest line in text."""
    return max((display_width(line) for line in text.split("\n")), default=0)


def _auto_fit(
    result: str,
    source: str,
    args: argparse.Namespace,
    render_fn,
    target_width: int | None = None,
) -> str:
    """Re-render with smaller gap/padding if the diagram exceeds target width.

    target_width: explicit width limit (from --width), or None to use
    terminal width.  Disabled when --no-auto-fit is set or output is
    not a terminal (unless --width is explicitly given).
    """
    if target_width is None:
        if args.no_auto_fit or not sys.stdout.isatty():
            return result
        target_width = shutil.get_terminal_size().columns

    if _max_line_width(result) <= target_width:
        return result

    # Progressively compact: reduce gap, then padding
    compact_steps = [
        {"gap": min(args.gap, 2)},
        {"gap": 1},
        {"gap": 1, "padding_x": 2},
        {"gap": 1, "padding_x": 0},
    ]

    for overrides in compact_steps:
        gap = overrides.get("gap", args.gap)
        px = overrides.get("padding_x", args.padding_x)
        if gap >= args.gap and px >= args.padding_x:
            continue
        candidate = render_fn(
            source,
            use_ascii=args.ascii,
            padding_x=px,
            padding_y=args.padding_y,
            rounded_edges=not args.sharp_edges,
            gap=gap,
        )
        if _max_line_width(candidate) <= target_width:
            return candidate
        result = candidate

    if _max_line_width(result) > target_width:
        print(
            f"Warning: diagram is {_max_line_width(result)} cols wide "
            f"but target is {target_width}. "
            f"Try: less -S, or use 'graph TD' for vertical layout.",
            file=sys.stderr,
        )

    return result


def _read_source(args: argparse.Namespace) -> str | None:
    """Read diagram source from file or stdin. Returns None on error."""
    if args.file:
        try:
            with open(args.file) as f:
                return f.read()
        except FileNotFoundError:
            print(f"Error: File not found: {args.file}", file=sys.stderr)
            return None
        except OSError as e:
            print(f"Error reading file: {e}", file=sys.stderr)
            return None
    elif not sys.stdin.isatty():
        return sys.stdin.read()
    else:
        print("Error: No input provided. Pass a file or pipe input.", file=sys.stderr)
        print("Usage: termaid diagram.mmd", file=sys.stderr)
        print("       echo 'graph LR; A-->B' | termaid", file=sys.stderr)
        return None


def _use_color(args: argparse.Namespace) -> bool:
    """Determine whether to use color output, respecting NO_COLOR."""
    if args.theme is None:
        return False
    if os.environ.get("NO_COLOR") is not None:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="termaid",
        description="Render Mermaid diagrams as Unicode art in the terminal",
    )
    parser.add_argument(
        "file",
        nargs="?",
        help="Mermaid diagram file (.mmd). Reads from stdin if not provided.",
    )
    parser.add_argument(
        "--ascii",
        action="store_true",
        help="Use ASCII characters instead of Unicode box-drawing",
    )
    parser.add_argument(
        "--padding-x",
        type=int,
        default=4,
        help="Horizontal padding inside node boxes (default: 4)",
    )
    parser.add_argument(
        "--padding-y",
        type=int,
        default=2,
        help="Vertical padding inside node boxes (default: 2)",
    )
    parser.add_argument(
        "--gap",
        type=int,
        default=4,
        help="Space between nodes (default: 4). Use 1 or 2 for compact diagrams.",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=None,
        help="Max output width. Re-renders with smaller gap/padding if exceeded.",
    )
    parser.add_argument(
        "--sharp-edges",
        action="store_true",
        help="Use sharp corners on edge turns instead of rounded",
    )
    parser.add_argument(
        "--theme",
        default=None,
        choices=["default", "terra", "neon", "mono", "amber", "phosphor",
                 "gruvbox", "monokai", "dracula", "nord", "solarized"],
        help="Color theme. Requires 'rich' package (pip install termaid[rich]).",
    )
    parser.add_argument(
        "--tui",
        action="store_true",
        help="Launch interactive TUI viewer. Requires 'textual' (pip install termaid[tui]).",
    )
    parser.add_argument(
        "--no-auto-fit",
        action="store_true",
        help="Disable automatic compaction when diagram exceeds terminal width",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        metavar="FILE",
        help="Write output to file instead of stdout",
    )
    parser.add_argument(
        "--show-ids",
        action="store_true",
        help="Show node IDs alongside labels (e.g. 'A: Start') for debugging.",
    )
    parser.add_argument(
        "--json",
        default=None,
        metavar="TYPE",
        choices=["treemap", "pie", "mindmap", "flowchart", "xychart"],
        help="Read JSON/tabular data from stdin and render as TYPE (treemap, pie, mindmap, flowchart).",
    )
    parser.add_argument(
        "--themes",
        action="store_true",
        help="List available color themes and exit.",
    )
    parser.add_argument(
        "--demo",
        nargs="?",
        const="all",
        default=None,
        metavar="TYPE",
        help="Render sample diagrams. Use 'all' or a type name (flowchart, sequence, etc.).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_get_version()}",
    )

    args = parser.parse_args(argv)

    if args.themes:
        return _list_themes()

    if args.demo is not None:
        return _run_demo(args)

    # Read input
    source = _read_source(args)
    if source is None:
        return 1

    source = source.strip()
    if not source:
        print("Error: Empty input.", file=sys.stderr)
        return 1

    # JSON ingest: convert structured data to Mermaid syntax
    if args.json:
        try:
            from .ingest import json_to_mermaid
            source = json_to_mermaid(source, args.json)
        except Exception as e:
            print(f"Error converting JSON to {args.json}: {e}", file=sys.stderr)
            return 1

    # TUI mode
    if args.tui:
        return _run_tui(source, args)

    # Render
    try:
        from termaid import render, render_rich
    except ImportError:
        _src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, _src_dir)
        try:
            from termaid import render, render_rich
        except ImportError:
            print("Error: termaid package not found. Install with: pip install -e .", file=sys.stderr)
            return 1

    try:
        use_color = _use_color(args)
        if use_color:
            rich_result = render_rich(
                source,
                use_ascii=args.ascii,
                padding_x=args.padding_x,
                padding_y=args.padding_y,
                rounded_edges=not args.sharp_edges,
                theme=args.theme or "default",
            )
            try:
                from rich import print as rprint
                rprint(rich_result)
            except ImportError:
                print("Error: 'rich' package required for --theme. Install with: pip install termaid[rich]", file=sys.stderr)
                return 1
        else:
            # --show-ids: patch node labels before rendering
            render_source = source
            if args.show_ids:
                render_source = _apply_show_ids(source)

            result = render(
                render_source,
                use_ascii=args.ascii,
                padding_x=args.padding_x,
                padding_y=args.padding_y,
                rounded_edges=not args.sharp_edges,
                gap=args.gap,
            )
            result = _auto_fit(
                result, render_source, args,
                render_fn=render,
                target_width=args.width,
            )
            if args.output:
                try:
                    with open(args.output, "w") as f:
                        f.write(result + "\n")
                except OSError as e:
                    print(f"Error writing to {args.output}: {e}", file=sys.stderr)
                    return 1
            else:
                print(result)
    except Exception as e:
        print(f"Error rendering diagram: {e}", file=sys.stderr)
        return 1

    return 0


def _run_tui(source: str, args: argparse.Namespace) -> int:
    """Launch the TUI viewer."""
    try:
        from textual.app import App, ComposeResult
        from textual.widgets import Static
        from termaid import render as _render
    except ImportError:
        print("Error: 'textual' package required for --tui. Install with: pip install termaid[tui]", file=sys.stderr)
        return 1

    class DiagramApp(App):
        CSS = "Static { width: auto; height: auto; }"

        def compose(self) -> ComposeResult:
            yield Static(_render(
                source,
                use_ascii=args.ascii,
                padding_x=args.padding_x,
                padding_y=args.padding_y,
                rounded_edges=not args.sharp_edges,
                gap=args.gap,
            ))

    DiagramApp().run()
    return 0


def _apply_show_ids(source: str) -> str:
    """Rewrite flowchart source so node labels include their IDs.

    For each node where label != id, appends a node definition line
    ``ID["ID: Label"]`` to the source so the parser picks up the new label.
    Non-flowchart diagrams are returned unchanged.
    """
    try:
        from termaid import parse
        graph = parse(source)
    except Exception:
        return source

    # Build rewrite lines for nodes where label differs from ID
    extra_lines: list[str] = []
    for nid, node in graph.nodes.items():
        if node.label != nid:
            # Escape quotes in the combined label
            safe_label = f"{nid}: {node.label}".replace('"', "'")
            extra_lines.append(f'  {nid}["{safe_label}"]')

    if not extra_lines:
        return source

    # Append the redefinition lines after the header
    lines = source.split("\n")
    # Insert after the first line (the graph/flowchart header)
    return lines[0] + "\n" + "\n".join(extra_lines) + "\n" + "\n".join(lines[1:])



def _list_themes() -> int:
    """List available color themes."""
    themes = [
        ("default",   "text",  "Cyan nodes, yellow arrows, white labels"),
        ("terra",     "text",  "Warm earth tones (browns, oranges)"),
        ("neon",      "text",  "Magenta nodes, green arrows, cyan edges"),
        ("mono",      "text",  "White/gray monochrome"),
        ("amber",     "text",  "Amber/gold CRT-style"),
        ("phosphor",  "text",  "Green phosphor terminal"),
        ("gruvbox",   "solid", "Gruvbox dark palette"),
        ("monokai",   "solid", "Monokai dark with pink/green accents"),
        ("dracula",   "solid", "Dracula purple/pink/green palette"),
        ("nord",      "solid", "Nord muted blue/cyan arctic palette"),
        ("solarized", "solid", "Solarized dark blue/yellow/cyan"),
    ]
    for name, kind, desc in themes:
        tag = f"[{kind}]"
        print(f"  {name:12s} {tag:8s} {desc}")
    return 0


_DEMO_SOURCES = {
    "flowchart": ("Flowchart", "graph TD\n  A[Start] --> B{Decision}\n  B -->|Yes| C[Process]\n  B -->|No| D[End]\n  C --> D"),
    "sequence": ("Sequence diagram", "sequenceDiagram\n  Client->>Server: GET /api\n  Server->>DB: SELECT\n  DB-->>Server: rows\n  Server-->>Client: 200 JSON"),
    "class": ("Class diagram", "classDiagram\n  class Animal {\n    +String name\n    +makeSound()\n  }\n  class Dog {\n    +fetch()\n  }\n  Animal <|-- Dog"),
    "er": ("ER diagram", "erDiagram\n  CUSTOMER ||--o{ ORDER : places\n  ORDER ||--|{ ITEM : contains"),
    "state": ("State diagram", "stateDiagram-v2\n  [*] --> Idle\n  Idle --> Running : start\n  Running --> Done : complete\n  Done --> [*]"),
    "block": ("Block diagram", "block-beta\n  columns 3\n  Frontend API Database"),
    "git": ("Git graph", "gitGraph\n  commit\n  branch develop\n  commit\n  commit\n  checkout main\n  merge develop\n  commit"),
    "pie": ("Pie chart", 'pie title Languages\n  "Python" : 45\n  "Go" : 30\n  "Rust" : 25'),
    "treemap": ("Treemap", 'treemap-beta\n  "Backend"\n    "API": 35\n    "Auth": 15\n  "Frontend"\n    "React": 30\n    "CSS": 10'),
    "mindmap": ("Mindmap", "mindmap\n  Project\n    Design\n      Wireframes\n      Mockups\n    Development\n      Frontend\n      Backend\n    Testing"),
    "timeline": ("Timeline", "timeline\n    title Roadmap\n    section Q1\n        Research : Analysis\n        Design : Wireframes\n    section Q2\n        Build : Frontend, Backend\n        Launch : Beta"),
    "kanban": ("Kanban", "kanban\n    Todo\n        Design homepage\n        Fix login bug\n    In Progress\n        API integration\n    Done\n        Project setup"),
    "xychart": ("XY chart", 'xychart-beta\n    title "Monthly Revenue"\n    x-axis [Jan, Feb, Mar, Apr, May, Jun]\n    y-axis "Revenue (k)"\n    bar [12, 18, 25, 20, 30, 35]'),
    "quadrant": ("Quadrant chart", 'quadrantChart\n    title Priority Matrix\n    x-axis Low Effort --> High Effort\n    y-axis Low Impact --> High Impact\n    quadrant-1 Do First\n    quadrant-2 Schedule\n    quadrant-3 Delegate\n    quadrant-4 Eliminate\n    Task A: [0.3, 0.8]\n    Task B: [0.8, 0.9]\n    Task C: [0.2, 0.2]'),
}


def _run_demo(args: argparse.Namespace) -> int:
    """Render sample diagrams."""
    demo_type = args.demo.lower()
    if demo_type == "all":
        keys = list(_DEMO_SOURCES.keys())
    elif demo_type in _DEMO_SOURCES:
        keys = [demo_type]
    else:
        print(f"Unknown demo type: {demo_type}", file=sys.stderr)
        print(f"Available: all, {', '.join(_DEMO_SOURCES.keys())}", file=sys.stderr)
        return 1

    use_color = _use_color(args)

    for key in keys:
        title, source = _DEMO_SOURCES[key]
        print(f"=== {title} ===")
        if use_color:
            try:
                from termaid import render_rich
                from rich import print as rprint
                rprint(render_rich(source, theme=args.theme or "default"))
            except ImportError:
                from termaid import render
                print(render(source))
        else:
            from termaid import render
            print(render(source))
        print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
