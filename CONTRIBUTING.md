# Contributing to termmaid

## Development setup

```bash
git clone https://github.com/fasouto/termmaid.git
cd termmaid
uv sync --all-extras
```

## Running tests

```bash
uv run pytest tests/ -q
```

To update snapshot tests after changing rendering output:

```bash
uv run pytest tests/ --update-snapshots
```

## Project structure

```
src/termmaid/
  __init__.py          # Public API: render(), render_rich(), parse()
  cli.py               # CLI entry point (argparse)
  graph/               # Graph data model (Node, Edge, Subgraph, NodeShape)
  model/               # Diagram-specific models (sequence, class, ER, block, gitgraph)
  parser/              # Mermaid syntax parsers (one per diagram type)
  layout/              # Grid-based layout computation (flowcharts)
  routing/             # A* edge routing (flowcharts)
  renderer/            # Canvas rendering, shapes, charsets, themes
  output/              # Output formats (text, rich, textual widget)
tests/
  fixtures/flowcharts/ # .mmd input fixtures + expected .txt outputs
```

### Architecture

There are two rendering paths:

**Path A — Flowcharts and state diagrams** use the shared `Graph` model with the grid layout engine and A* edge routing (`layout/` + `routing/` + `renderer/draw.py`).

**Path B — All other diagram types** (sequence, class, ER, block, git graph) have their own model (`model/`), parser (`parser/`), and renderer (`renderer/`) that draw directly onto a `Canvas`.

### Diagram dispatch

Both `render()` and `render_rich()` auto-detect the diagram type from the source text prefix (e.g. `sequenceDiagram`, `classDiagram`, `gitGraph`) and dispatch to the appropriate parser + renderer.

## Adding a new diagram type

1. Create the model in `src/termmaid/model/yourdiagram.py` (dataclasses)
2. Create the parser in `src/termmaid/parser/yourdiagram.py`
3. Create the renderer in `src/termmaid/renderer/yourdiagram.py` (returns a `Canvas`)
4. Add dispatch in `src/termmaid/__init__.py` (both `render()` and `render_rich()`)
5. Add tests

## Adding a new node shape

1. Add the shape to `NodeShape` enum in `src/termmaid/graph/shapes.py`
2. Add parser detection in `src/termmaid/parser/flowchart.py` (`_parse_node`)
3. Add renderer in `src/termmaid/renderer/shapes/__init__.py`
4. Register in `SHAPE_RENDERERS` dict
5. Add tests in `tests/test_shapes.py`

## Adding a test fixture

1. Create `tests/fixtures/flowcharts/my_test.mmd`
2. Run `uv run pytest tests/test_renderer.py -q` — it auto-generates the expected output
3. Review the generated `.txt` file in `tests/fixtures/expected/`
4. Run again to confirm it passes
