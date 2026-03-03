# termmaid

Render [Mermaid](https://mermaid.js.org/) diagrams as Unicode art in the terminal. Pure Python, zero dependencies.

```
┌─────────┐    ┌───────────┐    ┌───◇───┐    ╭────────╮
│         │    │           │    │       │Yes (        )
│  Start  ├───►│  Process  ├───►│  OK?  ├───►(  Done  )
│         │    │           │    │       │    (        )
└─────────┘    └───────────┘    └───◇───┘    ╰────────╯
```

## Why?

I needed Mermaid rendering for a Python project and couldn't find a library that worked
without a browser, Node.js, or external services. The existing tools in this space are
great, specially [mermaid-ascii](https://github.com/AlexanderGrooff/mermaid-ascii) (Go) and
[beautiful-mermaid](https://github.com/lukilabs/beautiful-mermaid) (TypeScript), but
neither offered a native Python library I could import and call directly.

## Install

```bash
pip install termmaid
```

## Quick start

### CLI

```bash
termmaid diagram.mmd
echo "graph LR; A-->B-->C" | termmaid
termmaid diagram.mmd --color --theme neon
termmaid diagram.mmd --ascii
```

### Python

```python
from termmaid import render

print(render("graph LR\n  A --> B --> C"))
```

```python
# Colored output (requires: pip install termmaid[rich])
from termmaid import render_rich
from rich import print as rprint

rprint(render_rich("graph LR\n  A --> B", theme="terra"))
```

```python
# Textual TUI widget (requires: pip install termmaid[textual])
from termmaid import MermaidWidget

widget = MermaidWidget("graph LR\n  A --> B")
```

## Supported diagram types

### Flowcharts

All five directions: `LR`, `RL`, `TD`/`TB`, `BT`

```mermaid
graph TD
    A[Start] --> B{Is valid?}
    B -->|Yes| C(Process)
    C --> D([Done])
    B -->|No| E[Error]
```

```
┌─────────────┐
│             │
│    Start    │
│             │
└──────┬──────┘
       │
       ▼
┌──────◇──────┐
│             │
│  Is valid?  │
│             │
└──────◇──────┘
       │No
       ╰Yes─────────────╮
       ▼                ▼
╭─────────────╮    ┌─────────┐
│             │    │         │
│   Process   │    │  Error  │
│             │    │         │
╰──────┬──────╯    └─────────┘
       │
       ▼
╭─────────────╮
(             )
(    Done     )
(             )
╰─────────────╯
```

**Node shapes:** rectangle `[text]`, rounded `(text)`, diamond `{text}`, stadium `([text])`, subroutine `[[text]]`, circle `((text))`, double circle `(((text)))`, hexagon `{{text}}`, cylinder `[(text)]`, asymmetric `>text]`, parallelogram `[/text/]`, trapezoid `[/text\]`, and `@{shape}` syntax

**Edge styles:** solid `-->`, dotted `-.->`, thick `==>`, bidirectional `<-->`, labeled `-->|text|`, variable length `--->`, `---->`

**Styling:** `classDef`, `style`, `linkStyle` directives, `:::className` suffix

**Subgraphs:** nesting, cross-boundary edges, per-subgraph `direction` override

**Other:** `%%` comments, `;` line separators, Markdown labels `` "`**bold** *italic*`" ``, `&` operator (`A & B --> C`)

### Sequence diagrams

```mermaid
sequenceDiagram
    Alice->>Bob: Hello Bob
    Bob-->>Alice: Hi Alice
    Alice->>Bob: How are you?
    Bob-->>Alice: Great!
```

```
 ┌──────────┐      ┌──────────┐
 │  Alice   │      │   Bob    │
 └──────────┘      └──────────┘
       ┆ Hello Bob       ┆
       ──────────────────►
       ┆ Hi Alice        ┆
       ◄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
       ┆ How are you?    ┆
       ──────────────────►
       ┆ Great!          ┆
       ◄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
       ┆                 ┆
```

**Message types:** solid arrow `->>`, dashed arrow `-->>`, solid line `->`, dashed line `-->`

**Participants:** `participant`, `actor`, aliases

### Class diagrams

```mermaid
classDiagram
    class Animal {
        +String name
        +int age
        +makeSound()
    }
    class Dog {
        +String breed
        +fetch()
    }
    Animal <|-- Dog
```

```
  ┌──────────────┐
  │    Animal    │
  ├──────────────┤
  │ +String name │
  │ +int age     │
  ├──────────────┤
  │ +makeSound() │
  └──────────────┘
          △
          │
          │
          │
  ┌───────────────┐
  │      Dog      │
  ├───────────────┤
  │ +String breed │
  ├───────────────┤
  │ +fetch()      │
  └───────────────┘
```

**Relationships:** inheritance `<|--`, composition `*--`, aggregation `o--`, association `--`, dependency `..>`, realization `..|>`

**Members:** attributes and methods with visibility (`+` public, `-` private, `#` protected, `~` package)

### ER diagrams

```mermaid
erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ LINE-ITEM : contains
```

```
  ┌──────────────┐
  │   CUSTOMER   │
  └──────────────┘
          │1
          └─places──┐
                    │
                    │0..*
            ┌──────────────┐
            │    ORDER     │
            └──────────────┘
                    │1
                    └─contains──┐
                                │
                                │1..*
                        ┌──────────────┐
                        │  LINE-ITEM   │
                        └──────────────┘
```

**Cardinality:** `||` (exactly one), `o|` (zero or one), `}|` (one or more), `o{` (zero or more)

**Line styles:** solid `--`, dashed `..`

**Attributes:** type, name, keys (`PK`, `FK`, `UK`), comments

### State diagrams

```mermaid
stateDiagram-v2
    [*] --> Idle
    Idle --> Processing : start
    Processing --> Done : complete
    Done --> [*]
```

```
╭───────◯──────╮
│              │
│      ●       │
│              │
╰───────◯──────╯
        │
        ▼
╭──────────────╮
│              │
│     Idle     │
│              │
╰───────┬──────╯
        │start
        ▼
╭──────────────╮
│              │
│  Processing  │
│              │
╰───────┬──────╯
        │complete
        ▼
╭──────────────╮
│              │
│     Done     │
│              │
╰───────┬──────╯
        │
        ▼
╭───────◯──────╮
│              │
│      ◉       │
│              │
╰───────◯──────╯
```

**Features:** `[*]` start/end states, transition labels, `state "name" as alias`, composite states (`state Parent { }`), stereotypes (`<<choice>>`, `<<fork>>`, `<<join>>`)

### Block diagrams

```mermaid
block-beta
    columns 3
    A["Frontend"] B["API"] C["Database"]
```

```
  ┌──────────┐    ┌──────────┐    ┌──────────┐
  │          │    │          │    │          │
  │ Frontend │    │   API    │    │ Database │
  │          │    │          │    │          │
  └──────────┘    └──────────┘    └──────────┘
```

**Features:** `columns N`, column spanning (`blockname:N`), links between blocks, nested blocks

### Git graphs

```mermaid
gitGraph
   commit id: "init"
   commit id: "feat"
   branch develop
   commit id: "dev-1"
   commit id: "dev-2"
   checkout main
   commit id: "fix"
   merge develop id: "merge"
```

```
  main    ───●─────●──────┼──────────────●──────●─
           init  feat     │             fix   merge
                          │                     │
  develop                 ●───────●─────────────┼
                        dev-1   dev-2
```

**Directions:** `LR` (default), `TB`, `BT`

**Commands:** `commit` (with `id:`, `type:`, `tag:`), `branch` (with `order:`), `checkout`/`switch`, `merge`, `cherry-pick`

**Commit types:** `NORMAL` (●), `REVERSE` (✖), `HIGHLIGHT` (■)

**Config:** `%%{init: {"gitGraph": {"mainBranchName": "master"}}}%%`

## CLI options

| Flag | Description |
|------|-------------|
| `--ascii` | ASCII-only output (no Unicode box-drawing) |
| `--color` | Colored output (requires `pip install termmaid[rich]`) |
| `--theme NAME` | Color theme: `default`, `terra`, `neon`, `mono`, `amber`, `phosphor` |
| `--padding-x N` | Horizontal padding inside boxes (default: 4) |
| `--padding-y N` | Vertical padding inside boxes (default: 2) |
| `--sharp-edges` | Sharp corners on edge turns instead of rounded |

## Python API

### `render(source, *, use_ascii=False, padding_x=4, padding_y=2, rounded_edges=True) -> str`

Render a Mermaid diagram as a plain text string. Auto-detects diagram type.

### `render_rich(source, *, use_ascii=False, padding_x=4, padding_y=2, rounded_edges=True, theme="default") -> rich.text.Text`

Render as a [Rich](https://rich.readthedocs.io/) `Text` object with colors. Requires `pip install termmaid[rich]`.

### `MermaidWidget`

A [Textual](https://textual.textualize.io/) widget with a reactive `source` attribute. Requires `pip install termmaid[textual]`.

```python
from termmaid import MermaidWidget

class MyApp(App):
    def compose(self):
        yield MermaidWidget("graph LR\n  A --> B")
```

## Themes

Six built-in color themes for `--color` / `render_rich()`:

| Theme | Description |
|-------|-------------|
| `default` | Cyan nodes, yellow arrows, white labels |
| `terra` | Warm earth tones (browns, oranges) |
| `neon` | Magenta nodes, green arrows, cyan edges |
| `mono` | White/gray monochrome |
| `amber` | Amber/gold CRT-style |
| `phosphor` | Green phosphor terminal-style |

## Optional extras

```bash
pip install termmaid[rich]      # Colored terminal output
pip install termmaid[textual]   # Textual TUI widget
```

## Limitations

- **Layout engine is approximate.** Node positioning uses a fixed-stride grid with a barycenter heuristic (up to 8 passes with improvement tracking). Graphs with many cross-layer edges may still produce crossings.
- **Manhattan-only edge routing.** Edges use A* pathfinding (4-directional, capped at 5,000 iterations). Dense graphs may have overlapping edges.

## Acknowledgements

Inspired by [mermaid-ascii](https://github.com/AlexanderGrooff/mermaid-ascii) by Alexander Grooff
and [beautiful-mermaid](https://github.com/lukilabs/beautiful-mermaid) by Lukilabs.

## License

MIT
