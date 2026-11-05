"""changed_lines.py — parses a unified diff into per-file changed-line
ranges, using the NEW file's line numbers throughout.

This is the scope boundary for the layers that only look at the PR's own
lines: style and clarity need to know which lines are actually new/changed
so they don't flag prose the PR never touched.

New-file line numbers are used because that's what everything downstream
already numbers against, such as the aggregated report's
`line` field — so no old/new translation is needed by callers.
"""
from __future__ import annotations

import argparse
import json
import sys
import re
from pathlib import Path

from scripts import _git

# Matches only the literal start of a "diff --git a/<old> b/<new>" file
# boundary — the ONE line in a unified diff that a hunk's own content can
# never fake, no matter what that content says. Every line inside a hunk
# body (added or removed) always carries its own leading "+"/"-" change
# marker character, prepended by git itself; a doc's line whose own text
# happens to start with "diff --git " would render as "+diff --git ..."
# (added) or "-diff --git ..." (removed), neither of which matches this
# pattern anchored at column 0. That's what makes anchoring here, instead
# of pattern-matching "+++ b/<path>"-shaped lines wherever they appear,
# structurally immune to content that resembles diff/patch syntax —
# plausible content specifically for this tool, since its job is
# analyzing diffs of documentation that may itself show such examples.
_DIFF_GIT_RE = re.compile(r"^diff --git ")

# Matches a diff's "+++ b/<path>" file header. A deleted file's header is
# "+++ /dev/null" instead (no b/ prefix) — captured as `devnull` so the
# caller can tell "no current file" apart from "haven't seen a header
# yet". Only ever consulted for the first such line following a
# _DIFF_GIT_RE match (see the `expect_header` state below) — never
# re-matched against hunk-body content afterward, which is what actually
# closes the spoofing risk described above (the anchor alone isn't
# enough without also refusing to look for more headers once past it).
# git ends the header of a path containing a space with a tab, which must not become part of the path.
_NEW_FILE_HEADER_RE = re.compile(r"^\+\+\+ (?:b/(?P<path>.+?)\t?|(?P<devnull>/dev/null))$")

# Matches a hunk header, e.g. "@@ -12,3 +14,5 @@ context". Only the new file's start line is
# used: the body lines of the hunk say which of its lines were added.
_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,\d+)? @@")


def parse_changed_ranges(diff_text: str) -> dict[str, list[tuple[int, int]]]:
    """Returns {file_path: [(start_line, end_line), ...]} — inclusive,
    1-based, new-file line ranges added or modified by this diff.

    Only the added ("+") lines count. A hunk's header range also covers the
    context lines around an edit when the diff was made with context (`gh pr
    diff` and `git diff` use 3 lines by default), and a context line is not
    a changed line. Counting the "+" lines gives the same ranges for a
    `--unified=0` diff and for one with context.

    Consecutive added lines become one range. A pure deletion adds no line,
    so it contributes no range: there is no line in the new file to attach a
    review scope to. A file touched only by deletions is omitted from the
    result entirely, same as a file with no hunks at all.
    """
    ranges: dict[str, list[tuple[int, int]]] = {}
    current_file: str | None = None
    # True from a "diff --git" line until the matching "+++" header is
    # found. While True, hunk lines are ignored (there's no confirmed
    # current_file yet for a header block still in progress). Once it
    # flips False, _NEW_FILE_HEADER_RE is never consulted again until the
    # next literal "diff --git" line — the reason a hunk body can't
    # hijack current_file no matter what its content looks like.
    expect_header = False
    # The new-file line number the next body line of the current hunk lands on;
    # None outside a hunk.
    new_line: int | None = None
    for line in diff_text.splitlines():
        if _DIFF_GIT_RE.match(line):
            expect_header = True
            new_line = None
            continue
        if expect_header:
            header = _NEW_FILE_HEADER_RE.match(line)
            if header:
                current_file = header.group("path")
                expect_header = False
            continue
        hunk = _HUNK_RE.match(line)
        if hunk:
            new_line = int(hunk.group("start"))
            continue
        if new_line is None or current_file is None:
            continue
        if line.startswith("+"):
            file_ranges = ranges.setdefault(current_file, [])
            if file_ranges and file_ranges[-1][1] == new_line - 1:
                file_ranges[-1] = (file_ranges[-1][0], new_line)
            else:
                file_ranges.append((new_line, new_line))
            new_line += 1
        elif line.startswith("-") or line.startswith("\\"):
            # A removed line has no new-file number; "\ No newline at end of file" is not a line.
            continue
        else:
            new_line += 1
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

    --src-prefix/--dst-prefix are passed explicitly so the output always
    carries "a/"/"b/" regardless of the caller's own git config: a repo
    (or a CI box's global config) with `diff.noprefix=true` set drops
    those prefixes from every header line — including "diff --git" itself
    — which would otherwise make every regex in this module fail to match
    anything, silently returning no ranges for a PR that genuinely has
    changes. Confirmed directly against a `diff.noprefix=true` repo before
    adding this.

    `-c core.quotePath=false` is passed for the same reason, against a
    different default: with quoting on (git's own default), a path with
    a non-ASCII character — plausible for doc filenames — renders as a
    quoted, octal-escaped string (`"caf\303\251.md"`) instead of plain
    UTF-8 text, which the header regex doesn't match either. Confirmed
    directly against a real `café.md` file under `core.quotePath=true`
    (git's default) before adding this — without it, that file silently
    gets zero changed-line ranges despite having a real change.

    Raises `_git.GitError` on failure — via this skill's own copy of
    content-reviewer's git wrapper (`scripts/_git.py`; each skill is
    invoked with PYTHONPATH scoped to only its own directory, so there's
    no cross-skill import path to begin with). This copy adds an explicit
    encoding pin and a subprocess timeout that content-reviewer's own copy
    does NOT have — syncing that hardening back deliberately deferred
    (2026-09-18) rather than applied, since content-reviewer's copy is
    also used by `open_pr.py`'s `git push`, the one call site among its
    users that's genuinely network-bound; a blanket timeout there needs
    its own decision, not one made as a side effect of hardening this
    skill's diff-fetch path."""
    args = [
        "-c", "core.quotePath=false",
        "diff", "--unified=0", "--src-prefix=a/", "--dst-prefix=b/", f"{base}...{head}",
    ]
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

    try:
        diff_text = fetch_diff(Path(args.repo_root), args.base, args.head, args.files or None)
    except _git.GitError as e:
        print(f"[changed_lines] ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(parse_changed_ranges(diff_text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
