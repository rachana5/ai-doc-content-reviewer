from __future__ import annotations
from unittest import mock
import subprocess

import pytest

from scripts import _gh


def test_run_returns_stdout_on_success(monkeypatch):
    monkeypatch.setattr(
        _gh.subprocess, "run",
        lambda cmd, **k: mock.Mock(returncode=0, stdout="ok\n", stderr=""),
    )
    assert _gh.run(["pr", "view"]) == "ok"


def test_run_raises_gherror_on_failure(monkeypatch):
    monkeypatch.setattr(
        _gh.subprocess, "run",
        lambda cmd, **k: mock.Mock(returncode=1, stdout="", stderr="not found"),
    )
    with pytest.raises(_gh.GhError, match="not found"):
        _gh.run(["pr", "view", "999999"])


def test_run_passes_a_timeout(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured.update(kwargs)
        return mock.Mock(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(_gh.subprocess, "run", fake_run)
    _gh.run(["pr", "view"])
    assert captured["timeout"] == _gh._TIMEOUT_SECONDS


def test_run_converts_a_timeout_expiry_into_gherror(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout"))

    monkeypatch.setattr(_gh.subprocess, "run", fake_run)
    with pytest.raises(_gh.GhError, match="timed out"):
        _gh.run(["pr", "comment"])


def test_run_converts_a_missing_gh_binary_into_gherror(monkeypatch):
    # A CI image that never installed gh raises FileNotFoundError (an
    # OSError subclass) before subprocess.run produces any CompletedProcess
    # at all -- same class of gap _git.py is already hardened against.
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", "gh")

    monkeypatch.setattr(_gh.subprocess, "run", fake_run)
    with pytest.raises(_gh.GhError, match="could not run gh"):
        _gh.run(["pr", "view"])
