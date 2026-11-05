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


def test_merge_forwards_and_release_prep_are_excluded():
    for title in ("Merge branch v3.7 into master", "Merge remote-tracking branch 'upstream/v3.7' into master",
                  "Prepare release v3.7.17", "  MERGE BRANCH v2.11 into v3.7"):
        assert pr_filter.is_excluded_pr_for_profile(author_login="maintainer", title=title, profile=PROXY), title


def test_real_change_titles_that_mention_merge_or_release_are_in_scope():
    for title in ("Add a tap middleware", "Merge two sentences in the retry docs", "Document the release process",
                  "Bump sigs.k8s.io/gateway-api to v1.7.0"):
        assert not pr_filter.is_excluded_pr_for_profile(author_login="maintainer", title=title, profile=PROXY), title


def test_every_skip_prefix_in_the_profile_is_lowercase():
    # The title is lowercased before it is compared, so a capitalized prefix would never match.
    assert all(p == p.lower() for p in PROXY["skip_title_prefixes"])
