from __future__ import annotations

from pathlib import Path

from tools.check_review_doc_pr_sync import _relevant_files, check_sync


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_relevant_files_ignores_pycache_and_pyc(tmp_path):
    _write(tmp_path, "scripts/foo.py", "x")
    _write(tmp_path, "scripts/__pycache__/foo.cpython-311.pyc", "junk")
    assert _relevant_files(tmp_path) == {"scripts/foo.py"}


def test_identical_trees_have_no_problems(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    _write(source, "scripts/foo.py", "same content")
    _write(target, "scripts/foo.py", "same content")
    assert check_sync(source=source, target=target) == []


def test_missing_file_in_target_is_reported(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    _write(source, "scripts/foo.py", "content")
    target.mkdir()
    problems = check_sync(source=source, target=target)
    assert len(problems) == 1
    assert "missing in hub-doc copy: scripts/foo.py" in problems[0]


def test_extra_file_in_target_is_reported(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.mkdir()
    _write(target, "scripts/extra.py", "content")
    problems = check_sync(source=source, target=target)
    assert len(problems) == 1
    assert "unexpected extra file" in problems[0]


def test_differing_content_is_reported(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    _write(source, "scripts/foo.py", "version A")
    _write(target, "scripts/foo.py", "version B")
    problems = check_sync(source=source, target=target)
    assert len(problems) == 1
    assert "content differs: scripts/foo.py" in problems[0]


def test_known_exception_is_excluded_from_comparison(tmp_path, monkeypatch):
    source = tmp_path / "source"
    target = tmp_path / "target"
    _write(source, "SKILL.md", "plugin version")
    _write(target, "SKILL.md", "hub-doc-specific version")
    _write(source, "scripts/changed_lines.py", "same")
    _write(target, "scripts/changed_lines.py", "same")

    import tools.check_review_doc_pr_sync as mod

    monkeypatch.setattr(mod, "KNOWN_EXCEPTIONS", {"SKILL.md": "test exception"})
    assert check_sync(source=source, target=target) == []


def test_not_copied_file_is_not_reported_as_missing(tmp_path, monkeypatch):
    source = tmp_path / "source"
    target = tmp_path / "target"
    _write(source, "scripts/tests/test_only_makes_sense_here.py", "content")
    target.mkdir()

    import tools.check_review_doc_pr_sync as mod

    monkeypatch.setattr(
        mod, "NOT_COPIED_TO_HUB_DOC", {"scripts/tests/test_only_makes_sense_here.py": "test reason"}
    )
    assert check_sync(source=source, target=target) == []


def test_not_copied_file_showing_up_in_target_anyway_is_still_reported(tmp_path, monkeypatch):
    source = tmp_path / "source"
    target = tmp_path / "target"
    _write(source, "scripts/tests/test_only_makes_sense_here.py", "content")
    _write(target, "scripts/tests/test_only_makes_sense_here.py", "content")

    import tools.check_review_doc_pr_sync as mod

    monkeypatch.setattr(
        mod, "NOT_COPIED_TO_HUB_DOC", {"scripts/tests/test_only_makes_sense_here.py": "test reason"}
    )
    problems = check_sync(source=source, target=target)
    assert len(problems) == 1
    assert "unexpected extra file" in problems[0]


def test_main_reports_exit_code_2_when_hub_doc_copy_missing(tmp_path, capsys):
    import tools.check_review_doc_pr_sync as mod

    empty_hub_doc = tmp_path / "not-a-hub-doc-clone"
    empty_hub_doc.mkdir()
    exit_code = mod.main(["--hub-doc-root", str(empty_hub_doc)])
    assert exit_code == 2
