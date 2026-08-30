"""_discover.py — locate the local traefik-hub clone (source of truth for
the Hub-docs accuracy layer) and the current repo's root (used for the
self-contained traefik/traefik / Proxy case, where docs and source live in
the same repo). Mirrors hub-doc-pr-generator's _discover.py search order.

Discovery is best-effort. If traefik-hub can't be auto-found, SKILL.md's
Step 1 prompts via AskUserQuestion and calls persist_traefik_hub() with the
answer so future runs skip discovery.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Optional

from scripts import _git

TRAEFIK_HUB_URL_RE = re.compile(
    r"github\.com[:/](?P<owner>[^/]+)/traefik-hub(?:\.git)?/?$"
)

CONFIG_PATH = Path.home() / ".config" / "doc-content-reviewer" / "config.json"

COMMON_PARENTS = [
    Path.home() / "code",
    Path.home() / "dev",
    Path.home() / "src",
    Path.home() / "Developer",
    Path.home() / "workspace",
    Path.home() / "projects",
    Path.home() / "git",
]


def _is_traefik_hub_clone(path: Path) -> bool:
    """True iff path is a git repo whose origin matches traefik/traefik-hub or a fork of it."""
    if not (path / ".git").exists():
        return False
    try:
        url = _git.run(str(path), ["config", "--get", "remote.origin.url"]).strip()
    except _git.GitError:
        return False
    return bool(TRAEFIK_HUB_URL_RE.search(url))


def _load_config() -> dict:
    if not CONFIG_PATH.is_file():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text())
    except json.JSONDecodeError:
        return {}


def _save_config(cfg: dict) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


def _siblings_of(cwd: Path, depth: int = 5) -> list[Path]:
    """Walk up cwd looking for a sibling 'traefik-hub' directory at each level."""
    found: list[Path] = []
    seen: set[Path] = set()
    p = cwd.resolve()
    for _ in range(depth):
        for candidate in (p / "traefik-hub", p.parent / "traefik-hub"):
            if candidate.is_dir() and candidate not in seen:
                seen.add(candidate)
                found.append(candidate)
        if p.parent == p:
            break
        p = p.parent
    return found


def _scan_common_parents() -> list[Path]:
    found: list[Path] = []
    for parent in COMMON_PARENTS:
        if not parent.is_dir():
            continue
        try:
            for child in parent.iterdir():
                if not child.is_dir():
                    continue
                if child.name == "traefik-hub":
                    found.append(child)
                else:
                    nested = child / "traefik-hub"
                    if nested.is_dir():
                        found.append(nested)
        except OSError:
            continue
    return found


def discover_traefik_hub(*, cwd: Optional[str] = None, env: Optional[dict] = None) -> Optional[str]:
    """Return an absolute path to a local traefik-hub clone, or None if not found.

    Search order:
      1. $TRAEFIK_HUB_PATH env var (escape hatch)
      2. Persisted config at ~/.config/doc-content-reviewer/config.json
      3. Sibling dirs of cwd (walks up to depth 5)
      4. Common workspace parents (~/code, ~/dev, ~/src, ~/Developer, etc.)
    """
    env_map = env if env is not None else os.environ
    cwd_p = Path(cwd) if cwd else Path.cwd()

    explicit = env_map.get("TRAEFIK_HUB_PATH")
    if explicit and _is_traefik_hub_clone(Path(explicit)):
        return str(Path(explicit).resolve())

    saved = _load_config().get("traefik_hub_path")
    if saved and _is_traefik_hub_clone(Path(saved)):
        return str(Path(saved).resolve())

    for cand in _siblings_of(cwd_p):
        if _is_traefik_hub_clone(cand):
            return str(cand.resolve())

    for cand in _scan_common_parents():
        if _is_traefik_hub_clone(cand):
            return str(cand.resolve())

    return None


def persist_traefik_hub(path: str) -> None:
    """Save a confirmed traefik-hub path so future runs skip discovery."""
    cfg = _load_config()
    cfg["traefik_hub_path"] = str(Path(path).resolve())
    _save_config(cfg)


def discover_repo_root(*, cwd: Optional[str] = None) -> Optional[str]:
    """Return the git toplevel of cwd, or None if cwd isn't inside a git repo.

    Used for the Proxy (traefik/traefik) case, where the docs and the source
    the accuracy layer needs to read live in the same repo — no separate
    discovery needed, just "what repo am I already in."
    """
    cwd_p = Path(cwd) if cwd else Path.cwd()
    try:
        return _git.run(str(cwd_p), ["rev-parse", "--show-toplevel"]).strip()
    except _git.GitError:
        return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Locate local clones used by content-reviewer.")
    sub = parser.add_subparsers(dest="target", required=True)
    sub.add_parser("traefik-hub", help="Print path to local traefik-hub clone, or exit 2 if not found.")
    sub.add_parser("repo-root", help="Print the current repo's root, or exit 2 if cwd isn't a git repo.")
    save = sub.add_parser("save-traefik-hub", help="Persist a traefik-hub path for future runs.")
    save.add_argument("path")
    args = parser.parse_args(argv)

    if args.target == "traefik-hub":
        path = discover_traefik_hub()
        if path is None:
            print("traefik-hub clone not found", file=sys.stderr)
            return 2
        print(path)
        return 0
    if args.target == "repo-root":
        path = discover_repo_root()
        if path is None:
            print("not a git repo (cwd)", file=sys.stderr)
            return 2
        print(path)
        return 0
    if args.target == "save-traefik-hub":
        persist_traefik_hub(args.path)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
