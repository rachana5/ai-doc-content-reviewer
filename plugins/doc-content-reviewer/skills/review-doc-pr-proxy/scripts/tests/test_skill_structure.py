from __future__ import annotations
import re
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent.parent
SKILL_MD = SKILL_DIR / "SKILL.md"
MAX_SKILL_TOKENS = 5_000
MAX_SKILL_LINES = 500
WORDS_TO_TOKENS = 1.3

REQUIRED_SCRIPTS = {
    "setup.py", "changed_lines.py", "_finding.py", "check_links.py", "aggregate.py", "_git.py",
    "_gh.py", "post_review.py", "pr_filter.py", "profile.py", "missing_docs.py",
    "prepare.py", "find_affected_docs.py",
}
REQUIRED_REFERENCES = {
    "accuracy-checklist.md", "style-checklist.md", "reference-checklist.md", "clarity-checklist.md",
    "finding-schema.md", "completeness-checklist.md", "missing-docs-checklist.md",
    "affected-docs-checklist.md", "proxy-style-guide.md",
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
    fm = _frontmatter(SKILL_MD.read_text())
    assert fm["name"] == "review-doc-pr-proxy"
    assert len(fm["description"]) > 20


def test_skill_md_stays_under_token_and_line_budget():
    text = SKILL_MD.read_text()
    assert int(len(text.split()) * WORDS_TO_TOKENS) <= MAX_SKILL_TOKENS
    assert len(text.splitlines()) <= MAX_SKILL_LINES


def test_skill_md_references_every_script_that_exists():
    text = SKILL_MD.read_text()
    for script in REQUIRED_SCRIPTS:
        assert script.removesuffix(".py") in text, f"SKILL.md never mentions {script}"
        assert (SKILL_DIR / "scripts" / script).exists(), f"{script} is listed but missing"


def test_skill_md_names_the_schema_and_loads_checklists_by_pattern():
    text = SKILL_MD.read_text()
    assert "references/finding-schema.md" in text and "references/<layer>-checklist.md" in text
    for ref in REQUIRED_REFERENCES:
        assert (SKILL_DIR / "references" / ref).exists(), f"{ref} is missing"


def test_skill_md_documents_once_only_trigger_and_marker_semantics():
    text = SKILL_MD.read_text().lower()
    assert "once" in text and "marker" in text
    assert "skip" in text and "edit-in-place" in text


def test_skill_md_documents_never_blocks_merge_and_has_no_pr_gate():
    text = SKILL_MD.read_text().lower()
    assert "never applies fixes" in text and "never blocks merge" in text
    assert "open a pr with these changes" not in text


def test_skill_md_documents_change_scoped_review_and_delivery_modes():
    text = SKILL_MD.read_text().lower()
    assert "scope rule" in text and "never to a whole file" in text
    assert "find_affected_docs" in text and "affected.json" in text
    assert "--dry-run" in text and "--out" in text


def test_skill_md_has_no_design_history_or_other_product_plumbing():
    text = SKILL_MD.read_text().lower()
    for noise in ("docs/superpowers", "byte-identical", "prototype", "demo copy", "traefik-hub", "vale", "hub-doc"):
        assert noise not in text


def test_templates_exist():
    assert (SKILL_DIR / "templates" / "pr-comment.md.tmpl").exists()
