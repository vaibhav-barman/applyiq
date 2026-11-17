"""PostToolUse hook: auto-format the file Claude just edited.

Claude Code sends the tool call as JSON on stdin. We read the edited file's
path and run the matching formatter. Nothing here can block Claude: every
failure is swallowed and the script always exits 0.

Deliberate choices:
- `uv run --no-sync`: a hook must never install or change packages.
- Ruff applies its safe fixes except F401 and F841 (unused import, unused
  variable). Claude often adds an import in one edit and uses it in the next;
  deleting it in between breaks the second edit. CI still reports both.
- Prettier is called from frontend/node_modules directly. `npx` could download
  a package, which a hook must never do.
- Paths resolve against the project root, not the shell's current directory.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

TIMEOUT_SECONDS = 20
PRETTIER_SUFFIXES = {".js", ".jsx", ".css", ".json", ".html"}
SKIP_DIRS = {".git", ".venv", "node_modules", "dist"}


def run(cmd: list[str], cwd: Path) -> None:
    """Run a formatter quietly. A missing tool, an error, or a timeout is fine."""
    try:
        # Fixed argument list from main(), no shell.
        subprocess.run(  # noqa: S603
            cmd, cwd=cwd, capture_output=True, timeout=TIMEOUT_SECONDS, check=False
        )
    except OSError, subprocess.SubprocessError:
        pass


def edited_file(payload: dict, root: Path) -> Path | None:
    """Return the edited file if it is a real file inside the project."""
    file_path = (payload.get("tool_input") or {}).get("file_path")
    if not file_path:
        return None
    path = Path(file_path)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if not path.is_file() or not path.is_relative_to(root):
        return None
    if SKIP_DIRS.intersection(path.relative_to(root).parts):
        return None
    return path


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return
    if not isinstance(payload, dict):
        return

    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd") or ".").resolve()
    path = edited_file(payload, root)
    if path is None:
        return
    parts = path.relative_to(root).parts

    if path.suffix == ".py" and shutil.which("uv"):
        run(["uv", "run", "--no-sync", "ruff", "format", str(path)], root)
        run(
            [
                "uv",
                "run",
                "--no-sync",
                "ruff",
                "check",
                "--fix",
                "--unfixable",
                "F401,F841",
                "--quiet",
                str(path),
            ],
            root,
        )
    elif path.suffix in PRETTIER_SUFFIXES and parts[0] == "frontend":
        prettier = root / "frontend" / "node_modules" / ".bin" / "prettier"
        if prettier.exists():
            run([str(prettier), "--write", str(path)], root / "frontend")


if __name__ == "__main__":
    try:
        main()
    finally:
        sys.exit(0)
