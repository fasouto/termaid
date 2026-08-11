// Resolves the termaid binary this machine's optional platform package installed.
// CommonJS on purpose: consumable by require() and import alike, on any Node still in service.
"use strict";

const fs = require("node:fs");
const path = require("node:path");

// npm's own platform words (process.platform / process.arch), which the os/cpu fields already speak.
const PLATFORMS = {
  "darwin arm64": "@tayomi/termaid-bin-darwin-arm64",
  "darwin x64": "@tayomi/termaid-bin-darwin-x64",
  "linux x64": "@tayomi/termaid-bin-linux-x64",
  "linux arm64": "@tayomi/termaid-bin-linux-arm64",
  "win32 x64": "@tayomi/termaid-bin-win32-x64",
};

const BINARY = process.platform === "win32" ? "termaid.exe" : "termaid";

/**
 * Absolute path of the installed termaid binary, or null: unsupported platform, or the optional
 * dependency was skipped (--no-optional, unsupported os/cpu, offline install).
 */
function termaidPath() {
  const pkg = PLATFORMS[`${process.platform} ${process.arch}`];
  if (pkg === undefined) return null;
  let dir;
  try {
    dir = path.dirname(require.resolve(`${pkg}/package.json`));
  } catch {
    return null;
  }
  const bin = path.join(dir, BINARY);
  return fs.existsSync(bin) ? bin : null;
}

module.exports = { termaidPath };
