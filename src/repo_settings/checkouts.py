"""Which checkout of a repository a directory is in, and which is the repository's main one.

git answers both, so there's nothing to guess: None means there's no such checkout, because the
directory isn't in a repository or the repository is bare.
"""

import subprocess
from pathlib import Path


def this_worktree(directory: Path) -> Path | None:
    """The root of the worktree directory is in, or None outside one."""
    top = _git(directory, "rev-parse", "--show-toplevel")
    return Path(top).resolve() if top else None


def main_worktree(directory: Path) -> Path | None:
    """The root of the main worktree of the repository directory is in: the one the repository
    was created or cloned in. None outside a repository, or when it's bare."""
    porcelain = _git(directory, "worktree", "list", "--porcelain")
    if porcelain is None:
        return None
    first = porcelain.split("\n\n", 1)[0].splitlines()  # git always lists the main one first
    if "bare" in first:
        return None
    return Path(first[0].removeprefix("worktree ")).resolve()


def every_worktree(directory: Path) -> tuple[Path, ...] | None:
    """The root of each worktree of the repository directory is in, the main one first, leaving
    out a bare repository's own directory and any worktree whose directory is gone. None outside
    a repository."""
    porcelain = _git(directory, "worktree", "list", "--porcelain")
    if porcelain is None:
        return None
    roots = []
    for entry in porcelain.split("\n\n"):
        lines = entry.splitlines()
        root = Path(lines[0].removeprefix("worktree "))
        if "bare" not in lines and root.is_dir():
            roots.append(root.resolve())
    return tuple(roots)


def _git(directory: Path, *args: str) -> str | None:
    """git's output in directory, stripped, or None when it fails."""
    result = subprocess.run(
        ["git", "-C", str(directory), *args],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
