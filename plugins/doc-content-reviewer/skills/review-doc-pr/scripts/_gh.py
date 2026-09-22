"""_gh.py — thin subprocess wrapper around the `gh` CLI."""
from __future__ import annotations
import subprocess


class GhError(RuntimeError):
    pass


def run(args: list[str]) -> str:
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise GhError(result.stderr.strip() or f"gh {args} failed")
    return result.stdout.strip()
