from __future__ import annotations
import re
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent.parent
SKILL_MD = SKILL_DIR / "SKILL.md"
MAX_SKILL_TOKENS = 5_000
MAX_SKILL_LINES = 500
WORDS_TO_TOKENS = 1.3

REQUIRED_SCRIPTS = {
    "setup.py", "_finding.py", "check_links.py", "run_style_lint.py",
    "aggregate.py", "apply_fixes.py", "open_pr.py", "_git.py", "_gh.py",
    "_discover.py",
}
REQUIRED_REFERENCES = {
    "accuracy-checklist.md", "style-checklist.md",
    "reference-checklist.md", "clarity-checklist.md", "finding-schema.md",
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
    assert fm["name"] == "content-reviewer"
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


def test_skill_md_documents_both_modes():
    text = SKILL_MD.read_text().lower()
    assert "full review" in text
    assert "targeted check" in text


def test_skill_md_documents_pr_gate():
    text = SKILL_MD.read_text().lower()
    assert "open a pr" in text or "open_pr" in text
    assert "confirm" in text or "explicit" in text


def test_templates_exist():
    assert (SKILL_DIR / "templates" / "review-report.md.tmpl").exists()
    assert (SKILL_DIR / "templates" / "pr-body.md.tmpl").exists()
