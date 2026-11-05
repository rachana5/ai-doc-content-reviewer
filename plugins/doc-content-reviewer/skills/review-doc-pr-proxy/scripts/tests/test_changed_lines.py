from __future__ import annotations
from pathlib import Path

from scripts import changed_lines, _git


def test_modified_file_single_hunk_uses_new_side_count():
    diff_text = (
        "diff --git a/docs/foo.md b/docs/foo.md\n"
        "index abc123..def456 100644\n"
        "--- a/docs/foo.md\n"
        "+++ b/docs/foo.md\n"
        "@@ -10 +10,2 @@ some context\n"
        "-old line\n"
        "+new line one\n"
        "+new line two\n"
    )
    assert changed_lines.parse_changed_ranges(diff_text) == {"docs/foo.md": [(10, 11)]}


def test_new_file_range_covers_the_whole_file():
    # A brand-new file (the common case out of hub-doc-pr-generator) has no
    # "--- a/..." side at all -- its whole content arrives as one hunk
    # starting at line 1, which is exactly the "diff-scoped == whole file"
    # behavior the review-doc-pr plan calls out as a free consequence, not
    # a special case this function needs to detect.
    diff_text = (
        "diff --git a/docs/bar.md b/docs/bar.md\n"
        "new file mode 100644\n"
        "index 0000000..abcdef1\n"
        "--- /dev/null\n"
        "+++ b/docs/bar.md\n"
        "@@ -0,0 +1,3 @@\n"
        "+line one\n"
        "+line two\n"
        "+line three\n"
    )
    assert changed_lines.parse_changed_ranges(diff_text) == {"docs/bar.md": [(1, 3)]}


def test_deletion_only_hunk_contributes_no_range():
    diff_text = (
        "diff --git a/docs/baz.md b/docs/baz.md\n"
        "index 111..222 100644\n"
        "--- a/docs/baz.md\n"
        "+++ b/docs/baz.md\n"
        "@@ -5,2 +4,0 @@\n"
        "-removed line 1\n"
        "-removed line 2\n"
    )
    assert changed_lines.parse_changed_ranges(diff_text) == {}


def test_single_line_hunk_omits_the_comma_count():
    diff_text = (
        "diff --git a/docs/qux.md b/docs/qux.md\n"
        "index 111..222 100644\n"
        "--- a/docs/qux.md\n"
        "+++ b/docs/qux.md\n"
        "@@ -7 +7 @@ heading\n"
        "-old\n"
        "+new\n"
    )
    assert changed_lines.parse_changed_ranges(diff_text) == {"docs/qux.md": [(7, 7)]}


def test_deleted_file_is_excluded_even_if_a_hunk_line_follows():
    diff_text = (
        "diff --git a/docs/gone.md b/docs/gone.md\n"
        "deleted file mode 100644\n"
        "index 111..0000000\n"
        "--- a/docs/gone.md\n"
        "+++ /dev/null\n"
        "@@ -1,2 +0,0 @@\n"
        "-line one\n"
        "-line two\n"
    )
    assert changed_lines.parse_changed_ranges(diff_text) == {}


def test_multiple_hunks_in_one_file_each_produce_their_own_range():
    diff_text = (
        "diff --git a/docs/multi.md b/docs/multi.md\n"
        "index 111..222 100644\n"
        "--- a/docs/multi.md\n"
        "+++ b/docs/multi.md\n"
        "@@ -5 +5,2 @@\n"
        "-old\n"
        "+new a\n"
        "+new b\n"
        "@@ -20 +21 @@\n"
        "-old\n"
        "+new\n"
    )
    assert changed_lines.parse_changed_ranges(diff_text) == {
        "docs/multi.md": [(5, 6), (21, 21)],
    }


def test_multiple_files_in_one_diff_are_kept_separate():
    diff_text = (
        "diff --git a/docs/a.md b/docs/a.md\n"
        "index 111..222 100644\n"
        "--- a/docs/a.md\n"
        "+++ b/docs/a.md\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
        "diff --git a/docs/b.md b/docs/b.md\n"
        "index 333..444 100644\n"
        "--- a/docs/b.md\n"
        "+++ b/docs/b.md\n"
        "@@ -9 +9,3 @@\n"
        "-old\n"
        "+new1\n"
        "+new2\n"
        "+new3\n"
    )
    assert changed_lines.parse_changed_ranges(diff_text) == {
        "docs/a.md": [(1, 1)],
        "docs/b.md": [(9, 11)],
    }


def test_empty_diff_returns_empty_dict():
    assert changed_lines.parse_changed_ranges("") == {}


def test_content_resembling_a_file_header_does_not_hijack_current_file():
    # A doc's own added content can legitimately look like a diff header:
    # the source line "++ b/fake.md" (e.g. a patch-syntax example) becomes
    # "+++ b/fake.md" once git prefixes it with its own "+" change-marker
    # for being an added line -- indistinguishable from a real header by
    # that line alone. The second hunk below must still attribute to
    # docs/real.md, not to the phantom "fake.md" the content line implies.
    diff_text = (
        "diff --git a/docs/real.md b/docs/real.md\n"
        "index 111..222 100644\n"
        "--- a/docs/real.md\n"
        "+++ b/docs/real.md\n"
        "@@ -1 +2,3 @@\n"
        "+line a\n"
        "+++ b/fake.md\n"
        "+line c\n"
        "@@ -10 +14,2 @@\n"
        "+another line\n"
        "+yet another\n"
    )
    assert changed_lines.parse_changed_ranges(diff_text) == {
        "docs/real.md": [(2, 4), (14, 15)],
    }


def test_content_resembling_a_full_header_pair_does_not_hijack_current_file():
    # Escalation of the case above: content that renders as a full
    # "--- a/old.md" / "+++ b/new.md" pair (source lines "-- a/old.md",
    # removed, immediately followed by "++ b/new.md", added -- each
    # gaining its own leading change-marker once diffed) must still not
    # be mistaken for a real file-section boundary. Anchoring on the
    # literal "diff --git" line is what makes this immune regardless of
    # how header-like the hunk body's own content looks: that line is the
    # only one a hunk's content can never produce, since every hunk-body
    # line always carries its own leading "+"/"-" marker.
    diff_text = (
        "diff --git a/docs/real.md b/docs/real.md\n"
        "index 111..222 100644\n"
        "--- a/docs/real.md\n"
        "+++ b/docs/real.md\n"
        "@@ -1 +1,2 @@\n"
        "--- a/old.md\n"
        "+++ b/new.md\n"
        "+second added\n"
        "@@ -10 +14,2 @@\n"
        "+another line\n"
        "+yet another\n"
    )
    assert changed_lines.parse_changed_ranges(diff_text) == {
        "docs/real.md": [(1, 2), (14, 15)],
    }


def test_context_lines_are_not_changed_lines():
    # `gh pr diff` and a plain `git diff` carry 3 lines of context around an edit.
    diff_text = (
        "diff --git a/docs/foo.md b/docs/foo.md\n"
        "--- a/docs/foo.md\n"
        "+++ b/docs/foo.md\n"
        "@@ -10,7 +10,7 @@ heading\n"
        " context one\n"
        " context two\n"
        " context three\n"
        "-old line\n"
        "+new line\n"
        " context four\n"
        " context five\n"
        " context six\n"
    )
    assert changed_lines.parse_changed_ranges(diff_text) == {"docs/foo.md": [(13, 13)]}


def test_a_diff_with_context_gives_the_same_ranges_as_one_without():
    header = "diff --git a/docs/foo.md b/docs/foo.md\n--- a/docs/foo.md\n+++ b/docs/foo.md\n"
    without_context = header + "@@ -13 +13 @@\n-old line\n+new line\n@@ -30,0 +31,2 @@\n+added one\n+added two\n"
    with_context = (
        header
        + "@@ -10,7 +10,7 @@\n c1\n c2\n c3\n-old line\n+new line\n c4\n c5\n c6\n"
        + "@@ -27,3 +28,5 @@\n c7\n c8\n c9\n+added one\n+added two\n"
    )
    assert (
        changed_lines.parse_changed_ranges(with_context)
        == changed_lines.parse_changed_ranges(without_context)
        == {"docs/foo.md": [(13, 13), (31, 32)]}
    )


def test_a_deletion_with_context_contributes_no_range():
    diff_text = (
        "diff --git a/docs/foo.md b/docs/foo.md\n"
        "--- a/docs/foo.md\n"
        "+++ b/docs/foo.md\n"
        "@@ -5,7 +5,6 @@\n"
        " c1\n c2\n c3\n"
        "-removed\n"
        " c4\n c5\n c6\n"
    )
    assert changed_lines.parse_changed_ranges(diff_text) == {}


def test_a_no_newline_marker_does_not_shift_the_numbering():
    diff_text = (
        "diff --git a/docs/foo.md b/docs/foo.md\n"
        "--- a/docs/foo.md\n"
        "+++ b/docs/foo.md\n"
        "@@ -1,2 +1,2 @@\n"
        " first\n"
        "-old last\n"
        "\\ No newline at end of file\n"
        "+new last\n"
        "\\ No newline at end of file\n"
    )
    assert changed_lines.parse_changed_ranges(diff_text) == {"docs/foo.md": [(2, 2)]}


def test_a_replaced_block_is_one_range_even_with_removed_lines_between_added_ones():
    diff_text = (
        "diff --git a/docs/foo.md b/docs/foo.md\n"
        "--- a/docs/foo.md\n"
        "+++ b/docs/foo.md\n"
        "@@ -3,2 +3,2 @@\n"
        "-old a\n+new a\n-old b\n+new b\n"
    )
    assert changed_lines.parse_changed_ranges(diff_text) == {"docs/foo.md": [(3, 4)]}


def test_file_name_with_a_space_keeps_its_path_without_the_trailing_tab():
    # git ends the "+++ b/<path>" line with a tab when the path contains a space.
    diff_text = (
        "diff --git a/docs/my page.md b/docs/my page.md\n"
        "--- a/docs/my page.md\t\n"
        "+++ b/docs/my page.md\t\n"
        "@@ -1 +1,2 @@\n"
        "+added\n"
        "+added too\n"
    )
    assert changed_lines.parse_changed_ranges(diff_text) == {"docs/my page.md": [(1, 2)]}


def test_line_in_ranges_checks_inclusive_bounds():
    ranges = [(5, 6), (21, 21)]
    assert changed_lines.line_in_ranges(5, ranges) is True
    assert changed_lines.line_in_ranges(6, ranges) is True
    assert changed_lines.line_in_ranges(21, ranges) is True
    assert changed_lines.line_in_ranges(7, ranges) is False
    assert changed_lines.line_in_ranges(20, ranges) is False


def test_fetch_diff_delegates_to_the_git_wrapper(monkeypatch):
    captured = {}

    def fake_run(repo_path, args):
        captured["repo_path"] = repo_path
        captured["args"] = args
        return "diff output"

    monkeypatch.setattr(changed_lines._git, "run", fake_run)
    result = changed_lines.fetch_diff(Path("/repo"), "main", "feature-branch")

    assert result == "diff output"
    assert captured["repo_path"] == "/repo"
    assert captured["args"] == [
        "-c", "core.quotePath=false",
        "diff", "--unified=0", "--src-prefix=a/", "--dst-prefix=b/", "main...feature-branch",
    ]


def test_fetch_diff_scopes_to_given_files(monkeypatch):
    captured = {}

    def fake_run(repo_path, args):
        captured["args"] = args
        return ""

    monkeypatch.setattr(changed_lines._git, "run", fake_run)
    changed_lines.fetch_diff(Path("/repo"), "main", "feature-branch", ["docs/a.md", "docs/b.md"])

    assert captured["args"][-3:] == ["--", "docs/a.md", "docs/b.md"]


def test_fetch_diff_propagates_git_errors(monkeypatch):
    def fake_run(repo_path, args):
        raise _git.GitError("fatal: bad revision 'main'")

    monkeypatch.setattr(changed_lines._git, "run", fake_run)
    try:
        changed_lines.fetch_diff(Path("/repo"), "main", "feature-branch")
        assert False, "expected _git.GitError"
    except _git.GitError as e:
        assert "bad revision" in str(e)


def test_main_reports_a_clean_error_on_git_failure_instead_of_a_traceback(monkeypatch, capsys):
    def fake_run(repo_path, args):
        raise _git.GitError("fatal: bad revision 'main'")

    monkeypatch.setattr(changed_lines._git, "run", fake_run)
    exit_code = changed_lines.main(["--repo-root", "/repo", "--base", "main", "--head", "feature"])

    assert exit_code == 1
    assert "bad revision" in capsys.readouterr().err
