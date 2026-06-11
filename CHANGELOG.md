# Changelog

## 0.7.1 (2026-06-11)

### Fixes
- Gantt: the widest task label is no longer truncated (the margin was sized 2 columns short of its own content)
- Kanban: the widest card is no longer truncated (same off-by-two in column sizing); `id[Title]` cards with trailing `@metadata` now unwrap correctly
- CJK/emoji labels no longer overflow boxes or destroy borders in class, ER, gantt, kanban, packet, and treemap renderers; new shared `truncate_to_width()` helper never splits a wide character
- Sequence: self-messages reserve the rows they draw, so the next message's label no longer overwrites the loop's return arrow; CJK message labels are no longer clipped
- Block diagrams: blocks nested two or more groups deep are rendered instead of silently dropped

## 0.7.0 (2026-06-11)

### Behavior changes
- `render()` and `render_rich()` now raise exceptions on failure instead of returning an error string; the CLI reports errors on stderr and exits with code 1 (previously it exited 0 with the error in stdout or the `-o` file)
- `render_rich()` accepts a `gap` parameter

### Fixes
- `--theme` no longer silently ignores `-o` (ANSI output is written to the file), `--show-ids`, `--gap`, and `--width`/auto-fit
- Missing `rich` with `--theme` now prints the install hint instead of a raw ImportError
- Flowchart: semicolons inside quoted labels (`A["a;b"]`) no longer split the statement
- Sequence: inline `-` activation marker deactivates the sender, not the receiver, matching Mermaid semantics
- Gantt: the `dateFormat` directive is honored (e.g. `DD-MM-YYYY`); non-ISO dates no longer silently drop task bars
- Kanban: `id[Title]` syntax is supported for columns and cards
- Quadrant/XY chart: malformed numbers like `0.1.2` no longer crash the parser
- State diagram: notes and redeclarations no longer reset `<<choice>>`/`<<fork>>`/`<<join>>` shapes
- Canvas: wide (CJK) characters at out-of-bounds positions no longer crash or corrupt rows
- Layout: orthogonal subgraphs containing a cycle no longer drop or duplicate nodes
- File I/O uses explicit UTF-8 encoding
- `--version` fallback no longer reports a stale version

## 0.6.1 (2026-03-30)

### Fixes
- Fix emoji display width: characters like 🗄 and 🖥 now correctly treated as 2 columns wide, fixing box alignment in architecture diagrams and any label containing emoji

## 0.6.0 (2026-03-30)

### New diagram types
- **Gantt chart** (`gantt`): horizontal bar chart with sections, task tags (done/active/crit/milestone), `after` dependencies, duration syntax, auto-chaining, vertical markers, today marker
- **Architecture diagram** (`architecture-beta`): service/group/junction layout with L/R/T/B direction hints for 2D grid positioning, icon prefixes, invisible junction elimination
- 18 diagram types now supported

## 0.5.0 (2026-03-29)

### New diagram types
- **XY Chart** (`xychart-beta` / `xychart`): bar charts, line charts, bar+line combos, horizontal orientation, rounded/sharp line corners, JSON ingest
- **User Journey** (`journey`): horizontal task timeline with sections, satisfaction emoji scores, multi-actor symbols (●◆■▲), rounded/sharp/ASCII corners
- **Packet diagram** (`packet` / `packet-beta`): bit-aligned network packet layouts with separated boxes per row, boundary numbers, auto-increment (`+N`) syntax, truncated label legend with bit ranges
- 16 diagram types now supported

### Improvements
- CJK/wide character display width fix (merged from community PR)
- Applied `display_width()` to all new renderers
- XY chart: even y-axis proportions, rounded line corners
- Packet: smart number placement (skip crowded single-bit fields)

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
