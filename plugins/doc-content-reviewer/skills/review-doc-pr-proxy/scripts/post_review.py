"""post_review.py: renders review-doc-pr's aggregated findings as one PR
comment and posts it, unless one from a previous run of this same PR state
is already there.

This is the only network-writing step. A marker match means the workflow was
invoked twice for the same PR (for example a CI retry), not a legitimate
update, so the run skips instead of editing the existing comment.

The empty-findings case is rendered here, since the template has no
conditionals to express "no findings".
"""
from __future__ import annotations

import argparse
import json
import re
import tempfile
from pathlib import Path

from scripts import _gh, aggregate, changed_lines

MARKER = "<!-- review-doc-pr:v1 -->"

_EMPTY_BODY = f"""## Docs review: no issues found

Automated review against the code and the style guide found nothing to flag. Nothing here blocks merge. This PR goes through its normal review.

{MARKER}
"""


def cap_severity_outside_diff(
    findings: list[dict], changed_ranges: dict[str, list[list[int]]],
) -> list[dict]:
    """Returns a new list, findings unchanged except `severity` forced to
    "suggestion" for any finding whose (file, line) falls outside the PR's
    own changed-line ranges.

    `blocking` is reserved for findings inside the PR's own changed lines. A
    finding about the PR's change set on a line or page the PR did not edit
    (an affected reference table, say) is still worth surfacing, but as a
    suggestion the author may act on, not a blocker. This cap applies uniformly to every finding regardless
    of layer -- nothing needs to check `layer`/`layers` to tell the
    difference.

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


def drop_outside_diff(
    findings: list[dict], changed_ranges: dict[str, list[list[int]]], layers: list[str],
) -> list[dict]:
    """Remove findings from `layers` whose line is outside the PR's changed
    lines (a finding merged from several layers is kept if any layer is not
    droppable). Used by profiles whose reference layer scans whole files: an
    old dead link the PR did not touch is not this PR's problem, and listing
    it makes the comment noisy. A finding marked `affected` (for example a link
    this PR broke by renaming a heading, found on a page the PR did not edit)
    is relevant to the PR and is kept."""
    if not layers:
        return findings
    kept = []
    for f in findings:
        if f.get("affected"):
            kept.append(f)
            continue
        fl = f.get("layers", [f["layer"]])
        ranges = [tuple(r) for r in changed_ranges.get(f["file"], [])]
        outside = not changed_lines.line_in_ranges(f["line"], ranges)
        if outside and all(l in layers for l in fl):
            continue
        kept.append(f)
    return kept


COMMENT_SIZE_CAP = 60_000  # GitHub's hard limit is 65,536 characters per comment
_FIX_CAP_ON_SHRINK = 500

_SEVERITY_MARK = {"blocking": "\U0001F534", "suggestion": "\U0001F7E1"}


def _sentences(text: str) -> tuple[str, str]:
    """(first sentence, the rest) of a whitespace-normalized text."""
    text = " ".join(str(text).split())
    m = re.match(r"(.+?[.!?])(?:\s+(.*))?$", text)
    return (m.group(1), m.group(2) or "") if m else (text, "")


def _html_inline(text: str) -> str:
    """Markdown is not rendered inside <summary>, so turn `code` into <code>."""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", text)


def _short_path(path: str) -> str:
    return "/".join(path.split("/")[-3:])


def _is_simple_edit(f: dict) -> bool:
    quote, fix = f["quote"], f["suggested_fix"]
    return (
        f["layer"] != "completeness"
        and "\n" not in quote and "\n" not in fix
        and not fix.startswith("(") and len(quote) < 400 and len(fix) < 400
    )


_LAYER_LABEL = {
    "accuracy": "Accuracy", "style": "Style guide", "reference": "Links and references",
    "clarity": "Clarity", "completeness": "Missing docs",
}


def render_finding(f: dict, fix_cap: int | None = None) -> str:
    """Collapsed row: marker, file:line, the rule that is not being followed.
    Expanded body: what is wrong, then the suggested fix. Nothing is cut off:
    the full reasoning is always in the body."""
    rule = f.get("rule") or _LAYER_LABEL.get(f["layer"], f["layer"].title())
    mark = _SEVERITY_MARK.get(f["severity"], "")
    summary = f'{mark} <code>{_short_path(f["file"])}:{f["line"]}</code> &nbsp;·&nbsp; {_html_inline(rule)}'
    quote, fix = f["quote"].strip(), f["suggested_fix"].strip()
    if fix_cap is not None and len(fix) > fix_cap:
        fix = fix[:fix_cap].rstrip() + "\n\n_(shortened to fit the comment size limit)_"
    parts = [f"<details>\n<summary>{summary}</summary>\n"]
    parts.append(f"**What's wrong:** {' '.join(str(f.get('reasoning', '')).split())}\n")
    if _is_simple_edit(f):
        parts.append("**Suggested fix:**\n")
        parts.append(f"```diff\n- {quote}\n+ {fix}\n```\n")
    elif f["layer"] == "completeness":
        parts.append(f"**Code change:** {quote}\n")
        parts.append("**Suggested fix:**\n")
        parts.append(f"{fix}\n")
    else:
        parts.append("\n".join("> " + line for line in quote.splitlines()) + "\n")
        parts.append("**Suggested fix:**\n")
        parts.append(f"{fix}\n")
    parts.append("</details>\n")
    return "\n".join(parts)


GROUP_THRESHOLD = 8  # group related suggestions only when there are 8 or more
_LINKS_GROUP = "Links and references"


def _group_key(f: dict) -> str | None:
    """Suggestions that share a key are candidates for one grouped row. The agent
    sets `group` (usually the option or field the findings are about); link
    findings from the reference layer group together by default."""
    if f["severity"] == "blocking":
        return None
    if f.get("group"):
        return f["group"].strip()
    return _LINKS_GROUP if f["layer"] == "reference" else None


# Importance of a layer's finding, most important first: a wrong fact, then missing docs,
# then a broken or missing link, then wording, then style.
_LAYER_RANK = {"accuracy": 0, "completeness": 1, "reference": 2, "clarity": 3, "style": 4}


def _order_key(f: dict) -> tuple:
    """Blocking first; then by layer importance, highest confidence, and location."""
    layers = f.get("layers", [f["layer"]])
    rank = min(_LAYER_RANK.get(l, len(_LAYER_RANK)) for l in layers)
    return (f["severity"] != "blocking", rank, -f["confidence"], f["file"], f["line"])


def group_findings(findings: list[dict], threshold: int = GROUP_THRESHOLD) -> list[list[dict]]:
    """Order findings into display units: blocking first, one per unit, then
    suggestions, most important first (see _order_key). With fewer than `threshold` suggestions nothing is grouped.
    At or above it, suggestions sharing a key (two or more) collapse into one
    unit placed where its first member would sit. Blocking is never grouped."""
    ordered = sorted(findings, key=_order_key)
    suggestions = [f for f in ordered if f["severity"] != "blocking"]
    if len(suggestions) < threshold:
        return [[f] for f in ordered]
    members: dict[str, list[dict]] = {}
    for f in suggestions:
        key = _group_key(f)
        if key:
            members.setdefault(key, []).append(f)
    units: list[list[dict]] = []
    placed: set[str] = set()
    for f in ordered:
        key = _group_key(f)
        if key and len(members.get(key, [])) >= 2:
            if key not in placed:
                placed.add(key)
                units.append(members[key])
        else:
            units.append([f])
    return units


def render_group(key: str, members: list[dict], fix_cap: int | None = None) -> str:
    """One collapsed row that opens to the member findings, each still a
    collapsed row of its own, so nothing is hidden or merged away."""
    summary = (f'{_SEVERITY_MARK["suggestion"]} {len(members)} related suggestions'
               f' &nbsp;·&nbsp; {_html_inline(key)}')
    inner = "\n".join(render_finding(f, fix_cap) for f in members)
    return f"<details>\n<summary>{summary}</summary>\n\n{inner}\n</details>\n"


def _render_units(units: list[list[dict]], fix_cap: int | None = None) -> str:
    out = []
    for unit in units:
        if len(unit) == 1:
            out.append(render_finding(unit[0], fix_cap))
        else:
            out.append(render_group(_group_key(unit[0]) or "", unit, fix_cap))
    return "\n".join(out)


def render_findings_block(findings: list[dict]) -> str:
    """Blocking first, then suggestions; within each, by layer importance, then
    confidence, then file and line. Eight or
    more suggestions get related ones grouped (see group_findings). If the result
    would exceed the size cap, shorten the longest suggested fixes."""
    units = group_findings(findings)
    block = _render_units(units)
    if len(block) > COMMENT_SIZE_CAP:
        block = _render_units(units, fix_cap=_FIX_CAP_ON_SHRINK)
        block += "\n_Some suggested text was shortened to fit the comment size limit._\n"
    return block


def render_comment(findings: list[dict], template_text: str, marker: str = MARKER) -> str:
    """The zero-findings special case the mustache-ish template can't
    express on its own (see module docstring); anything non-empty just
    delegates to the already-reused aggregate.render_report().

    `marker` defaults to MARKER; both _EMPTY_BODY and the template file
    embed MARKER as a literal string (there's no {{marker}} placeholder
    to substitute), so a non-default marker is swapped in with a targeted
    string replace afterward. Without this, a caller passing --marker to
    bump the sentinel would change what has_existing_comment searches for
    without changing what actually gets posted -- the idempotency check
    and the posted body silently disagreeing on the marker."""
    if not findings:
        body = _EMPTY_BODY
    elif "{{findings_block}}" in template_text:
        # Header/footer come from the template; the findings are laid out in
        # Python (conditional layout the mustache-ish renderer can't express).
        # Fill the block last so finding text is never scanned for placeholders.
        body = aggregate.render_report(findings, template_text)
        body = body.replace("{{findings_block}}", render_findings_block(findings))
    else:
        body = aggregate.render_report(findings, template_text)
    body = re.sub(r"\b1 suggestions\b", "1 suggestion", body)
    if marker != MARKER:
        body = body.replace(MARKER, marker)
    return body


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
    parser.add_argument("--repo", required=True, help="owner/repo, e.g. traefik/traefik")
    parser.add_argument("--pr", required=True, help="PR number")
    parser.add_argument("--findings", required=True, help="path to aggregate.py's merged findings JSON")
    parser.add_argument("--changed-lines", required=True, help="path to scripts.changed_lines's output JSON")
    parser.add_argument("--template", required=True, help="path to templates/pr-comment.md.tmpl")
    parser.add_argument("--marker", default=MARKER)
    parser.add_argument("--profile", help="product profile; its drop_outside_diff_layers removes out-of-diff findings of those layers")
    parser.add_argument("--classify", help="classify.json from scripts.missing_docs; decides whether any comment is posted at all")
    parser.add_argument(
        "--out", help="write the rendered comment to this file and stop: no marker check, no "
                      "posting. For a workflow that posts the comment itself.")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print what would be posted instead of calling gh — no marker check either, "
             "since a dry run isn't the real invocation this skill fires once per PR for.",
    )
    args = parser.parse_args(argv)

    action = json.loads(Path(args.classify).read_text())["action"] if args.classify else None
    findings = json.loads(Path(args.findings).read_text())
    changed_ranges = json.loads(Path(args.changed_lines).read_text())
    if args.profile:
        from scripts import profile as profile_mod
        findings = drop_outside_diff(
            findings, changed_ranges, profile_mod.load(args.profile).get("drop_outside_diff_layers", []))
    findings = cap_severity_outside_diff(findings, changed_ranges)

    # Silence rules: nothing to review, or a code-only PR with no docs gap found.
    if action == "silent" or (action == "missing-docs-only" and not findings):
        print(f"[post_review] action={action} with {len(findings)} finding(s): no comment posted.")
        return 0
    template_text = Path(args.template).read_text()
    body = render_comment(findings, template_text, args.marker)

    if args.out:
        Path(args.out).write_text(body)
        print(f"[post_review] wrote the comment to {args.out}; nothing posted.")
        return 0

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
