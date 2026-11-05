"""CLI entry point for termaid."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from typing import NoReturn

from .diagnostics import Diagnostic
from .utils import display_width


def _get_version() -> str:
    """Get version from package metadata, falling back to the source version."""
    try:
        from importlib.metadata import version
        return version("termaid")
    except Exception:
        from termaid import __version__
        return __version__


class _ArgumentParser(argparse.ArgumentParser):
    diagnostics_format = "text"

    def error(self, message: str) -> NoReturn:
        if self.diagnostics_format == "json":
            Diagnostic("invalid_arguments", message, exit_code=2).emit("json")
            self.exit(2)
        super().error(message)


def _report(
    args: argparse.Namespace,
    code: str,
    message: str,
    *,
    exit_code: int = 1,
    severity: str = "error",
    **details: str | int,
) -> int:
    """Print a diagnostic in the format chosen by --diagnostics-format."""
    diagnostic = Diagnostic(code, message, exit_code=exit_code, severity=severity, details=details)
    return diagnostic.emit(args.diagnostics_format)


def _max_line_width(text: str) -> int:
    """Return the width of the longest line in text."""
    return max((display_width(line) for line in text.split("\n")), default=0)


def _plain(result) -> str:
    """Plain-text view of a render result (str, rich.text.Text or StyledDocument)."""
    if isinstance(result, dict):
        return "\n".join("".join(chunk["text"] for chunk in line) for line in result["lines"])
    return getattr(result, "plain", result)


def _auto_fit(
    result,
    source: str,
    args: argparse.Namespace,
    render_fn,
    target_width: int | None = None,
):
    """Re-render with smaller gap/padding if the diagram exceeds target width.

    target_width: explicit width limit (from --width), or None to use
    terminal width.  Disabled when --no-auto-fit is set or output is
    not a terminal (unless --width is explicitly given).
    """
    if target_width is None:
        if args.no_auto_fit or not sys.stdout.isatty():
            return result
        target_width = shutil.get_terminal_size().columns

    def width_of(candidate) -> int:
        return _max_line_width(_plain(candidate))

    if width_of(result) <= target_width:
        return result

    def render(**overrides):
        return render_fn(
            source,
            use_ascii=args.ascii,
            padding_y=args.padding_y,
            rounded_edges=not args.sharp_edges,
            inline_edge_labels=args.inline_edge_labels,
            arrow_style=args.arrow_style,
            **overrides,
        )

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
        candidate = render(gap=gap, padding_x=px)
        if width_of(candidate) <= target_width:
            return candidate
        result = candidate

    # Spacing alone was not enough: wrap labels and keep the widest label
    # width that fits. Width 1 goes first: if it changes nothing, this diagram
    # type ignores label width; if it still overflows, nothing will fit.
    narrowest = render(gap=1, padding_x=0, max_label_width=1)
    if _plain(narrowest) != _plain(result):
        result = narrowest
        if width_of(narrowest) <= target_width:
            low, high = 2, min(target_width, 64)
            while low <= high:
                label_width = (low + high) // 2
                candidate = render(gap=1, padding_x=0, max_label_width=label_width)
                if width_of(candidate) <= target_width:
                    result = candidate
                    low = label_width + 1
                else:
                    high = label_width - 1
            return result

    actual_width = width_of(result)
    if actual_width > target_width and not args.strict_width:
        _report(
            args,
            "width_exceeded",
            f"diagram is {actual_width} cols wide but target is {target_width}. "
            f"Try: less -S, or use 'graph TD' for vertical layout.",
            exit_code=0,
            severity="warning",
            actual_width=actual_width,
            max_width=target_width,
        )

    return result


def _read_source(args: argparse.Namespace) -> str | None:
    """Read diagram source from file or stdin. Returns None on error."""
    if args.file:
        try:
            with open(args.file, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            _report(args, "input_missing", f"File not found: {args.file}", path=args.file)
            return None
        except (OSError, UnicodeDecodeError) as e:
            _report(args, "input_missing", f"Error reading file: {e}", path=args.file)
            return None
    elif not sys.stdin.isatty():
        return sys.stdin.read()
    else:
        _report(
            args,
            "input_missing",
            "No input provided. Pass a file or pipe input.\n"
            "Usage: termaid diagram.mmd\n"
            "       echo 'graph LR; A-->B' | termaid",
        )
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
    # Read --diagnostics-format first, so argument errors honour it too.
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--diagnostics-format", default="text")
    diagnostics_format = pre_parser.parse_known_args(argv)[0].diagnostics_format

    parser = _ArgumentParser(
        prog="termaid",
        description="Render Mermaid diagrams as Unicode art in the terminal",
    )
    parser.diagnostics_format = diagnostics_format
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
        "--arrow-style",
        choices=("pointer", "triangle", "outline"),
        default="pointer",
        help="Arrowheads: pointer (default, ► ◄ ▼ ▲), triangle (▶ ◀ ▼ ▲) or outline (▷ ◁ ▽ △). See --arrow-styles",
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
        help="Max output width. Re-renders with smaller gap/padding, then wraps labels, if exceeded.",
    )
    parser.add_argument(
        "--strict-width",
        action="store_true",
        help="Exit with status 2 instead of a warning when the output is still wider than --width.",
    )
    parser.add_argument(
        "--max-height",
        type=int,
        default=None,
        metavar="ROWS",
        help="Exit with status 2 when the output has more than ROWS lines. "
             "A check on the final output, not a fitting target.",
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
        "--inline-edge-labels",
        action="store_true",
        help="Attach labels directly to their edges",
    )
    parser.add_argument(
        "--format",
        dest="output_format",
        default="text",
        choices=["text", "styled-json"],
        help="Output format. styled-json prints one JSON document of text "
             "chunks tagged with style keys, for editors and other tools.",
    )
    parser.add_argument(
        "--diagnostics-format",
        default="text",
        choices=["text", "json"],
        help="Print errors and warnings on stderr as text or as JSON lines.",
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
        "--markdown",
        action="store_true",
        help="Read a Markdown document and render each ```mermaid block in place.",
    )
    parser.add_argument(
        "--claude-hook",
        action="store_true",
        help="Run as a Claude Code MessageDisplay hook: read one batch of the "
             "response as JSON on stdin and draw its Mermaid blocks in place.",
    )
    parser.add_argument(
        "--arrow-styles",
        action="store_true",
        help="List available arrowhead styles and exit.",
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
    styled = args.output_format == "styled-json"

    if styled and (args.claude_hook or args.tui or args.markdown):
        return _report(
            args,
            "invalid_arguments",
            "--format styled-json cannot be combined with --claude-hook, --tui or --markdown.",
            exit_code=2,
        )

    if args.claude_hook:
        from .claude_hook import run_claude_hook
        return run_claude_hook(width=args.width, use_ascii=args.ascii)

    if args.themes:
        return _list_themes()

    if args.arrow_styles:
        return _list_arrow_styles()

    if args.demo is not None:
        return _run_demo(args)

    if args.width is not None and args.width < 1:
        return _report(args, "invalid_arguments", "--width must be positive.", exit_code=2)

    # Read input
    source = _read_source(args)
    if source is None:
        return 1

    # Markdown keeps its leading lines, so warnings report true line numbers.
    source = source.rstrip() if args.markdown else source.strip()
    if not source.strip():
        return _report(args, "input_empty", "Empty input.")

    if args.markdown and (args.json or args.tui):
        return _report(args, "invalid_arguments", "--markdown cannot be combined with --json or --tui.")

    if args.strict_width and args.width is None:
        return _report(args, "invalid_arguments", "--strict-width requires --width.", exit_code=2)
    if args.max_height is not None and args.max_height < 1:
        return _report(args, "invalid_arguments", "--max-height must be positive.", exit_code=2)

    # JSON ingest: convert structured data to Mermaid syntax
    if args.json:
        try:
            from .ingest import json_to_mermaid
            source = json_to_mermaid(source, args.json)
        except Exception as e:
            return _report(args, "input_conversion_failed", f"Error converting JSON to {args.json}: {e}")

    # TUI mode
    if args.tui:
        return _run_tui(source, args)

    # Render
    from termaid import render, render_rich, render_styled

    use_color = not styled and _use_color(args)
    if use_color:
        try:
            from rich import print as rprint
            from rich.console import Console
        except ImportError:
            return _report(
                args,
                "dependency_missing",
                "'rich' package required for --theme. Install with: pip install termaid[rich]",
                dependency="rich",
            )

    if styled:
        render_fn = render_styled
    elif use_color:
        def render_fn(src: str, **kwargs):
            return render_rich(src, theme=args.theme or "default", **kwargs)
    else:
        render_fn = render

    try:
        if args.markdown:
            result = _render_markdown(source, args, render_fn, use_color)
        else:
            result = _render_one(source, args, render_fn, target_width=args.width)
            if not _plain(result).strip():
                return _report(args, "render_empty", "Input produced no renderable diagram.")

        failed = _check_output(_plain(result), args)
        if failed is not None:
            return failed

        if use_color:
            rich_result = result
            if args.output:
                try:
                    with open(args.output, "w", encoding="utf-8") as f:
                        console = Console(
                            file=f,
                            force_terminal=True,
                            width=max(_max_line_width(_plain(rich_result)), 80),
                        )
                        console.print(rich_result)
                except OSError as e:
                    return _report(args, "output_write_failed", f"Error writing to {args.output}: {e}", path=args.output)
            else:
                rprint(rich_result)
        else:
            if styled:
                result = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
            if args.output:
                try:
                    with open(args.output, "w", encoding="utf-8") as f:
                        f.write(result + "\n")
                except OSError as e:
                    return _report(args, "output_write_failed", f"Error writing to {args.output}: {e}", path=args.output)
            else:
                print(result)
    except Exception as e:
        return _report(args, "render_failed", f"Error rendering diagram: {e}")

    return 0


def _check_output(text: str, args: argparse.Namespace) -> int | None:
    """Apply --strict-width and --max-height to the final output; 2 when violated."""
    width = _max_line_width(text)
    height = len(text.split("\n"))
    if args.strict_width and width > args.width:
        return _report(
            args, "width_exceeded",
            f"diagram is {width} cols wide but target is {args.width}.",
            exit_code=2, actual_width=width, max_width=args.width,
        )
    if args.max_height is not None and height > args.max_height:
        return _report(
            args, "height_exceeded",
            f"diagram exceeds {args.max_height} output rows.",
            exit_code=2, actual_height=height, max_height=args.max_height,
        )
    return None


def _render_one(source: str, args: argparse.Namespace, render_fn, target_width: int | None):
    """Render one diagram with the CLI's options, fitted to target_width."""
    if args.show_ids:
        source = _apply_show_ids(source)
    result = render_fn(
        source,
        use_ascii=args.ascii,
        padding_x=args.padding_x,
        padding_y=args.padding_y,
        rounded_edges=not args.sharp_edges,
        gap=args.gap,
        inline_edge_labels=args.inline_edge_labels,
        arrow_style=args.arrow_style,
    )
    return _auto_fit(result, source, args, render_fn=render_fn, target_width=target_width)


def _render_markdown(text: str, args: argparse.Namespace, render_fn, use_color: bool):
    """Render every Mermaid block in a Markdown document, in place.

    Text outside the blocks is passed through unchanged. A diagram nested in
    a list item keeps the item's indentation. A block that fails to render is
    shown as its original source, with a warning on stderr, so one bad
    diagram does not lose the rest of the document. That includes a block
    that renders to nothing, which is what unrecognised input produces.
    """
    from .markdown import split_markdown

    if args.width is not None:
        width = args.width
    elif args.no_auto_fit or not sys.stdout.isatty():
        width = None
    else:
        width = shutil.get_terminal_size().columns

    pieces = []
    for seg in split_markdown(text):
        if not seg.is_mermaid:
            pieces.append(seg.text)
            continue
        target = None if width is None else max(width - display_width(seg.indent), 1)
        try:
            drawn = _render_one(seg.text, args, render_fn, target)
        except Exception as e:
            failure = ("render_failed", str(e))
        else:
            failure = None if _plain(drawn).strip() else ("render_empty", "nothing to draw")
        if failure is None:
            pieces.append(_indent(drawn, seg.indent))
            continue
        code, reason = failure
        _report(
            args,
            code,
            f"could not render the diagram at line {seg.line}: {reason}",
            exit_code=0,
            severity="warning",
            line=seg.line,
        )
        pieces.append(seg.raw)

    if not use_color:
        return "\n".join(pieces)

    from rich.text import Text
    return Text("\n").join(p if isinstance(p, Text) else Text(p) for p in pieces)


def _indent(result, indent: str):
    """Prefix every line of a render result (str or rich.text.Text)."""
    if not indent:
        return result
    if isinstance(result, str):
        return "\n".join(indent + line for line in result.split("\n"))
    from rich.text import Text
    return Text("\n").join(Text(indent) + line for line in result.split("\n", allow_blank=True))


def _run_tui(source: str, args: argparse.Namespace) -> int:
    """Launch the TUI viewer."""
    try:
        from textual.app import App, ComposeResult
        from textual.widgets import Static
        from termaid import render as _render
    except ImportError:
        return _report(
            args,
            "dependency_missing",
            "'textual' package required for --tui. Install with: pip install termaid[tui]",
            dependency="textual",
        )

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
                arrow_style=args.arrow_style,
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
        from termaid import _prepare_source, _skip_directives, parse
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

    # Insert the redefinitions right after the graph/flowchart header line.
    lines = _skip_directives(_prepare_source(source)).split("\n")
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



def _list_arrow_styles() -> int:
    """List available arrowhead styles."""
    from .renderer.charset import ARROW_STYLES

    descriptions = {
        "pointer": "Pointers (default)",
        "triangle": "Solid triangles, matching the up and down arrows",
        "outline": "Open triangles",
    }
    for name, (right, left, down, up) in ARROW_STYLES.items():
        print(f"  {name:10s} {right} {left} {down} {up}   {descriptions.get(name, '')}")
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
    "journey": ("User journey", "journey\n    title My working day\n    section Go to work\n        Make tea: 5: Me\n        Go upstairs: 3: Me\n        Do work: 1: Me, Cat\n    section Go home\n        Go downstairs: 5: Me\n        Sit down: 5: Me"),
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
        return _report(
            args,
            "invalid_arguments",
            f"Unknown demo type: {demo_type}\nAvailable: all, {', '.join(_DEMO_SOURCES.keys())}",
        )

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
