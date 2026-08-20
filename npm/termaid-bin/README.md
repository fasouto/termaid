# @tayomi/termaid-bin

Unofficial prebuilt binaries of [termaid](https://github.com/fasouto/termaid) by Fabio Souto: Mermaid diagrams rendered as Unicode art in the terminal, without needing Python installed.

This package authors nothing: it repackages binaries compiled (Nuitka) by the CI of [mopi1402/termaid](https://github.com/mopi1402/termaid), a fork that only adds the build pipeline. All credit for termaid itself goes to its author. MIT, upstream license included.

## How it works

Installing this package pulls exactly one `optionalDependency`: the platform package matching your `os`/`cpu` (darwin-arm64, darwin-x64, linux-x64, linux-arm64, win32-x64). The binary arrives through npm, integrity-checked by your lockfile, with no postinstall script and no network fetch at runtime.

```js
const { termaidPath } = require("@tayomi/termaid-bin");

termaidPath(); // absolute path of the binary, or null on an unsupported platform
```

```sh
$(node -p 'require("@tayomi/termaid-bin").termaidPath()') --demo flowchart
```
