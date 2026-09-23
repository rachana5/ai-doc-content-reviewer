import unittest
from scripts.pr_filter import is_excluded_pr, main


class TestIsExcludedPr(unittest.TestCase):
    def test_renovate_bot_author_excluded(self):
        self.assertTrue(is_excluded_pr(
            author_login="app/renovate-with-github-actions",
            title="docs: something that slipped through with a docs-looking title",
        ))

    def test_chore_deps_title_excluded(self):
        self.assertTrue(is_excluded_pr(author_login="someone", title="chore(deps): update github actions"))

    def test_fix_deps_title_excluded(self):
        self.assertTrue(is_excluded_pr(author_login="someone", title="fix(deps): update dependency foo to v2"))

    def test_case_and_whitespace_insensitive_title_match(self):
        self.assertTrue(is_excluded_pr(author_login="someone", title="  CHORE(deps): bump lockfile  "))

    def test_normal_doc_pr_not_excluded(self):
        self.assertFalse(is_excluded_pr(
            author_login="rachana5",
            title="docs: add per-API authentication and keyless authentication",
        ))

    def test_chore_title_without_deps_scope_not_excluded(self):
        # e.g. "chore: add review-doc-pr skill" (#1015 itself) -- a real, human-authored
        # project change, not a dependency bump. Only the deps-scoped prefix is excluded.
        self.assertFalse(is_excluded_pr(author_login="rachana5", title="chore: add review-doc-pr skill"))


class TestMain(unittest.TestCase):
    def test_excluded_exits_1(self):
        self.assertEqual(
            main(["--author-login", "app/renovate-with-github-actions", "--title", "chore(deps): x"]),
            1,
        )

    def test_in_scope_exits_0(self):
        self.assertEqual(main(["--author-login", "rachana5", "--title", "docs: add X"]), 0)


if __name__ == "__main__":
    unittest.main()
