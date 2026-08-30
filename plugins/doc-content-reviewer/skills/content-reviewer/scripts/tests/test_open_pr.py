# scripts/tests/test_open_pr.py
from __future__ import annotations
from unittest import mock

from scripts import open_pr


def test_create_branch_calls_git_checkout_b(monkeypatch):
    calls = []
    monkeypatch.setattr(open_pr._git, "run", lambda repo, args: calls.append(args))
    open_pr.create_branch("/repo", "content-review/2026-08-28")
    assert ["checkout", "-b", "content-review/2026-08-28"] in calls


def test_commit_changes_calls_git_add_and_commit(monkeypatch):
    calls = []
    monkeypatch.setattr(open_pr._git, "run", lambda repo, args: calls.append(args))
    open_pr.commit_changes("/repo", "fix: apply review findings", ["docs/a.md", "docs/b.md"])
    assert ["add", "docs/a.md", "docs/b.md"] in calls
    assert ["commit", "-m", "fix: apply review findings"] in calls


def test_open_pr_pushes_and_creates_pr(monkeypatch):
    git_calls = []
    monkeypatch.setattr(open_pr._git, "run", lambda repo, args: git_calls.append(args))
    monkeypatch.setattr(
        open_pr._gh, "run",
        lambda args: "https://github.com/x/y/pull/42\n",
    )
    result = open_pr.open_pr(
        "/repo", branch="content-review/2026-08-28",
        title="docs: content review fixes", body="body text",
    )
    assert result.url == "https://github.com/x/y/pull/42"
    assert result.branch == "content-review/2026-08-28"
    assert ["push", "-u", "origin", "content-review/2026-08-28"] in git_calls


def test_main_creates_branch_commits_and_opens_pr(monkeypatch, tmp_path, capsys):
    import json
    calls = []
    monkeypatch.setattr(open_pr._git, "run", lambda repo, args: calls.append(args))
    monkeypatch.setattr(open_pr._gh, "run", lambda args: "https://github.com/x/y/pull/9\n")

    exit_code = open_pr.main([
        "--repo-root", str(tmp_path), "--branch", "content-review/test",
        "--title", "docs: fixes", "--body", "body", "--files", "docs/a.md",
    ])
    assert exit_code == 0
    result = json.loads(capsys.readouterr().out)
    assert result["url"] == "https://github.com/x/y/pull/9"
    assert ["checkout", "-b", "content-review/test"] in calls
    assert ["add", "docs/a.md"] in calls
