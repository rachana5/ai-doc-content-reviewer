#!/usr/bin/env python3
"""check_review_doc_pr_sync.py -- guard against drift between this repo's
canonical `review-doc-pr` skill and the copy checked into `traefik/hub-doc`
at `.claude/skills/review-doc-pr/`.

Background: `review-doc-pr` is a sibling skill to `content-reviewer` in this
repo, but only `review-doc-pr` gets embedded in `hub-doc` -- it's the CI-
triggered, comment-only skill described in
`docs/superpowers/plans/2026-09-17-per-pr-review-skill-plan.md` (in the
`automation` workspace, not this repo). `content-reviewer` itself stays
plugin-only, invoked on demand by a human; nothing about it is copied
anywhere. The copy is a plain file copy, not a shared import or a submodule
-- same constraint as `hub-doc-pr-generator`'s own copy into `hub-doc`, whose
sync checker (`check_hub_doc_pr_generator_sync.py`, in the sibling
`ai-ws-hub-doc-pr-generator` repo) this tool mirrors.

Default policy: everything should match, byte for byte, with NO exceptions
list up front. If a concrete need to diverge shows up later (most likely
`SKILL.md`, once written, if each copy's own "Required environment"/intro
section needs to describe its own distribution the way
`hub-doc-pr-generator`'s does), add that specific relative path to
KNOWN_EXCEPTIONS below with a comment explaining why.

Usage:
    python3 tools/check_review_doc_pr_sync.py --hub-doc-root <path>

Exit codes:
    0  in sync
    1  drift detected (see output for which files and how)
    2  the hub-doc copy doesn't exist yet (nothing to compare against)
"""
from __future__ import annotations

import argparse
import filecmp
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SOURCE_SKILL = _REPO_ROOT / "plugins" / "doc-content-reviewer" / "skills" / "review-doc-pr"

# Directories/files never expected to match -- build artifacts, not source.
_IGNORE_NAMES = {"__pycache__", ".pytest_cache", ".DS_Store"}
_IGNORE_SUFFIXES = {".pyc"}

# Relative paths (POSIX-style, relative to the skill directory root) that
# are allowed to differ, each with a reason. Empty by design -- see module
# docstring. Add an entry only once a real, concrete need to diverge exists.
KNOWN_EXCEPTIONS: dict[str, str] = {}

# Relative paths that exist in this repo's canonical skill but are
# deliberately NEVER copied into hub-doc's embedded copy -- distinct from
# KNOWN_EXCEPTIONS above, which is for files present in BOTH that are
# allowed to differ.
#
# Found 2026-09-21 by actually testing a real copy in place (not just
# running check_sync, which only compares files that exist on both sides
# and would never have caught this): test_content_reviewer_duplication_sync.py
# asserts content-reviewer's canonical files exist as a SIBLING skill
# directory (`_SKILLS_ROOT / "content-reviewer"`) -- true in this repo,
# false once review-doc-pr is copied standalone into hub-doc, since
# content-reviewer is never copied there at all. Same class of problem
# ai-ws-hub-doc-pr-generator's own NOT_COPIED_TO_HUB_DOC solves for its
# test_cross_skill_duplication_sync.py -- confirmed that repo's real
# hub-doc copy excludes that file the same way.
NOT_COPIED_TO_HUB_DOC: dict[str, str] = {
    "scripts/tests/test_content_reviewer_duplication_sync.py": (
        "Guards against drift between review-doc-pr's duplicated engine "
        "files and content-reviewer's canonical ones by comparing against "
        "a sibling content-reviewer/ directory -- a relationship that only "
        "exists in this repo. content-reviewer is never copied into "
        "hub-doc, so there is nothing there for this test to compare "
        "against; the invariant it checks is still verified at the "
        "source, in this repo's own test suite."
    ),
}


def _relevant_files(root: Path) -> set[str]:
    found = set()
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if any(part in _IGNORE_NAMES for part in path.parts):
            continue
        if path.suffix in _IGNORE_SUFFIXES:
            continue
        found.add(str(path.relative_to(root).as_posix()))
    return found


def check_sync(*, source: Path, target: Path) -> list[str]:
    """Return a list of human-readable problem descriptions; empty if in sync."""
    problems: list[str] = []

    source_files = _relevant_files(source)
    target_files = _relevant_files(target)

    # NOT_COPIED_TO_HUB_DOC paths are stripped from source only, not target:
    # they're never expected in the copy (so no "missing" report), but if one
    # ever DID show up in target that would be a real, worth-flagging
    # surprise, not something to silently tolerate.
    checked_source = source_files - KNOWN_EXCEPTIONS.keys() - NOT_COPIED_TO_HUB_DOC.keys()
    checked_target = target_files - KNOWN_EXCEPTIONS.keys()

    missing_in_target = sorted(checked_source - checked_target)
    for rel in missing_in_target:
        problems.append(f"missing in hub-doc copy: {rel}")

    extra_in_target = sorted(checked_target - checked_source)
    for rel in extra_in_target:
        problems.append(f"unexpected extra file in hub-doc copy (not in plugin repo): {rel}")

    common = sorted(checked_source & checked_target)
    for rel in common:
        if not filecmp.cmp(source / rel, target / rel, shallow=False):
            problems.append(f"content differs: {rel}")

    return problems


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Check that hub-doc's copy of review-doc-pr matches this repo's canonical version."
    )
    parser.add_argument(
        "--hub-doc-root", required=True,
        help="Path to a local traefik/hub-doc clone (the one containing .claude/skills/review-doc-pr/).",
    )
    args = parser.parse_args(argv)

    target = Path(args.hub_doc_root).expanduser().resolve() / ".claude" / "skills" / "review-doc-pr"
    if not target.is_dir():
        print(f"hub-doc copy not found at {target} -- nothing to compare against yet.", file=sys.stderr)
        return 2

    if KNOWN_EXCEPTIONS:
        print("Documented exceptions (present in both, allowed to differ):")
        for rel, reason in sorted(KNOWN_EXCEPTIONS.items()):
            print(f"  - {rel}: {reason}")
        print()

    if NOT_COPIED_TO_HUB_DOC:
        print("Deliberately not copied to hub-doc (not expected in the copy at all):")
        for rel, reason in sorted(NOT_COPIED_TO_HUB_DOC.items()):
            print(f"  - {rel}: {reason}")
        print()

    problems = check_sync(source=_SOURCE_SKILL, target=target)
    if not problems:
        print(f"In sync: {target} matches {_SOURCE_SKILL}.")
        return 0

    print(f"Drift detected between {_SOURCE_SKILL} and {target}:")
    for p in problems:
        print(f"  - {p}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
