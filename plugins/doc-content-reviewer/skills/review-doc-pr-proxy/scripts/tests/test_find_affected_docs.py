from __future__ import annotations

from scripts import find_affected_docs as fad

PROF = {
    "docs_root": "docs/content/", "doc_extensions": [".md"],
    "generated_files": ["docs/content/reference/install-configuration/configuration-options.md"],
}


def _tree(tmp_path):
    root = tmp_path / "docs/content"
    (root / "reference/mw").mkdir(parents=True)
    (root / "reference/install-configuration").mkdir(parents=True)
    (root / "guide").mkdir()
    (root / "guide/retry.md").write_text("Set `maxBackoff` to cap the wait.\n")
    (root / "reference/mw/retry.md").write_text("| maxBackoff | Cap | 10s |\nunrelated line\n")
    (root / "reference/install-configuration/configuration-options.md").write_text("--retry.maxBackoff\n")
    (root / "guide/other.md").write_text("nothing relevant, maxBackoffs is a different word\n")
    (root / "guide/image.png").write_bytes(b"maxBackoff")
    return tmp_path


def test_finds_pages_the_pr_did_not_touch(tmp_path):
    root = _tree(tmp_path)
    out = fad.find_affected(root, PROF, ["maxBackoff"], ["docs/content/guide/retry.md"])
    by = {f["file"]: f for f in out["files"]}
    assert by["docs/content/reference/mw/retry.md"]["in_pr"] is False
    assert by["docs/content/guide/retry.md"]["in_pr"] is True


def test_whole_word_match_only_and_ignores_non_doc_files(tmp_path):
    out = fad.find_affected(_tree(tmp_path), PROF, ["maxBackoff"], [])
    files = {f["file"] for f in out["files"]}
    assert "docs/content/guide/other.md" not in files
    assert not any(f.endswith(".png") for f in files)


def test_flags_generated_files(tmp_path):
    out = fad.find_affected(_tree(tmp_path), PROF, ["maxBackoff"], [])
    gen = [f for f in out["files"] if f["generated"]]
    assert [f["file"] for f in gen] == ["docs/content/reference/install-configuration/configuration-options.md"]


def test_untouched_pages_sort_before_pr_pages_and_seeds_first(tmp_path):
    out = fad.find_affected(
        _tree(tmp_path), PROF, ["maxBackoff"], ["docs/content/guide/retry.md"],
        seeds=["docs/content/reference/mw/retry.md"])
    order = [f["file"] for f in out["files"]]
    assert order[0] == "docs/content/reference/mw/retry.md"
    assert order[-1] == "docs/content/guide/retry.md"


def test_short_terms_are_dropped_and_caps_apply(tmp_path):
    root = _tree(tmp_path)
    assert fad.find_affected(root, PROF, ["a", " "], [])["files"] == []
    for i in range(fad.MAX_FILES + 5):
        (root / f"docs/content/guide/p{i}.md").write_text("maxBackoff\n")
    out = fad.find_affected(root, PROF, ["maxBackoff"], [])
    assert len(out["files"]) == fad.MAX_FILES and out["truncated"] is True
