from __future__ import annotations

from scripts import pr_filter, profile

PROXY = profile.load("proxy")


def test_dependency_bot_authors_and_title_prefixes_are_excluded():
    assert pr_filter.is_excluded_pr_for_profile(author_login="app/dependabot", title="x", profile=PROXY)
    assert pr_filter.is_excluded_pr_for_profile(author_login="a", title="chore(deps): bump", profile=PROXY)
    assert pr_filter.is_excluded_pr_for_profile(author_login="a", title="Fix(deps): bump", profile=PROXY)


def test_other_chore_and_docs_prs_are_in_scope():
    assert not pr_filter.is_excluded_pr_for_profile(author_login="a", title="chore: tidy docs", profile=PROXY)
    assert not pr_filter.is_excluded_pr_for_profile(author_login="a", title="docs: fix", profile=PROXY)


def test_main_exit_codes():
    assert pr_filter.main(["--author-login", "renovate[bot]", "--title", "x"]) == 1
    assert pr_filter.main(["--author-login", "alice", "--title", "docs: fix"]) == 0
