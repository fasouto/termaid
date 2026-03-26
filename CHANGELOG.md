# Changelog

## 0.4.0 (2026-03-26)

### New diagram types
- **Timeline** (`timeline` syntax): vertical event list with sections and details
- **Kanban** (`kanban` syntax): column-based task boards with cards
- **Quadrant chart** (`quadrantChart` syntax): 2x2 grid with plotted data points
- 13 diagram types now supported

### New themes
- **Solid-background themes**: `gruvbox`, `monokai`, `dracula`, `nord`, `solarized` with filled region backgrounds
- Per-section coloring: kanban columns, quadrant regions, and timeline sections get distinct colors
- Depth shading: kanban cards use a lighter shade of the column color
- `--themes` flag to list all available themes

### New features
- **JSON ingest** (`--json TYPE`): pipe structured data and render as treemap, pie, mindmap, or flowchart
- **`--demo [TYPE]`**: render sample diagrams for any diagram type
- **`padding_x` and `gap`** now supported by sequence, class, ER, block, and kanban renderers
- Parser fix: edge labels with quoted text (`-->|"Yes"|`) no longer rendered as spaces

## 0.3.0 (2026-03-25)

### Rendering engine overhaul

- **Directional canvas**: junction characters derived from direction bitfields instead of a lookup table, producing correct junctions in all cases
- **Gap expansion**: crossing edges between layers automatically get extra routing space so they no longer overlap
- **Endpoint spreading**: overlapping arrows on the same node border are spread apart so all edges are visible
- **Subgraph separation**: nodes stay inside their declared subgraph even with cross-boundary edges
- **Routing bias**: edges prefer the natural flow direction, avoiding tight corners next to node borders
- **Label separation**: edge labels from different edges no longer merge onto the same output line
- **Parser fix**: arrow syntax inside quoted labels (`A["has --> arrow"]`) no longer confuses the parser

### New diagram type

- **Mindmaps** (`mindmap` syntax): indentation-based tree layout with automatic overflow to the left for crowded roots, rounded/sharp/ASCII branch characters

### CLI improvements

- `--width N`: set max output width, re-renders with smaller gap/padding if exceeded
- `-o FILE` / `--output FILE`: write output to file instead of stdout
- `--show-ids`: show node IDs alongside labels for debugging
- `--no-auto-fit`: disable automatic terminal width compaction
- `NO_COLOR` environment variable respected
- `--version` reads from package metadata instead of hardcoded string
- Auto-fit: diagrams that exceed terminal width are automatically re-rendered with compact settings

### Code quality

- Layout engine split from 1 file (1095 lines) into 5 focused modules
- 1066 tests, 0 failures, 0 xfails (up from 1004 tests, 5 xfails)
- Gallery script and docs/gallery.md with all 78 fixture diagrams

## 0.2.1 (2026-03-25)

- Add `--gap` CLI flag and `gap` parameter for compact diagram spacing
- Document wide LR diagram workarounds in README

## 0.2.0 (2026-03-20)

- Add pie chart support (`pie` syntax, rendered as horizontal bar charts)
- Add treemap support (`treemap-beta` syntax with nested sections and proportional sizing)
- 9 diagram types now supported

## 0.1.3 (2026-03-04)

- Add `--tui` flag to CLI for interactive TUI viewer
- Update demo GIF with pipe and TUI examples

## 0.1.1 (2026-03-04)

- Rename package from `termmaid` to `termaid`

## 0.1.0 (2026-03-04)

Initial release.

### Features

- **7 diagram types:** flowcharts, sequence, class, ER, state, block, and git graphs
- **Flowcharts** (`graph`/`flowchart`) with all 5 directions (`LR`, `RL`, `TD`/`TB`, `BT`)
- **Sequence diagrams** with participants, actors, solid/dashed messages
- **Class diagrams** with attributes, methods, visibility, and 6 relationship types
- **ER diagrams** with cardinality, attributes, keys, and relationship labels
- **State diagrams** (`stateDiagram-v2`) with transitions, composite states, stereotypes
- **Block diagrams** (`block-beta`) with column layout and spanning
- **Git graphs** (`gitGraph`) with branches, merges, cherry-picks, tags, and 3 orientations
- 14 flowchart node shapes: rectangle, rounded, stadium, subroutine, diamond, hexagon, circle, double circle, asymmetric, cylinder, parallelogram, parallelogram alt, trapezoid, trapezoid alt
- 3 edge styles: solid, dotted, thick
- Bidirectional edges (`<-->`, `<-.->`, `<==>`)
- Edge labels (`-->|label|`)
- Subgraphs with nesting and cross-boundary edges
- `classDef`, `style`, and `linkStyle` directives
- `@{shape}` node syntax
- Link length control (`--->`, `---->`)
- Markdown labels (`**bold**`, `*italic*`)
- ASCII mode (`--ascii`) for terminals without Unicode support
- Colored output via Rich (`--color`) with 6 built-in themes
- Textual widget for TUI applications
- CLI tool with stdin/file input
- Pure Python, zero runtime dependencies
