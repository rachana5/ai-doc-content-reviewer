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
import sys
import tempfile
from pathlib import Path

from scripts import _finding, _gh, aggregate, changed_lines

MARKER = "<!-- review-doc-pr:v1 -->"

_EMPTY_BODY = f"""## Docs review: no issues found

{{{{commit_line}}}}

Automated review against the code and the style guide found nothing to flag. Nothing here blocks merge. This PR goes through its normal review.

{MARKER}
"""


def all_as_suggestions(findings: list[dict]) -> list[dict]:
    """Returns a new list, findings unchanged except `severity` forced to
    "suggestion".

    This comment is advisory and never blocks merge, and a docs reviewer is not the
    one to decide that a PR is blocked, so every finding is shown as a suggestion.
    How much a finding matters is its `impact`, which sets the order (see _order_key).
    Must run before render_comment(): the heading's suggestion_count is computed from
    whatever `severity` each finding has at that point."""
    return [{**f, "severity": "suggestion"} for f in findings]


def drop_outside_diff(
    findings: list[dict], changed_ranges: dict[str, list[list[int]]], layers: list[str],
) -> list[dict]:
    """Remove findings from `layers` whose line is outside the PR's changed
    lines (a finding merged from several layers is kept if any layer is not
    droppable). Used for layers scoped to the PR's own lines (reference, style, clarity): an
    old dead link or a wording nit on text the PR did not touch is not this PR's problem, and
    listing it makes the comment noisy. A finding about the whole file (`line` 0) is kept. A finding marked `affected` (for example a link
    this PR broke by renaming a heading, found on a page the PR did not edit)
    is relevant to the PR and is kept."""
    if not layers:
        return findings
    kept = []
    for f in findings:
        if f.get("affected"):
            kept.append(f)
            continue
        if f["line"] == 0:
            # A finding about the whole file has no line to compare with the changed ranges.
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


# A markdown link or image: `[text](target)` / `![alt](target)`. The target may hold one level of
# balanced parentheses (`page_(draft).md`).
_MD_LINK = re.compile(r"(!?)\[([^\]]*)\]\(((?:[^()\s]|\([^()\s]*\))+)(?:\s+\"[^\"]*\")?\)")
_CODE_SPAN = re.compile(r"(`+)(?:(?!\1).)+?\1", re.DOTALL)


def _is_safe_target(target: str) -> bool:
    """Only a full HTTPS URL, an in-page anchor or a mailto survives the posting workflow."""
    return target.startswith(("https://", "#", "mailto:"))


def neutralize_links(text: str) -> str:
    """Rewrite a markdown link or image whose target is not a full HTTPS URL, `[text](../a.md#x)`,
    as `text (`../a.md#x`)`. The posting workflow replaces such a link (a relative path, but also
    `http://`) with "(link unavailable: invalid HTTPS URL)" in prose and block quotes, so it would
    reach the contributor corrupted. HTTPS links, in-page anchors and mailto links are left alone.
    Text inside inline code is never touched (it is shown verbatim). Fenced code is not rewritten
    by the workflow, so callers keep verbatim text in fences instead."""
    def fix(m: re.Match) -> str:
        bang, label, target = m.group(1), m.group(2), m.group(3)
        if _is_safe_target(target):
            return m.group(0)
        label = label or ("image" if bang else target)
        return f"{label} (`{target}`)"

    out, pos = [], 0
    for code in _CODE_SPAN.finditer(text):
        out.append(_MD_LINK.sub(fix, text[pos:code.start()]))
        out.append(code.group(0))
        pos = code.end()
    out.append(_MD_LINK.sub(fix, text[pos:]))
    return "".join(out)


def fenced(text: str, lang: str = "") -> str:
    """`text` in a code fence long enough to contain any fence inside it. Text in a fence is
    shown and copied verbatim and is never rewritten, so a relative link survives."""
    longest = max((len(m) for m in re.findall(r"`{3,}", text)), default=2)
    fence = "`" * max(3, longest + 1)
    return f"{fence}{lang}\n{text}\n{fence}"


_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def is_full_sha(commit: str | None) -> bool:
    return bool(commit and _FULL_SHA.match(commit))


def commit_line(commit: str | None, repo: str | None = None) -> str:
    """"Reviewed at commit `abc1234` ([view](commit URL))." The text up to and including the
    opening backtick must stay exactly as written: the traefik/ai workflow finds a PR it
    already reviewed by searching comments for "Reviewed at commit `". A link wrapped around
    the SHA would break that match, so the link follows it. Empty when no commit is given."""
    if not commit:
        return ""
    short = commit[:7]
    if repo:
        return f"Reviewed at commit `{short}` ([view](https://github.com/{repo}/commit/{commit}))."
    return f"Reviewed at commit `{short}`."


STYLE_LAYERS = ("style", "clarity")


def merge_same_rule(findings: list[dict]) -> list[dict]:
    """One finding per (file, layer, rule) for style and clarity: a style and a clarity finding with
    the same rule label stay apart. The same wording rule broken on
    several lines of one file is one thing for the author to fix, not several: on
    traefik/traefik#14302 one terminology rule in one table row was reported as three
    suggestions. The first finding (by line) leads; the others are kept as `occurrences`
    (line, quote, fix) and rendered inside it. Other layers are never merged: two accuracy
    findings are two different facts."""
    out: list[dict] = []
    lead: dict[tuple, dict] = {}
    for f in sorted(findings, key=lambda x: (x["file"], x["line"])):
        if f["layer"] not in STYLE_LAYERS or not f.get("rule") or f["line"] == 0:
            # A finding about the whole file (line 0) has no line to list and would lead the
            # merged row with a meaningless location, so it stays on its own.
            out.append(f)
            continue
        key = (f["file"], f["layer"], f["rule"])
        if key in lead:
            lead[key].setdefault("occurrences", []).append(
                {"line": f["line"], "quote": f["quote"], "suggested_fix": f["suggested_fix"]})
            lead[key]["confidence"] = max(lead[key]["confidence"], f["confidence"])
        else:
            f = {**f}
            lead[key] = f
            out.append(f)
    return out


_LAYER_LABEL = {
    "accuracy": "Accuracy", "style": "Style guide", "reference": "Links and references",
    "clarity": "Clarity", "completeness": "Completeness",
}


def _fix_block(f: dict, with_label: bool = False) -> str:
    """The quote and suggested fix of one finding (or one occurrence of a merged one). A one-line
    literal replacement is a before/after diff; anything else (a `(needs a human to ...)` fix, a
    multi-line quote, a completeness draft) is shown as a fenced quote and a fenced fix, never as
    paste-able replacement text."""
    quote, fix = f["quote"], f["suggested_fix"]
    label = "**Suggested fix:**\n\n" if with_label else ""
    if _is_simple_edit(f):
        return f"{label}{fenced('- ' + quote + chr(10) + '+ ' + fix, 'diff')}\n\n"
    if f["layer"] == "completeness":
        return (f"**Code change:** {neutralize_links(quote)}\n\n**Suggested fix:**\n\n"
                f"{fenced(fix, 'markdown')}\n\n")
    return f"{fenced(quote)}\n\n{'**Suggested fix:**' + chr(10) + chr(10) if with_label else ''}{fenced(fix, 'markdown')}\n\n"


def render_finding(f: dict, fix_cap: int | None = None) -> str:
    """Collapsed row: marker, file:line, the rule that is not being followed.
    Expanded body: what is wrong, then the suggested fix. Nothing is cut off:
    the full reasoning is always in the body."""
    rule = f.get("rule") or _LAYER_LABEL.get(f["layer"], f["layer"].title())
    more = f["occurrences"] if f.get("occurrences") else []
    where = f'{_short_path(f["file"])}:{f["line"]}' + (f" (+{len(more)} more)" if more else "")
    summary = f'<code>{where}</code> &nbsp;·&nbsp; {_html_inline(rule)}'
    quote, fix = f["quote"].strip(), f["suggested_fix"].strip()
    if fix_cap is not None and len(fix) > fix_cap:
        fix = fix[:fix_cap].rstrip() + "\n\n_(shortened to fit the comment size limit)_"
    parts = [f"<details>\n<summary>{summary}</summary>\n"]
    parts.append(f"**What's wrong:** {neutralize_links(' '.join(str(f.get('reasoning', '')).split()))}\n")
    if more:
        parts.append("**Suggested fix, at each place:**\n")
        for occ in [{"line": f["line"], "quote": quote, "suggested_fix": fix}, *more]:
            ofix = occ["suggested_fix"].strip()
            if fix_cap is not None and len(ofix) > fix_cap:
                ofix = ofix[:fix_cap].rstrip() + "\n\n_(shortened to fit the comment size limit)_"
            parts.append(f"Line {occ['line']}:\n")
            parts.append(_fix_block({**f, "quote": occ["quote"].strip(), "suggested_fix": ofix}))
    else:
        parts.append(_fix_block({**f, "quote": quote, "suggested_fix": fix}, with_label=True))
    parts.append("</details>\n")
    return "\n".join(parts)


GROUP_THRESHOLD = 8  # group related suggestions only when there are 8 or more
_LINKS_GROUP = "Links and references"


def _group_key(f: dict) -> str | None:
    """Suggestions that share a key are candidates for one grouped row. The agent
    sets `group` (usually the option or field the findings are about); link
    findings from the reference layer group together by default."""
    if f.get("group"):
        return f["group"].strip()
    return _LINKS_GROUP if f["layer"] == "reference" else None


# Tie-break inside one impact level: a wrong fact, then missing docs, then a broken or
# missing link, then wording, then style.
_LAYER_RANK = {"accuracy": 0, "completeness": 1, "reference": 2, "clarity": 3, "style": 4}


def _order_key(f: dict) -> tuple:
    """Most to least impactful: by impact (high, medium, low; see
    _finding.effective_impact for the default of a finding that sets none), then layer
    importance, highest confidence, and location."""
    layers = f.get("layers", [f["layer"]])
    rank = min(_LAYER_RANK.get(l, len(_LAYER_RANK)) for l in layers)
    return (_finding.IMPACT_RANK[_finding.effective_impact(f)], rank, -f["confidence"], f["file"], f["line"])


def group_findings(findings: list[dict], threshold: int = GROUP_THRESHOLD) -> list[list[dict]]:
    """Order findings into display units, most impactful first (see _order_key).
    With fewer than `threshold` findings nothing is grouped. At or above it,
    findings sharing a key (two or more) collapse into one unit placed where its
    first member would sit."""
    ordered = sorted(findings, key=_order_key)
    if len(ordered) < threshold:
        return [[f] for f in ordered]
    members: dict[str, list[dict]] = {}
    for f in ordered:
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
    summary = f'{len(members)} related suggestions &nbsp;·&nbsp; {_html_inline(key)}'
    inner = "\n".join(render_finding(f, fix_cap) for f in members)
    return f"<details>\n<summary>{summary}</summary>\n\n{inner}\n</details>\n"


def _render_units(units: list, fix_cap: int | None = None) -> str:
    out = []
    for unit in units:
        if isinstance(unit, tuple):
            out.append(_render_fold(unit[1], fix_cap))
        elif len(unit) == 1:
            out.append(render_finding(unit[0], fix_cap))
        else:
            out.append(render_group(_group_key(unit[0]) or "", unit, fix_cap))
    return "\n".join(out)


STYLE_VISIBLE = 3  # wording-only units shown as their own row; the rest fold into one


def fold_wording(units: list[list[dict]], visible: int = STYLE_VISIBLE) -> list:
    """Keep the first `visible` units made only of style or clarity findings, and fold the
    rest into one collapsed row placed where the first folded unit would sit. Wording nits
    are the lowest-impact findings, so a long run of them no longer pushes real findings
    out of view. Nothing is dropped: the fold opens to every finding."""
    out: list = []
    folded: list[list[dict]] = []
    seen = 0
    slot = None
    for unit in units:
        if all(f["layer"] in STYLE_LAYERS for f in unit):
            seen += 1
            if seen > visible:
                if slot is None:
                    slot = len(out)
                    out.append(None)
                folded.append(unit)
                continue
        out.append(unit)
    if slot is not None:
        out[slot] = ("fold", folded)
    return out


def _render_fold(folded: list[list[dict]], fix_cap: int | None = None) -> str:
    n = sum(len(u) for u in folded)
    inner = _render_units(folded, fix_cap)
    return (f"<details>\n<summary>{n} more wording suggestions &nbsp;·&nbsp; style and clarity"
            f"</summary>\n\n{inner}\n</details>\n")


def render_findings_block(findings: list[dict]) -> str:
    """Most impactful first, then by layer importance, confidence, file and line.
    Eight or more findings get related ones grouped (see group_findings). If the
    result would exceed the size cap, shorten the longest suggested fixes."""
    units = fold_wording(group_findings(findings))
    block = _render_units(units)
    if len(block) > COMMENT_SIZE_CAP:
        block = _render_units(units, fix_cap=_FIX_CAP_ON_SHRINK)
        block += "\n_Some suggested text was shortened to fit the comment size limit._\n"
    return block


def render_comment(findings: list[dict], template_text: str, marker: str = MARKER, reviewed: str = "") -> str:
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
    # The commit line sits under the heading; a template without the placeholder gets it
    # inserted after its first line.
    if "{{commit_line}}" in body:
        body = body.replace("{{commit_line}}\n\n", f"{reviewed}\n\n" if reviewed else "")
        body = body.replace("{{commit_line}}", reviewed)
    elif reviewed:
        head, _, rest = body.partition("\n\n")
        body = f"{head}\n\n{reviewed}\n\n{rest}"
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
    parser.add_argument("--commit", help="the PR head commit the review ran on (full 40-character SHA; "
                        "`head_sha` of context.json, captured when the review started). Shown under the "
                        "heading as \"Reviewed at commit\". Required unless --dry-run: the traefik/ai "
                        "workflow finds an already-reviewed PR by that text, so a comment without it "
                        "would be reviewed again.")
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
    findings = merge_same_rule(all_as_suggestions(findings))

    # Silence rules: nothing to review, or a code-only PR with no docs gap found.
    if action == "silent" or (action == "missing-docs-only" and not findings):
        print(f"[post_review] action={action} with {len(findings)} finding(s): no comment posted.")
        return 0
    if not is_full_sha(args.commit):
        msg = (f"[post_review] --commit must be the full 40-character head SHA the review ran on "
               f"(got {args.commit!r}); take it from context.json (`head_sha`), not from a lookup made now.")
        if not args.dry_run:
            print(msg + " Nothing posted or written.", file=sys.stderr)
            return 2
        print(msg + " Dry run: continuing without the commit line.", file=sys.stderr)
        args.commit = None
    template_text = Path(args.template).read_text()
    body = render_comment(findings, template_text, args.marker, commit_line(args.commit, args.repo))

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
    sys.exit(main())
