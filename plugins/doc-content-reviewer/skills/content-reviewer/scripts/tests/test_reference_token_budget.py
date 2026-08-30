from __future__ import annotations
from pathlib import Path

REFERENCES_DIR = Path(__file__).parent.parent.parent / "references"
MAX_TOKENS_PER_FILE = 10_000
WORDS_TO_TOKENS = 1.3  # rough heuristic: tokens ≈ words * 1.3


def _estimate_tokens(text: str) -> int:
    return int(len(text.split()) * WORDS_TO_TOKENS)


def test_all_layer_checklists_exist():
    expected = {
        "accuracy-checklist.md", "style-checklist.md",
        "reference-checklist.md", "clarity-checklist.md",
    }
    actual = {p.name for p in REFERENCES_DIR.glob("*-checklist.md")}
    assert expected == actual


def test_each_checklist_stays_under_token_budget():
    for path in REFERENCES_DIR.glob("*-checklist.md"):
        tokens = _estimate_tokens(path.read_text())
        assert tokens <= MAX_TOKENS_PER_FILE, f"{path.name}: ~{tokens} tokens exceeds {MAX_TOKENS_PER_FILE}"


def test_each_checklist_has_worked_examples():
    for path in REFERENCES_DIR.glob("*-checklist.md"):
        text = path.read_text()
        assert "## Example" in text or "### Example" in text, f"{path.name} has no worked example section"
