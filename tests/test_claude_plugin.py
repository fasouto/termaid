"""The Claude Code plugin build: its tree, idempotence, and the bundled launcher."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import termaid

REPO = Path(__file__).resolve().parent.parent
BUILD_SCRIPT = REPO / "scripts" / "build_claude_plugin.py"

EVENT = {
    "hook_event_name": "MessageDisplay",
    "delta": "Here:\n```mermaid\ngraph LR\n  A-->B\n```\n",
    "final": True,
}


def _build(out):
    result = subprocess.run(
        [sys.executable, str(BUILD_SCRIPT), str(out)],
        capture_output=True, text=True, cwd=str(out.parent),
    )
    assert result.returncode == 0, result.stderr
    return out


@pytest.fixture
def built(tmp_path):
    return _build(tmp_path / "plugin")


def _snapshot(root):
    return {
        str(p.relative_to(root)): (p.read_bytes() if p.is_file() else None)
        for p in sorted(root.rglob("*"))
    }


def _launcher(root, *args, stdin="", env_extra=None):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env.update(env_extra or {})
    return subprocess.run(
        [sys.executable, "-I", "-S", str(root / "scripts" / "termaid.py"), *args],
        input=stdin, capture_output=True, encoding="utf-8", env=env, cwd=str(root.parent),
    )


def test_build_tree(built):
    plugin = json.loads((built / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert plugin["version"] == termaid.__version__
    assert (built / "lib" / "termaid" / "__init__.py").is_file()
    assert (built / "LICENSE").is_file()
    assert (built / "skills" / "mermaid" / "SKILL.md").is_file()
    assert not [p for p in built.rglob("*") if p.name == "__pycache__" or p.suffix == ".pyc"]

    readme = re.sub(r"```.*?```", "", (built / "README.md").read_text(encoding="utf-8"), flags=re.S)
    assert len(readme.split()) >= 40

    hooks = json.loads((built / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    command = hooks["hooks"]["MessageDisplay"][0]["hooks"][0]["command"]
    assert "scripts/termaid.py" in command
    assert (built / "scripts" / "termaid.py").is_file()
    assert not (built / "bin").exists()


def _run_hook_command(root, bin_dir):
    hooks = json.loads((root / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    command = hooks["hooks"]["MessageDisplay"][0]["hooks"][0]["command"]
    env = {"PATH": str(bin_dir), "CLAUDE_PLUGIN_ROOT": str(root), "COLUMNS": "80"}
    return subprocess.run(["/bin/sh", "-c", command], input=json.dumps(EVENT),
                          capture_output=True, encoding="utf-8", env=env)


def _fake_program(path, body):
    path.write_text("#!/bin/sh\n" + body + "\n")
    path.chmod(0o755)


@pytest.mark.skipif(not os.path.exists("/bin/sh"), reason="runs the hook command in a POSIX shell")
@pytest.mark.parametrize("python3", [None, "exit 49"])
def test_hook_command_falls_back_to_python(built, tmp_path, python3):
    # On Windows, python3 is often only the Microsoft Store stub, which fails,
    # while Python itself is installed as python.
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    if python3:
        _fake_program(bin_dir / "python3", python3)
    _fake_program(bin_dir / "python", f'exec "{sys.executable}" "$@"')
    result = _run_hook_command(built, bin_dir)
    assert result.returncode == 0, result.stderr
    assert "┌" in json.loads(result.stdout)["hookSpecificOutput"]["displayContent"]


@pytest.mark.skipif(not os.path.exists("/bin/sh"), reason="runs the hook command in a POSIX shell")
def test_hook_command_without_python_does_nothing(built, tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_program(bin_dir / "python3", "exit 49")
    result = _run_hook_command(built, bin_dir)
    assert (result.returncode, result.stdout) == (0, "")


def test_build_is_idempotent_and_clears_output(built):
    (built / ".git").mkdir()
    (built / ".git" / "HEAD").write_text("ref")
    (built / "stray.txt").write_text("x")
    (built / "lib" / "stale.py").write_text("x")
    before = _snapshot(built)
    _build(built)
    after = _snapshot(built)
    assert "stray.txt" not in after
    assert str(Path("lib") / "stale.py") not in after
    assert (built / ".git" / "HEAD").read_text(encoding="utf-8") == "ref"
    del before["stray.txt"], before[str(Path("lib") / "stale.py")]
    assert before == after
    _build(built)
    assert _snapshot(built) == after


def test_hook_works_from_the_build_alone(built):
    result = _launcher(
        built, "--claude-hook", stdin=json.dumps(EVENT), env_extra={"COLUMNS": "80"}
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)["hookSpecificOutput"]["displayContent"]
    assert "┌" in out
    assert "```mermaid" not in out


def test_missing_lib(built):
    import shutil

    shutil.rmtree(built / "lib")
    hook = _launcher(built, "--claude-hook", stdin=json.dumps(EVENT))
    assert hook.returncode == 0
    assert hook.stdout == ""
    cli = _launcher(built, "diagram.mmd")
    assert cli.returncode == 1
    assert cli.stderr.strip()


def test_cli_through_launcher_reads_stdin(built):
    result = _launcher(built, "--width", "80", stdin="graph LR\n  A-->B\n")
    assert result.returncode == 0, result.stderr
    assert "┌" in result.stdout

