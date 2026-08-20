// Stages the npm packages for one release: five platform packages, each carrying one compiled binary,
// and the @tayomi/termaid-bin meta package pinning them as optionalDependencies.
//
// Shared by the CI and a local dry-run, so what publishes is exactly what was rehearsed:
//   node scripts/stage-npm.mjs <version> <assets-dir> <out-dir>
// <assets-dir> holds the release assets (termaid-<target>[.exe]) the binaries job uploaded.

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const META_SRC = path.join(ROOT, "npm", "termaid-bin");
const LICENSE = path.join(ROOT, "LICENSE");
const SCOPE = "@tayomi/termaid-bin";
const UPSTREAM = "https://github.com/fasouto/termaid";
const FORK = "git+https://github.com/mopi1402/termaid.git";
const EXEC_MODE = 0o755;

// Asset names speak the CI matrix's words, package names speak npm's (process.platform / os,cpu).
const TARGETS = [
  { asset: "termaid-darwin-arm64", suffix: "darwin-arm64", os: "darwin", cpu: "arm64", bin: "termaid" },
  { asset: "termaid-darwin-x64", suffix: "darwin-x64", os: "darwin", cpu: "x64", bin: "termaid" },
  { asset: "termaid-linux-x64", suffix: "linux-x64", os: "linux", cpu: "x64", bin: "termaid" },
  { asset: "termaid-linux-arm64", suffix: "linux-arm64", os: "linux", cpu: "arm64", bin: "termaid" },
  { asset: "termaid-windows-x64.exe", suffix: "win32-x64", os: "win32", cpu: "x64", bin: "termaid.exe" },
];

const [version, assetsDir, outDir] = process.argv.slice(2);
if (!version || !assetsDir || !outDir) {
  console.error("usage: node scripts/stage-npm.mjs <version> <assets-dir> <out-dir>");
  process.exit(1);
}

const write = (dir, name, value) =>
  fs.writeFileSync(path.join(dir, name), `${JSON.stringify(value, null, 2)}\n`);

const pins = {};
for (const t of TARGETS) {
  const name = `${SCOPE}-${t.suffix}`;
  const src = path.join(assetsDir, t.asset);
  if (!fs.existsSync(src)) {
    console.error(`stage-npm: missing asset ${src}`);
    process.exit(1);
  }
  const dir = path.join(outDir, `termaid-bin-${t.suffix}`);
  fs.mkdirSync(dir, { recursive: true });
  write(dir, "package.json", {
    name,
    version,
    description: `Unofficial prebuilt termaid binary (${t.suffix}). termaid is by Fabio Souto (${UPSTREAM}); this package only redistributes a compiled binary.`,
    license: "MIT",
    os: [t.os],
    cpu: [t.cpu],
    files: [t.bin],
    repository: { type: "git", url: FORK },
    homepage: UPSTREAM,
  });
  fs.copyFileSync(src, path.join(dir, t.bin));
  fs.chmodSync(path.join(dir, t.bin), EXEC_MODE);
  fs.copyFileSync(LICENSE, path.join(dir, "LICENSE"));
  pins[name] = version;
}

// The meta package: sources copied as written, version and exact pins stamped. Exact on purpose:
// a meta at X installing a platform at Y is two releases pretending to be one.
const meta = path.join(outDir, "termaid-bin");
fs.mkdirSync(meta, { recursive: true });
for (const f of fs.readdirSync(META_SRC)) fs.copyFileSync(path.join(META_SRC, f), path.join(meta, f));
fs.copyFileSync(LICENSE, path.join(meta, "LICENSE"));
const pkg = JSON.parse(fs.readFileSync(path.join(meta, "package.json"), "utf8"));
pkg.version = version;
pkg.optionalDependencies = pins;
write(meta, "package.json", pkg);

console.log(`stage-npm: staged ${TARGETS.length} platform packages + meta at ${version} in ${outDir}`);
