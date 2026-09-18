"""changed_lines.py — parses a unified diff into per-file changed-line
ranges, using the NEW file's line numbers throughout.

This is the scope boundary between "whole file" and "diff-only" layers
(see the review-doc-pr plan's per-layer scope table): style and clarity
need to know which lines are actually new/changed so they don't flag
prose the PR never touched, while accuracy and reference deliberately
skip this and read the whole file instead.

New-file line numbers are used because that's what everything downstream
already numbers against — Vale/alex output, and the aggregated report's
`line` field — so no old/new translation is needed by callers.
"""
from __future__ import annotations

import argparse
import json
import sys
import re
from pathlib import Path

from scripts import _git

# Matches a diff's "+++ b/<path>" file header. A deleted file's header is
# "+++ /dev/null" instead (no b/ prefix) — captured as `devnull` so the
# caller can tell "no current file" apart from "haven't seen a header
# yet", and any hunks that follow are then skipped: nothing in a deleted
# file's old content belongs on a "what's new" range list.
_FILE_HEADER_RE = re.compile(r"^\+\+\+ (?:b/(?P<path>.+)|(?P<devnull>/dev/null))$")

# Matches a hunk header's new-file side, e.g. "@@ -12,3 +14,5 @@ context".
# The count is omitted by unified-diff convention when it's exactly 1
# (e.g. "+14 @@"), so a missing group means count=1, not count=0.
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@")


def parse_changed_ranges(diff_text: str) -> dict[str, list[tuple[int, int]]]:
    """Returns {file_path: [(start_line, end_line), ...]} — inclusive,
    1-based, new-file line ranges added or modified by this diff.

    A hunk with count=0 on the new-file side (a pure deletion — nothing
    was added at that location) contributes no range: there's no line in
    the new file to attach a review scope to. A file touched only by such
    hunks is omitted from the result entirely, same as a file with no
    hunks at all.
    """
    ranges: dict[str, list[tuple[int, int]]] = {}
    current_file: str | None = None
    for line in diff_text.splitlines():
        header = _FILE_HEADER_RE.match(line)
        if header:
            current_file = header.group("path")
            continue
        hunk = _HUNK_RE.match(line)
        if hunk and current_file is not None:
            start = int(hunk.group("start"))
            count = int(hunk.group("count")) if hunk.group("count") is not None else 1
            if count == 0:
                continue
            ranges.setdefault(current_file, []).append((start, start + count - 1))
    return ranges


def line_in_ranges(line: int, ranges: list[tuple[int, int]]) -> bool:
    """True if `line` falls inside any (start, end) range — the check the
    style-lint output filter and the clarity layer's prompt scoping both
    need to make, once per candidate line."""
    return any(start <= line <= end for start, end in ranges)


def fetch_diff(repo_root: Path, base: str, head: str, files: list[str] | None = None) -> str:
    """Runs `git diff --unified=0` between two refs already present in
    `repo_root`'s history (the CI checkout is expected to have fetched
    both — the PR's head, already checked out, and its base branch).
    --unified=0 is what makes hunk ranges exactly the changed lines, with
    no surrounding context lines to exclude afterward.

    Raises `_git.GitError` on failure — reuses content-reviewer's own
    git wrapper rather than a second, slightly different subprocess
    implementation living here."""
    args = ["diff", "--unified=0", f"{base}...{head}"]
    if files:
        args += ["--", *files]
    return _git.run(str(repo_root), args)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--base", required=True, help="the PR's target branch")
    parser.add_argument("--head", required=True, help="the PR's own branch")
    parser.add_argument("files", nargs="*", help="restrict the diff to these files (optional)")
    args = parser.parse_args(argv)

    diff_text = fetch_diff(Path(args.repo_root), args.base, args.head, args.files or None)
    print(json.dumps(parse_changed_ranges(diff_text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
