"""_git.py — thin subprocess wrapper around `git -C <repo_path> ...`."""
from __future__ import annotations
import subprocess


class GitError(RuntimeError):
    pass


def run(repo_path: str, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", repo_path, *args], capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or f"git {args} failed")
    return result.stdout.strip()
