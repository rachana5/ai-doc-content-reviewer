from __future__ import annotations
from unittest import mock
import subprocess

import pytest

from scripts import _git


def test_run_returns_stdout_on_success(monkeypatch):
    monkeypatch.setattr(
        _git.subprocess, "run",
        lambda cmd, **k: mock.Mock(returncode=0, stdout="ok\n", stderr=""),
    )
    assert _git.run("/repo", ["status"]) == "ok"


def test_run_raises_giterror_on_failure(monkeypatch):
    monkeypatch.setattr(
        _git.subprocess, "run",
        lambda cmd, **k: mock.Mock(returncode=1, stdout="", stderr="bad ref"),
    )
    with pytest.raises(_git.GitError, match="bad ref"):
        _git.run("/repo", ["checkout", "nope"])


def test_run_pins_an_explicit_encoding_instead_of_the_locale_default(monkeypatch):
    # A C-locale CI box would otherwise decode non-ASCII git output (accented
    # names, smart quotes, emoji in doc content) via ASCII, raising a raw
    # UnicodeDecodeError instead of the clean GitError this wrapper exists
    # to produce.
    captured = {}

    def fake_run(cmd, **kwargs):
        captured.update(kwargs)
        return mock.Mock(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(_git.subprocess, "run", fake_run)
    _git.run("/repo", ["status"])
    assert captured["encoding"] == "utf-8"


def test_run_passes_a_timeout(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured.update(kwargs)
        return mock.Mock(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(_git.subprocess, "run", fake_run)
    _git.run("/repo", ["status"])
    assert captured["timeout"] == _git._TIMEOUT_SECONDS


def test_run_converts_a_timeout_expiry_into_giterror(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(_git.subprocess, "run", fake_run)
    with pytest.raises(_git.GitError, match="timed out"):
        _git.run("/repo", ["fetch"])


def test_run_converts_a_missing_git_binary_into_giterror(monkeypatch):
    # A CI image that never installed git raises FileNotFoundError (an
    # OSError subclass) before subprocess.run produces any CompletedProcess
    # at all -- confirmed directly against a real PATH with git's directory
    # stripped out, not just mocked here.
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "git")

    monkeypatch.setattr(_git.subprocess, "run", fake_run)
    with pytest.raises(_git.GitError, match="could not run git"):
        _git.run("/repo", ["status"])


def test_run_converts_undecodable_output_into_giterror(monkeypatch):
    # git's output can contain bytes that aren't valid utf-8 (e.g. leaking
    # through a binary file's diff) -- subprocess.run raises this from
    # inside its own decode step, before returncode is ever checked.
    def fake_run(cmd, **kwargs):
        raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

    monkeypatch.setattr(_git.subprocess, "run", fake_run)
    with pytest.raises(_git.GitError, match="isn't valid utf-8"):
        _git.run("/repo", ["log"])
