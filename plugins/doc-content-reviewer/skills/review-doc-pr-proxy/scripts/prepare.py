"""prepare.py: the deterministic first half of a review run, in one command.

Resolves the PR, decides whether to skip it, classifies its changed files against the
profile, and computes the changed-line ranges. Writes three files to `--out-dir`:

  context.json        profile name, skip decision, action, doc and code lists
  classify.json       scripts.missing_docs output (also read by find_affected_docs and post_review)
  changed-lines.json  per-file changed-line ranges (read by post_review)

A workflow can run this as a pre-step and hand `context.json` to an agent that has no
shell. A manual run lets the agent run it as Steps 0 to 2 in one go.

`--files` (a file with one changed path per line) plus `--author` and `--title` run it
offline, without calling `gh`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts import _gh, _git, changed_lines, missing_docs, pr_filter
from scripts import profile as profile_mod


def build_context(
    *, prof: dict, pr: str, repo: str | None, files: list[str], author: str, title: str,
    base: str, head: str,
) -> tuple[dict, dict]:
    """(context, classify). Pure: no I/O."""
    classify = missing_docs.classify(files, prof)
    skip = pr_filter.is_excluded_pr_for_profile(author_login=author, title=title, profile=prof)
    if skip:
        classify = {**classify, "action": "silent"}
    context = {
        "profile": prof["name"], "pr": pr, "repo": repo,
        "base": base, "head": head, "author": author, "title": title,
        "skip": skip, "skip_reason": "dependency bot or dependency-bump title" if skip else None,
        "action": classify["action"], "docs_changed": classify["docs_changed"],
        "user_facing_code": classify["user_facing_code"],
        "generated_touched": classify["generated_touched"],
    }
    return context, classify


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--profile", default="proxy", help="profile name or path (default: proxy)")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--repo", help="owner/repo; default is the repo gh resolves from the checkout")
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--files", help="offline: file with one changed path per line")
    ap.add_argument("--author", help="offline: PR author login")
    ap.add_argument("--title", help="offline: PR title")
    ap.add_argument("--base", help="offline: the PR's target branch")
    ap.add_argument("--head", help="offline: the PR's own branch")
    args = ap.parse_args(argv)

    prof = profile_mod.load(args.profile)
    repo_args = ["--repo", args.repo] if args.repo else []
    try:
        if args.files:
            files = [l.strip() for l in Path(args.files).read_text().splitlines() if l.strip()]
            author, title = args.author or "", args.title or ""
            base, head = args.base, args.head
        else:
            info = json.loads(_gh.run(
                ["pr", "view", args.pr, *repo_args, "--json", "author,title,baseRefName,headRefName"]))
            author, title = info["author"]["login"], info["title"]
            base, head = info["baseRefName"], info["headRefName"]
            files = [l for l in _gh.run(["pr", "diff", args.pr, *repo_args, "--name-only"]).splitlines() if l]
        ranges = {}
        if base and head:
            ranges = changed_lines.parse_changed_ranges(
                changed_lines.fetch_diff(Path(args.repo_root), base, head))
    except (_gh.GhError, _git.GitError) as e:
        print(f"[prepare] ERROR: {e}", file=sys.stderr)
        return 1

    context, classify = build_context(
        prof=prof, pr=args.pr, repo=args.repo, files=files, author=author, title=title,
        base=base or "", head=head or "")
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "context.json").write_text(json.dumps(context, indent=2))
    (out / "classify.json").write_text(json.dumps(classify, indent=2))
    (out / "changed-lines.json").write_text(json.dumps(ranges))
    print(f"[prepare] profile={context['profile']} action={context['action']} "
          f"docs_changed={len(context['docs_changed'])} user_facing_code={len(context['user_facing_code'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
