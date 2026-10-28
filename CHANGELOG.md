# Changelog

## Unreleased

### Fixes
- Sequence: a message label keeps its spaces where it crosses another participant's lifeline, so the lifeline no longer shows through a gap between two words (`no opening┆hours`)

## 0.10.0 (2026-10-25)

### New
- Claude Code integration: `termaid --claude-hook` runs as a `MessageDisplay` hook and draws the mermaid blocks in Claude's replies in place while they stream, holding a fence that spans batches until it closes. The repo doubles as a plugin marketplace (`/plugin install termaid --marketplace fasouto/termaid`) that installs the hook and a `/termaid:mermaid` skill
- Wrap-mode fitting: when `--width` cannot fit a diagram by tightening spacing alone, labels now wrap at word boundaries (sequence participants, messages, notes and frame titles; flowchart node and edge labels) and termaid keeps the widest wrap that fits. A diagram that already fits renders exactly as before
- `--strict-width`: exit with status 2 instead of a warning when the output is still wider than `--width`
- `--max-height ROWS`: exit with status 2 when the output has more lines than `ROWS`
- `--format styled-json` prints the diagram as one JSON document of text chunks tagged with style keys (`node`, `edge`, `class:<name>`, ...), for editors and tools that color the output themselves. `termaid.render_styled()` returns the same document
- `--diagnostics-format json` prints each error and warning on stderr as a versioned JSON line with a stable `code`, argument errors included
- Python API: `render()` and `render_rich()` take `max_label_width` to wrap labels in flowcharts and sequence diagrams
- Gantt charts at any time scale: dates keep their time of day, `dateFormat` accepts the dayjs tokens `HH:mm:ss`, `SSS`, `x` (Unix milliseconds) and `X` (Unix seconds, both read as UTC), durations take Mermaid's units `ms`, `s`, `m`, `h`, `d`, `w`, `M`, `y` with decimals (`1.5h`), `axisFormat` labels the axis with d3 directives including `%L`, and `tickInterval` places ticks every N units
- The styled output, the JSON diagnostics, the wrap-mode fitting and the two strict flags come from @BeckWlim's proposal and fork in #11, ported to the current layout code

### Behavior changes
- `--width` must be positive. `--width 0` now exits with status 2 instead of being accepted
- `render_rich()` honors `padding_x`, `padding_y`, `gap` and `rounded_edges` for architecture, journey, mindmap and packet diagrams the way `render()` does, so colored and plain output have the same layout
- `termaid --demo` with an unknown type now prefixes its message with `Error:` like every other error
- Input that draws nothing (a comment-only file, text that is not a diagram) now exits with status 1 and the `render_empty` diagnostic instead of printing nothing with status 0
- Gantt durations follow Mermaid's case-sensitive units: `3m` is now 3 minutes (it was 90 days) and `3M` is 3 calendar months. `30D` is no longer a duration. The long spellings `days`, `weeks` and `months` still work
- The blank between two words of a label now carries the label's style, so solid themes (`dracula`, `nord`, ...) no longer leave a differently colored gap inside a label, and styled JSON emits one chunk per label

### Fixes
- Flowchart subgraphs: a node mentioned inside two subgraphs now belongs only to the first one that closes, as in Mermaid. The two boxes no longer overlap or share a border row, and every subgraph border gets its own row with its padding and label space
- Flowchart subgraphs: an edge from a node in one subgraph to a node in the subgraph below now leaves through the bottom border and enters through the top border, going around sibling nodes inside the box instead of running down outside it. A box widens over the gap column beside its nodes only when one of its own edges runs there
- Flowcharts: two edges with neither a source nor a target in common no longer run along the same line or meet at a T junction, so a line no longer appears to lead to a node it does not reach. Such edges may still cross. Where an edge would otherwise have to share a line between two layers, that gap grows by one row (one column in LR diagrams), so it keeps its usual sides instead of leaving or arriving sideways
- Cylinder nodes (`[(DB)]`, sequence `database` participants): the second row is now the front rim of the lid, drawn inside the sides (`│╰──╯│`, `|\__/|` in ASCII), so the top no longer reads as a flat box stacked on another box
- Gantt: a task written as `after x, 2024-04-05` ends on that date instead of starting on it, so the tasks chained after it get their bars
- Flowchart: `%%` inside a quoted label is label text, not the start of a comment, so `A["50%% off"] --> B` keeps its edge
- Flowchart: `:::` inside a quoted label no longer assigns a class, so `A["a:::b"]` keeps its whole label
- Flowchart: entity codes in node labels, edge labels and subgraph titles are decoded, as in Mermaid (`#quot;`, `#amp;`, `#lt;` and other HTML names, decimal codes such as `#9829;`)

## 0.9.1 (2026-10-18)

### New
- `--markdown`: read a Markdown document (a README, a PR description, an LLM's reply) and draw each ```` ```mermaid ```` block in place, passing the rest of the text through. Diagrams inside list items keep their indentation, mermaid examples quoted inside a longer code fence are left alone, and a block that cannot be drawn is kept as source with a warning on stderr

### Fixes
- Flowchart layout: nodes now line up with their own parents and parents are centred over their children, so a node is no longer drawn next to an unrelated node in the same rank (#14). Fan-outs are symmetric and trees spread like trees; diagrams with subgraphs keep the previous packed layout.

## 0.9.0 (2026-09-15)

### New
- XY charts: the y-axis title is drawn (above the ticks in vertical charts, under the value axis in horizontal ones), and horizontal charts now render line series instead of falling back to vertical

### Behavior changes
- Sequence: block frames (alt, loop, par, ...) span only the participants they involve, matching Mermaid, instead of every lifeline
- Class and ER diagrams: several relationships leaving or entering the same box are spread further apart, and lines that jog sideways between layers each get their own row, so the gap between layers grows with the number of crossings

### Fixes
- Sequence scope frames now enclose their messages, notes, branches, and nested frames. Deep nesting no longer crosses message arrows, and long scope titles remain inside their borders.
- Sequence: else/and section labels keep their spaces instead of being drawn with dashes
- Flowchart: open links with a label (`A ---|text| B`) no longer get an arrowhead
- Flowchart: `A -- text --> B` is a normal-length link again; the leading dashes were being counted as extra length, which stretched the layout
- Flowchart: sibling subgraphs kept the same order between runs only by luck (hash order); layout is now deterministic
- State diagrams: transitions to or from a composite state attach to its border instead of drawing a duplicate plain state next to it
- Class and ER diagrams: relationship labels and cardinalities are drawn after all lines, so a later line no longer erases them; side-by-side boxes are joined with a straight line instead of a kinked one; two relationships between the same pair of classes get separate rows instead of overwriting each other; cardinalities no longer land on a box border

## 0.8.0 (2026-07-29)

### New
- Flowchart: edges can link subgraphs directly (`A --> B` where A and B are subgraphs), matching Mermaid semantics. All mixed forms work too: subgraph to node, node to subgraph, and links across subgraphs. Edges attach to the subgraph border with a proper tee and arrowhead instead of grabbing an inner node (#6)

### Fixes
- Flowchart layout: edges with subgraph endpoints now constrain layer assignment, so chains like `A --> C --> B` stack vertically instead of piling into overlapping rows
- Flowchart layout: the space between subgraph boxes is sized by counting the actual borders in each gap; sibling boxes no longer touch when a standalone node shares a row, and the workaround of passing a large `--gap` is no longer needed
- Flowchart routing: edges no longer cut through unrelated subgraph boxes when a route around them exists

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
