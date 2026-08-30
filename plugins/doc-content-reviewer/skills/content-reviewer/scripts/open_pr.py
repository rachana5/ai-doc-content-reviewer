"""open_pr.py — branch, commit, push, and open a PR. Only ever called after
the user has explicitly confirmed they want a PR (see SKILL.md's PR-gate
step) — nothing in this module runs on its own.
"""
from __future__ import annotations
import argparse
import json
from dataclasses import dataclass

from scripts import _git, _gh


@dataclass
class PrResult:
    url: str
    branch: str


def create_branch(repo_path: str, branch_name: str) -> None:
    _git.run(repo_path, ["checkout", "-b", branch_name])


def commit_changes(repo_path: str, message: str, files: list[str]) -> None:
    _git.run(repo_path, ["add", *files])
    _git.run(repo_path, ["commit", "-m", message])


def open_pr(repo_path: str, *, branch: str, title: str, body: str, base: str = "main") -> PrResult:
    _git.run(repo_path, ["push", "-u", "origin", branch])
    url = _gh.run([
        "pr", "create", "--title", title, "--body", body,
        "--base", base, "--head", branch,
    ]).strip()
    return PrResult(url=url, branch=branch)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--body", required=True)
    parser.add_argument("--base", default="main")
    parser.add_argument("--files", nargs="*", default=[])
    parser.add_argument("--commit-message", default=None)
    args = parser.parse_args(argv)

    create_branch(args.repo_root, args.branch)
    if args.files:
        commit_changes(args.repo_root, args.commit_message or args.title, args.files)
    result = open_pr(args.repo_root, branch=args.branch, title=args.title, body=args.body, base=args.base)
    print(json.dumps({"url": result.url, "branch": result.branch}))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
