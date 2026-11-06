"""JSON-to-Mermaid converters for CLI data ingest.

Converts structured JSON data into Mermaid diagram syntax so users
can pipe output from other CLI tools directly into termaid.

Usage:
    du -d1 -k /var | termaid --json treemap
    echo '{"A":30,"B":70}' | termaid --json pie
"""
from __future__ import annotations

import json
import sys


def json_to_mermaid(data: str, diagram_type: str) -> str:
    """Convert JSON string to Mermaid syntax for the given diagram type."""
    converters = {
        "xychart": _to_xychart,
        "treemap": _to_treemap,
        "pie": _to_pie,
        "mindmap": _to_mindmap,
        "flowchart": _to_flowchart,
    }

    converter = converters.get(diagram_type)
    if converter is None:
        supported = ", ".join(converters.keys())
        raise ValueError(f"Unsupported JSON diagram type: {diagram_type}. Supported: {supported}")

    # Try parsing as JSON first
    try:
        parsed = json.loads(data)
        return converter(parsed)
    except json.JSONDecodeError:
        pass

    # Fall back to tabular input (TSV/space-separated: value\tlabel)
    return _from_tabular(data, diagram_type)


def _to_treemap(data: object) -> str:
    """Convert JSON to treemap-beta syntax."""
    lines = ["treemap-beta"]

    def _walk(obj: object, indent: int = 4) -> None:
        pad = " " * indent
        if isinstance(obj, dict):
            for key, val in obj.items():
                if isinstance(val, dict):
                    lines.append(f'{pad}"{key}"')
                    _walk(val, indent + 4)
                elif isinstance(val, (int, float)):
                    lines.append(f'{pad}"{key}": {val}')
                elif isinstance(val, list):
                    lines.append(f'{pad}"{key}"')
                    for item in val:
                        _walk(item, indent + 4)
                else:
                    lines.append(f'{pad}"{key}": {val}')
        elif isinstance(obj, list):
            for item in obj:
                _walk(item, indent)

    _walk(data)
    return "\n".join(lines)


def _to_pie(data: object) -> str:
    """Convert JSON to pie chart syntax."""
    lines = ["pie"]

    if isinstance(data, dict):
        for key, val in data.items():
            if isinstance(val, (int, float)):
                lines.append(f'    "{key}" : {val}')
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                for key, val in item.items():
                    if isinstance(val, (int, float)):
                        lines.append(f'    "{key}" : {val}')

    return "\n".join(lines)


def _to_mindmap(data: object) -> str:
    """Convert JSON to mindmap syntax."""
    lines = ["mindmap"]

    def _walk(obj: object, indent: int = 2) -> None:
        pad = " " * indent
        if isinstance(obj, dict):
            for key, val in obj.items():
                lines.append(f"{pad}{key}")
                if isinstance(val, dict):
                    _walk(val, indent + 2)
                elif isinstance(val, list):
                    for item in val:
                        if isinstance(item, str):
                            lines.append(f"{pad}  {item}")
                        elif isinstance(item, dict):
                            _walk(item, indent + 2)
        elif isinstance(obj, list):
            for item in obj:
                if isinstance(item, str):
                    lines.append(f"{pad}{item}")
                elif isinstance(item, dict):
                    _walk(item, indent)

    _walk(data)
    return "\n".join(lines)


def _to_flowchart(data: object) -> str:
    """Convert JSON to flowchart syntax.

    Accepts:
        [{"from": "A", "to": "B"}, ...]
        or {"nodes": [...], "edges": [...]}
    """
    lines = ["graph TD"]

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                src = item.get("from") or item.get("source") or item.get("src")
                tgt = item.get("to") or item.get("target") or item.get("dst")
                label = item.get("label", "")
                if src and tgt:
                    if label:
                        lines.append(f"    {src}-->|{label}|{tgt}")
                    else:
                        lines.append(f"    {src}-->{tgt}")
    elif isinstance(data, dict):
        edges = data.get("edges", [])
        for item in edges:
            if isinstance(item, dict):
                src = item.get("from") or item.get("source")
                tgt = item.get("to") or item.get("target")
                if src and tgt:
                    lines.append(f"    {src}-->{tgt}")

    return "\n".join(lines)


def _to_xychart(data: object) -> str:
    """Convert JSON to xychart-beta syntax.

    Accepts:
        [10, 25, 18, 32]  -- simple array of numbers
        {"Jan": 10, "Feb": 25}  -- object with categories
        {"bar": [10, 25], "line": [8, 20]}  -- multiple datasets
    """
    lines = ["xychart-beta"]

    if isinstance(data, list) and all(isinstance(v, (int, float)) for v in data):
        cats = [str(i + 1) for i in range(len(data))]
        lines.append(f"    x-axis [{', '.join(cats)}]")
        vals = ", ".join(str(v) for v in data)
        lines.append(f"    bar [{vals}]")

    elif isinstance(data, dict):
        # Check if keys are dataset types (bar/line)
        if "bar" in data or "line" in data:
            max_len = 0
            for key in ("bar", "line"):
                if key in data and isinstance(data[key], list):
                    max_len = max(max_len, len(data[key]))
            cats = [str(i + 1) for i in range(max_len)]
            lines.append(f"    x-axis [{', '.join(cats)}]")
            for key in ("bar", "line"):
                if key in data and isinstance(data[key], list):
                    vals = ", ".join(str(v) for v in data[key])
                    lines.append(f"    {key} [{vals}]")
        else:
            # Keys are categories, values are numbers
            cats = list(data.keys())
            vals = [data[k] for k in cats if isinstance(data[k], (int, float))]
            lines.append(f"    x-axis [{', '.join(cats)}]")
            lines.append(f"    bar [{', '.join(str(v) for v in vals)}]")

    return "\n".join(lines)


def _from_tabular(data: str, diagram_type: str) -> str:
    """Parse tabular input (like du output) into Mermaid syntax.

    Expects lines with: number<tab>label or number<space>label
    """
    entries: list[tuple[str, float]] = []
    for line in data.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            try:
                val = float(parts[0])
                entries.append((parts[1], val))
            except ValueError:
                # Try reversed: label<tab>number
                try:
                    val = float(parts[1])
                    entries.append((parts[0], val))
                except ValueError:
                    continue

    if not entries:
        raise ValueError("Could not parse input as JSON or tabular data")

    if diagram_type == "treemap":
        lines = ['treemap-beta', '    "data"']
        for label, val in entries:
            safe = label.replace('"', "'")
            lines.append(f'        "{safe}": {val}')
        return "\n".join(lines)

    if diagram_type == "pie":
        lines = ["pie"]
        for label, val in entries:
            safe = label.replace('"', "'")
            lines.append(f'    "{safe}" : {val}')
        return "\n".join(lines)

    raise ValueError(f"Tabular input not supported for {diagram_type}")
