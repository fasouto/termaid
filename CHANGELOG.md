# Changelog

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
