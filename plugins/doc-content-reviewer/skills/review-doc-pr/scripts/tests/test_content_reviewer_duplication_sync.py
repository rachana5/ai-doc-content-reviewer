"""Guards against silent drift between review-doc-pr's duplicated copies of
content-reviewer's shared engine and the canonical originals.

review-doc-pr can't import content-reviewer's modules at runtime -- each
skill is invoked with PYTHONPATH scoped to its OWN directory (see
changed_lines.py's module docstring for the same constraint applied to this
skill's git-diff wrapper), and once review-doc-pr is copied standalone into
hub-doc/.claude/skills/review-doc-pr/, content-reviewer won't even exist
alongside it on disk. So the finding schema (_finding.py), the mechanical
reference/style checkers (check_links.py, run_style_lint.py), the
aggregation/report logic (aggregate.py), and all five reference docs
(finding-schema.md + the four checklists) are duplicated file-for-file
rather than shared.

Unlike _git.py (duplicated in step 1, deliberately allowed to diverge --
content-reviewer's copy alone does open_pr.py's network-bound git push,
which needs its own timeout decision), these files are supposed to be the
EXACT same logic and the exact same checklists -- a human running
content-reviewer and the automated review-doc-pr should reach the same
verdict on the same content. So this test requires byte-for-byte identity,
not just equivalent behavior: any edit to a checklist or to the schema/
aggregation code that isn't mirrored to the other skill fails here
immediately, instead of silently making review-doc-pr's findings diverge
from what content-reviewer would report for the same text.

This is a same-repo, same-test-run check (unlike
tools/check_review_doc_pr_sync.py, which checks review-doc-pr's OWN copy
against the separate traefik/hub-doc checkout -- a different repo, a
different failure mode, a different tool).
"""
from __future__ import annotations

from pathlib import Path

# this_file -> tests -> scripts -> review-doc-pr (skill dir) -> skills
_SKILLS_ROOT = Path(__file__).resolve().parents[3]
_REVIEW_DOC_PR = _SKILLS_ROOT / "review-doc-pr"
_CONTENT_REVIEWER = _SKILLS_ROOT / "content-reviewer"

# Duplicated verbatim -- must stay byte-identical. If a real, concrete need
# to diverge ever shows up (the same kind of thing that justified _git.py's
# divergence), move that path's assertion out of this list into its own
# documented exception, the same way tools/check_review_doc_pr_sync.py's
# KNOWN_EXCEPTIONS works for the hub-doc copy -- don't just delete the check.
_DUPLICATED_SCRIPTS = (
    "aggregate.py", "check_links.py", "run_style_lint.py", "_finding.py",
    # run_style_lint.py imports `from scripts.setup import check_lint_tools`
    # -- setup.py has to be duplicated too, or that import fails the moment
    # review-doc-pr runs standalone with no content-reviewer alongside it.
    "setup.py",
    # Locates the local traefik-hub clone the accuracy layer reads
    # against (Step 1) -- its $TRAEFIK_HUB_PATH env var escape hatch is
    # what makes it usable non-interactively in CI, no AskUserQuestion
    # needed on the happy path.
    "_discover.py",
    # post_review.py's gh CLI wrapper (Step 6) -- generic, no
    # content-reviewer-specific behavior, unlike _git.py which has a real
    # documented reason to diverge (see review-doc-pr's own _git.py
    # docstring).
    "_gh.py",
)
_DUPLICATED_REFERENCES = (
    "finding-schema.md", "accuracy-checklist.md", "style-checklist.md",
    "reference-checklist.md", "clarity-checklist.md",
)


def _assert_in_sync(rel_dir: str, filename: str) -> None:
    review_doc_pr_copy = _REVIEW_DOC_PR / rel_dir / filename
    canonical = _CONTENT_REVIEWER / rel_dir / filename
    assert canonical.exists(), f"canonical file missing: {canonical}"
    assert review_doc_pr_copy.exists(), f"review-doc-pr's copy missing: {review_doc_pr_copy}"
    assert review_doc_pr_copy.read_text() == canonical.read_text(), (
        f"{filename} has drifted between content-reviewer/{rel_dir}/ and "
        f"review-doc-pr/{rel_dir}/ -- a change applied to one copy wasn't "
        f"mirrored to the other. Sync them, or move this file into a "
        f"documented, explained exception if the divergence is real and "
        f"intentional."
    )


def test_duplicated_scripts_stay_in_sync():
    for filename in _DUPLICATED_SCRIPTS:
        _assert_in_sync("scripts", filename)


def test_duplicated_references_stay_in_sync():
    for filename in _DUPLICATED_REFERENCES:
        _assert_in_sync("references", filename)
