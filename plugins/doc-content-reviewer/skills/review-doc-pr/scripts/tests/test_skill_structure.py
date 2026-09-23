from __future__ import annotations
import re
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent.parent
SKILL_MD = SKILL_DIR / "SKILL.md"
MAX_SKILL_TOKENS = 5_000
MAX_SKILL_LINES = 500
WORDS_TO_TOKENS = 1.3

REQUIRED_SCRIPTS = {
    "setup.py", "_discover.py", "changed_lines.py", "_finding.py",
    "check_links.py", "run_style_lint.py", "aggregate.py", "_git.py",
    "_gh.py", "post_review.py", "pr_filter.py",
}
REQUIRED_REFERENCES = {
    "accuracy-checklist.md", "style-checklist.md",
    "reference-checklist.md", "clarity-checklist.md", "finding-schema.md",
    "completeness-checklist.md",
}


def _frontmatter(text: str) -> dict:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, "SKILL.md must start with --- frontmatter ---"
    fields = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields


def test_skill_md_exists_and_has_frontmatter():
    assert SKILL_MD.exists()
    fm = _frontmatter(SKILL_MD.read_text())
    assert fm["name"] == "review-doc-pr"
    assert "description" in fm and len(fm["description"]) > 20


def test_skill_md_stays_under_token_and_line_budget():
    text = SKILL_MD.read_text()
    tokens = int(len(text.split()) * WORDS_TO_TOKENS)
    assert tokens <= MAX_SKILL_TOKENS, f"~{tokens} tokens exceeds {MAX_SKILL_TOKENS}"
    assert len(text.splitlines()) <= MAX_SKILL_LINES


def test_skill_md_references_every_script_that_exists():
    text = SKILL_MD.read_text()
    for script in REQUIRED_SCRIPTS:
        assert script in text, f"SKILL.md never mentions {script}"


def test_skill_md_references_every_reference_file():
    text = SKILL_MD.read_text()
    for ref in REQUIRED_REFERENCES:
        assert ref in text, f"SKILL.md never mentions {ref}"


def test_skill_md_documents_once_only_trigger_and_marker_semantics():
    text = SKILL_MD.read_text().lower()
    assert "once" in text
    assert "marker" in text
    # the specific contradiction fixed 2026-09-21 must stay fixed
    assert "skip" in text and "edit-in-place" in text


def test_skill_md_documents_never_blocks_merge():
    text = SKILL_MD.read_text().lower()
    assert "never applies fixes" in text or "read-only" in text
    assert "never blocks merge" in text or "advisory" in text


def test_skill_md_does_not_document_a_pr_gate():
    """Unlike content-reviewer, review-doc-pr never opens a PR -- this
    would be a real regression if it crept back in."""
    text = SKILL_MD.read_text().lower()
    assert "open a pr with these changes" not in text


def test_skill_md_documents_per_layer_scope_split():
    text = SKILL_MD.read_text().lower()
    assert "whole file" in text
    assert "diff-scoped" in text or "changed lines" in text


def test_templates_exist():
    assert (SKILL_DIR / "templates" / "pr-comment.md.tmpl").exists()
