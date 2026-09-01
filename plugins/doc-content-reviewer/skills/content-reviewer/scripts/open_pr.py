"""open_pr.py — branch, commit, push, and open a PR. Only ever called after
the user has explicitly confirmed they want a PR (see SKILL.md's PR-gate
step) — nothing in this module runs on its own.
"""
from __future__ import annotations
import argparse
import json
import re
from dataclasses import dataclass

from scripts import _git, _gh

_REMOTE_URL_RE = re.compile(r"github\.com[:/](?P<slug>[^/]+/[^/]+?)(?:\.git)?/?$")


@dataclass
class PrResult:
    url: str
    branch: str


def create_branch(repo_path: str, branch_name: str) -> None:
    _git.run(repo_path, ["checkout", "-b", branch_name])


def commit_changes(repo_path: str, message: str, files: list[str]) -> None:
    _git.run(repo_path, ["add", *files])
    _git.run(repo_path, ["commit", "-m", message])


def _repo_slug_for_remote(repo_path: str, remote: str) -> str:
    url = _git.run(repo_path, ["remote", "get-url", remote])
    match = _REMOTE_URL_RE.search(url)
    if not match:
        raise _git.GitError(f"couldn't parse owner/repo from remote {remote!r} URL: {url!r}")
    return match.group("slug")


def open_pr(
    repo_path: str, *, branch: str, title: str, body: str, base: str = "main",
    remote: str = "origin",
) -> PrResult:
    # A repo checked out from a fork commonly carries two remotes — origin
    # (the real upstream, e.g. traefik/hub-doc) and a fork remote (the
    # user's own copy). Pushing to a hardcoded "origin" would land this
    # branch on the real upstream repo regardless of which one the caller
    # actually intended — confirmed as a live risk, not hypothetical: this
    # was caught before running against hub-doc-demo-review, where origin
    # is genuinely traefik/hub-doc and the user has real push access to it.
    # --repo is derived from the SAME remote just pushed to, so gh opens
    # the PR in the repo the branch actually landed in, not wherever
    # origin happens to point.
    _git.run(repo_path, ["push", "-u", remote, branch])
    repo_slug = _repo_slug_for_remote(repo_path, remote)
    url = _gh.run([
        "pr", "create", "--repo", repo_slug, "--title", title, "--body", body,
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
    parser.add_argument(
        "--remote", default="origin",
        help="Git remote to push to and open the PR against — must be set "
             "explicitly to the fork's remote name (e.g. 'fork') whenever "
             "the repo has both an origin (upstream) and a fork remote, "
             "or this defaults to pushing straight to origin.",
    )
    args = parser.parse_args(argv)

    create_branch(args.repo_root, args.branch)
    if args.files:
        commit_changes(args.repo_root, args.commit_message or args.title, args.files)
    result = open_pr(
        args.repo_root, branch=args.branch, title=args.title, body=args.body,
        base=args.base, remote=args.remote,
    )
    print(json.dumps({"url": result.url, "branch": result.branch}))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
