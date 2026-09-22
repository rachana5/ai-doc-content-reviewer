"""post_review.py — renders review-doc-pr's aggregated findings as one PR
comment and posts it, unless one from a previous run of this same PR state
is already there.

This is the only network-writing step in review-doc-pr, and the only place
the plan's "fires once per PR" contract and the marker-based idempotency
check actually meet: a marker match means this workflow got invoked twice
for the same PR (e.g. a CI retry after an infra blip), not a legitimate
update, so the right behavior is to skip, not to edit the existing comment
in place. See docs/superpowers/plans/2026-09-17-per-pr-review-skill-plan.md
(in the automation workspace)'s "New work required" item 2 and the note
under SKILL.md's Step 6 for the full reasoning.

Reuses aggregate.render_report() (content-reviewer's engine, duplicated
byte-for-byte into this skill — see
scripts/tests/test_content_reviewer_duplication_sync.py) for the
non-empty case; the empty-findings case is this module's own special case,
since the mustache-ish template has no conditionals to express "no
findings" without producing an awkward "0 blocking · 0 suggestions" body.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from scripts import _gh, aggregate, changed_lines

MARKER = "<!-- review-doc-pr:v1 -->"

_EMPTY_BODY = f"""## Content review — no issues found

Automated review against source and style rules found nothing to flag. Nothing here blocks merge — this PR goes through its normal review as usual.

{MARKER}
"""


def cap_severity_outside_diff(
    findings: list[dict], changed_ranges: dict[str, list[list[int]]],
) -> list[dict]:
    """Returns a new list, findings unchanged except `severity` forced to
    "suggestion" for any finding whose (file, line) falls outside the PR's
    own changed-line ranges.

    `blocking` is reserved for findings inside the PR's own changed lines
    (see the plan's "Severity cap for out-of-diff findings" section) — the
    whole-file accuracy/reference scan's value is surfacing drift the PR
    happens to touch, not making an unrelated pre-existing issue this PR's
    problem to fix. Style/clarity findings can never be outside their own
    diff-only scope to begin with, so this has no effect on them; nothing
    needs to check `layer`/`layers` to tell the difference.

    Must run before render_report() is called (whether that's from this
    module or from an `aggregate` CLI invocation upstream of it) --
    render_report()'s blocking_count/suggestion_count are computed
    directly from whatever `severity` is on each finding at that point.
    """
    capped = []
    for finding in findings:
        f = dict(finding)
        ranges = [tuple(r) for r in changed_ranges.get(f["file"], [])]
        if not changed_lines.line_in_ranges(f["line"], ranges):
            f["severity"] = "suggestion"
        capped.append(f)
    return capped


def render_comment(findings: list[dict], template_text: str) -> str:
    """The zero-findings special case the mustache-ish template can't
    express on its own (see module docstring); anything non-empty just
    delegates to the already-reused aggregate.render_report()."""
    if not findings:
        return _EMPTY_BODY
    return aggregate.render_report(findings, template_text)


def has_existing_comment(repo: str, pr: str, marker: str = MARKER) -> bool:
    """True if a PR comment containing `marker` already exists.

    Uses `gh pr view --json comments`, not `gh api .../comments
    --paginate` -- the latter prints one JSON array per page when a PR has
    enough comments to paginate, which is NOT valid single-document JSON
    for json.loads to parse. `gh pr view --json` returns one object
    regardless of how many comments there are.
    """
    raw = _gh.run(["pr", "view", pr, "--repo", repo, "--json", "comments"])
    data = json.loads(raw)
    return any(marker in c.get("body", "") for c in data.get("comments", []))


def post_comment(repo: str, pr: str, body: str) -> None:
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
        f.write(body)
        body_path = f.name
    try:
        _gh.run(["pr", "comment", pr, "--repo", repo, "--body-file", body_path])
    finally:
        Path(body_path).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render and post review-doc-pr's findings as one PR comment.")
    parser.add_argument("--repo", required=True, help="owner/repo, e.g. traefik/hub-doc")
    parser.add_argument("--pr", required=True, help="PR number")
    parser.add_argument("--findings", required=True, help="path to aggregate.py's merged findings JSON")
    parser.add_argument("--changed-lines", required=True, help="path to scripts.changed_lines's output JSON")
    parser.add_argument("--template", required=True, help="path to templates/pr-comment.md.tmpl")
    parser.add_argument("--marker", default=MARKER)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print what would be posted instead of calling gh — no marker check either, "
             "since a dry run isn't the real invocation this skill fires once per PR for.",
    )
    args = parser.parse_args(argv)

    findings = json.loads(Path(args.findings).read_text())
    changed_ranges = json.loads(Path(args.changed_lines).read_text())
    findings = cap_severity_outside_diff(findings, changed_ranges)
    template_text = Path(args.template).read_text()
    body = render_comment(findings, template_text)

    if args.dry_run:
        print(body)
        return 0

    if has_existing_comment(args.repo, args.pr, args.marker):
        print(f"[post_review] a comment with marker {args.marker!r} already exists on "
              f"{args.repo}#{args.pr} — skipping (this run is a duplicate invocation, not an update).")
        return 0

    post_comment(args.repo, args.pr, body)
    print(f"[post_review] posted review comment to {args.repo}#{args.pr}.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
