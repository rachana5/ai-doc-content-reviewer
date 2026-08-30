from __future__ import annotations
from unittest import mock
import pytest

from scripts import _git, _gh


def test_git_run_returns_stdout_on_success(monkeypatch):
    monkeypatch.setattr(
        _git.subprocess, "run",
        lambda cmd, **k: mock.Mock(returncode=0, stdout="ok\n", stderr=""),
    )
    result = _git.run("/repo", ["status"])
    assert result == "ok"


def test_git_run_raises_giterror_on_failure(monkeypatch):
    monkeypatch.setattr(
        _git.subprocess, "run",
        lambda cmd, **k: mock.Mock(returncode=1, stdout="", stderr="bad ref"),
    )
    with pytest.raises(_git.GitError, match="bad ref"):
        _git.run("/repo", ["checkout", "nope"])


def test_gh_run_returns_stdout_on_success(monkeypatch):
    monkeypatch.setattr(
        _gh.subprocess, "run",
        lambda cmd, **k: mock.Mock(returncode=0, stdout="https://github.com/x/y/pull/1\n", stderr=""),
    )
    result = _gh.run(["pr", "create"])
    assert result == "https://github.com/x/y/pull/1"


def test_gh_run_raises_gherror_on_failure(monkeypatch):
    monkeypatch.setattr(
        _gh.subprocess, "run",
        lambda cmd, **k: mock.Mock(returncode=1, stdout="", stderr="not authenticated"),
    )
    with pytest.raises(_gh.GhError, match="not authenticated"):
        _gh.run(["pr", "create"])
