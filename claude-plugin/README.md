# termaid for Claude Code

This plugin draws the Mermaid diagrams in Claude's replies as text diagrams, in place. They are fitted to the width of your terminal. Only the display changes. The transcript keeps the Mermaid source.

## Skill

The `/termaid:mermaid` skill draws diagrams that live in files, Markdown documents and PR descriptions.

## What it runs

The plugin has one MessageDisplay hook. The hook runs `python3` on the copy of termaid bundled in `lib/`. It runs locally and uses no network access.

The hook keeps a small state file for each message in a private folder under the system temp directory. This lets it draw a diagram that is split across several streamed batches.

## Requirements

You need Python 3.9 or later, available as `python3`. macOS and most Linux systems include it. Without it the plugin does nothing, and replies show as written.

## Source

The `lib/` folder is generated from https://github.com/fasouto/termaid by each release. Send changes there, not to this branch.

## License

MIT
