"""pr_filter.py — decide whether a PR is out of scope for review-doc-pr.

review-doc-pr reviews documentation content. Renovate/dependency-bump PRs
are infrastructure changes with their own reviewer (this repo's
`renovate-pr-review` skill) — running the content-review layers
against them produces zero-value "no issues found" noise on a PR that has
no doc content to review in the first place. Excluded before Step 1 does
any work, not filtered out after the fact.
"""
from __future__ import annotations

# Same bot login `renovate-pr-review`'s own SKILL.md keys off of.
RENOVATE_BOT_LOGIN = "app/renovate-with-github-actions"

_CHORE_DEP_PREFIXES = ("chore(deps)", "fix(deps)")


def is_excluded_pr(*, author_login: str, title: str) -> bool:
    """True if this PR is out of scope and review-doc-pr should exit
    without running any layer or posting any comment."""
    if author_login == RENOVATE_BOT_LOGIN:
        return True
    normalized = title.strip().lower()
    return normalized.startswith(_CHORE_DEP_PREFIXES)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="Exit 1 (excluded, stop the run) or 0 (in scope, proceed) for a PR's author/title."
    )
    parser.add_argument("--author-login", required=True)
    parser.add_argument("--title", required=True)
    args = parser.parse_args(argv)

    excluded = is_excluded_pr(author_login=args.author_login, title=args.title)
    print(json.dumps({"excluded": excluded}))
    return 1 if excluded else 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
