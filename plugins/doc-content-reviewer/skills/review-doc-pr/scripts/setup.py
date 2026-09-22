"""setup.py — preflight checks for content-reviewer.

Usage:
    python -m scripts.setup --check
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

MIN_PYTHON = (3, 11)


def check_python_version(version_info: tuple[int, int, int] | None = None) -> tuple[bool, str]:
    version_info = version_info or sys.version_info[:3]
    if version_info[:2] >= MIN_PYTHON:
        return True, f"Python {version_info[0]}.{version_info[1]} OK (need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+)"
    return False, f"Python {version_info[0]}.{version_info[1]} found, need {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+"


def check_gh_auth() -> tuple[bool, str]:
    result = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
    if result.returncode == 0:
        return True, "gh authenticated"
    return False, "gh not authenticated — run `gh auth login`"


_ALEX_CONFIG_NAMES = (".alexrc.yaml", ".alexrc.yml", ".alexrc.json", ".alexrc")


def check_lint_tools(repo_root: Path) -> dict:
    """Detect vale/alex as usable FOR THIS REPO — binary on PATH AND a config
    file at repo_root, both required.

    A binary alone isn't enough: `hub-doc` ships `.vale.ini` + `.alexrc.yaml`,
    but `traefik/traefik` (the other repo this plugin targets) currently has
    neither. Without this check, Vale would silently walk up from cwd and
    pick up whatever `.vale.ini` it finds first (potentially the wrong repo's
    rules), and alex would run with no config and report false-clean. Missing
    tools/config are not fatal either way — the style layer degrades to
    agent-only judgment (see spec's error-handling section) — but the
    degrade must be based on real per-repo usability, not just PATH."""
    vale_ok = shutil.which("vale") is not None and (repo_root / ".vale.ini").exists()
    alex_ok = shutil.which("alex") is not None and any(
        (repo_root / name).exists() for name in _ALEX_CONFIG_NAMES
    )
    return {"vale": vale_ok, "alex": alex_ok}


def check_git_status(repo_root: Path) -> tuple[bool, str]:
    """Advisory only — never blocks. `apply_fixes.py` writes straight into
    the working tree once the user confirms, so a dirty tree going in means
    this run's fixes are hard to tell apart from the user's own unstaged
    changes once they're both sitting in the same diff. Flag it, don't stop
    the run over it — the user may have a perfectly good reason to be
    mid-edit already."""
    result = subprocess.run(
        ["git", "-C", str(repo_root), "status", "--porcelain"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        # Not a git repo, or git itself failed — a different, earlier step
        # (repo detection) is responsible for catching that; this check has
        # nothing useful to say here, so it must not manufacture a warning.
        return True, "not a git repository — skipping working-tree check"
    if result.stdout.strip():
        return False, "working tree has uncommitted changes — this run's fixes may be hard to tell apart from your own edits"
    return True, "working tree is clean"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if not args.check:
        parser.print_help()
        return 1

    py_ok, py_msg = check_python_version()
    print(f"[setup] {'OK' if py_ok else 'ERROR'}: {py_msg}")
    if not py_ok:
        return 1

    gh_ok, gh_msg = check_gh_auth()
    print(f"[setup] {'OK' if gh_ok else 'ERROR'}: {gh_msg}")
    if not gh_ok:
        return 1

    lint = check_lint_tools(Path.cwd())
    for tool, present in lint.items():
        status = "OK" if present else "WARNING"
        note = "" if present else " (style layer will degrade to agent-only judgment)"
        print(f"[setup] {status}: {tool}{note}")

    git_ok, git_msg = check_git_status(Path.cwd())
    print(f"[setup] {'OK' if git_ok else 'WARNING'}: {git_msg}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
