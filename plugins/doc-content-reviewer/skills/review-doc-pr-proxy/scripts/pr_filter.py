"""pr_filter.py: decide whether a PR is out of scope for review-doc-pr-proxy.

Dependency-bump PRs (authors and title prefixes listed in the profile) are not
documentation changes and have their own reviewer, so the run stops before any layer.

Exit 1: excluded, stop the run. Exit 0: in scope, proceed.
"""
from __future__ import annotations

import argparse
import sys

from scripts import profile as profile_mod


def is_excluded_pr_for_profile(*, author_login: str, title: str, profile: dict) -> bool:
    if author_login in profile.get("skip_authors", []):
        return True
    return title.strip().lower().startswith(tuple(profile.get("skip_title_prefixes", ())))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--profile", default="proxy", help="profile name or path (default: proxy)")
    parser.add_argument("--author-login", required=True)
    parser.add_argument("--title", required=True)
    args = parser.parse_args(argv)
    excluded = is_excluded_pr_for_profile(
        author_login=args.author_login, title=args.title, profile=profile_mod.load(args.profile))
    if excluded:
        print(f"[pr_filter] EXCLUDED: {args.author_login!r} / {args.title!r}: stop, run no layer, post nothing.")
        return 1
    print("[pr_filter] in scope")
    return 0


if __name__ == "__main__":
    sys.exit(main())
