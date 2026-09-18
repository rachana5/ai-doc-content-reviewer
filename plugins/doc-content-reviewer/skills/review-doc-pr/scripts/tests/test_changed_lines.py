from __future__ import annotations
from pathlib import Path
from unittest import mock

from scripts import changed_lines


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


def test_line_in_ranges_checks_inclusive_bounds():
    ranges = [(5, 6), (21, 21)]
    assert changed_lines.line_in_ranges(5, ranges) is True
    assert changed_lines.line_in_ranges(6, ranges) is True
    assert changed_lines.line_in_ranges(21, ranges) is True
    assert changed_lines.line_in_ranges(7, ranges) is False
    assert changed_lines.line_in_ranges(20, ranges) is False


def test_fetch_diff_invokes_git_diff_with_unified_zero(monkeypatch):
    captured = {}

    def fake_run(args, capture_output, text):
        captured["args"] = args
        return mock.Mock(returncode=0, stdout="diff output", stderr="")

    monkeypatch.setattr(changed_lines.subprocess, "run", fake_run)
    result = changed_lines.fetch_diff(Path("/repo"), "main", "feature-branch")

    assert result == "diff output"
    assert captured["args"] == [
        "git", "-C", "/repo", "diff", "--unified=0", "main...feature-branch",
    ]


def test_fetch_diff_scopes_to_given_files(monkeypatch):
    captured = {}

    def fake_run(args, capture_output, text):
        captured["args"] = args
        return mock.Mock(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(changed_lines.subprocess, "run", fake_run)
    changed_lines.fetch_diff(Path("/repo"), "main", "feature-branch", ["docs/a.md", "docs/b.md"])

    assert captured["args"][-3:] == ["--", "docs/a.md", "docs/b.md"]


def test_fetch_diff_raises_on_git_failure(monkeypatch):
    def fake_run(args, capture_output, text):
        return mock.Mock(returncode=128, stdout="", stderr="fatal: bad revision 'main'")

    monkeypatch.setattr(changed_lines.subprocess, "run", fake_run)
    try:
        changed_lines.fetch_diff(Path("/repo"), "main", "feature-branch")
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "bad revision" in str(e)
