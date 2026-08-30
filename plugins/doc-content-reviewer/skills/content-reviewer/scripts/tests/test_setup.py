from __future__ import annotations
import sys
from pathlib import Path
from unittest import mock

from scripts import setup


def test_check_python_version_ok_on_311_plus():
    ok, msg = setup.check_python_version(version_info=(3, 11, 0))
    assert ok is True
    assert "3.11" in msg


def test_check_python_version_fails_below_floor():
    ok, msg = setup.check_python_version(version_info=(3, 9, 0))
    assert ok is False
    assert "3.11" in msg


def test_check_gh_auth_ok(monkeypatch):
    monkeypatch.setattr(
        setup.subprocess, "run",
        lambda *a, **k: mock.Mock(returncode=0, stdout="Logged in", stderr=""),
    )
    ok, msg = setup.check_gh_auth()
    assert ok is True


def test_check_gh_auth_fails_when_not_logged_in(monkeypatch):
    monkeypatch.setattr(
        setup.subprocess, "run",
        lambda *a, **k: mock.Mock(returncode=1, stdout="", stderr="not logged in"),
    )
    ok, msg = setup.check_gh_auth()
    assert ok is False
    assert "gh auth login" in msg


def test_check_lint_tools_detects_missing_binaries(monkeypatch, tmp_path):
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    result = setup.check_lint_tools(tmp_path)
    assert result == {"vale": False, "alex": False}


def test_check_lint_tools_false_when_binary_present_but_no_repo_config(monkeypatch, tmp_path):
    # A vale/alex binary on PATH is not enough — without a config file for
    # THIS repo, Vale would otherwise silently pick up whatever .vale.ini it
    # finds walking up from cwd (e.g. a different repo's config), or alex
    # would run with no rules at all and report false-clean. Both must be
    # treated as "not usable" until this repo has its own config.
    monkeypatch.setattr(setup.shutil, "which", lambda name: f"/usr/bin/{name}")
    result = setup.check_lint_tools(tmp_path)
    assert result == {"vale": False, "alex": False}


def test_check_lint_tools_true_when_binary_and_repo_config_present(monkeypatch, tmp_path):
    monkeypatch.setattr(setup.shutil, "which", lambda name: f"/usr/bin/{name}")
    (tmp_path / ".vale.ini").write_text("StylesPath = .github/vale\n")
    (tmp_path / ".alexrc.yaml").write_text("allow: []\n")
    result = setup.check_lint_tools(tmp_path)
    assert result == {"vale": True, "alex": True}


def test_check_lint_tools_independent_per_tool(monkeypatch, tmp_path):
    # traefik/traefik today has neither config — only hub-doc does. Each
    # tool's availability must be evaluated on its own, not as one bundled flag.
    monkeypatch.setattr(setup.shutil, "which", lambda name: f"/usr/bin/{name}")
    (tmp_path / ".vale.ini").write_text("StylesPath = .github/vale\n")
    result = setup.check_lint_tools(tmp_path)
    assert result == {"vale": True, "alex": False}


def test_check_git_status_reports_clean_tree(monkeypatch, tmp_path):
    monkeypatch.setattr(
        setup.subprocess, "run",
        lambda cmd, **k: mock.Mock(returncode=0, stdout="", stderr=""),
    )
    ok, msg = setup.check_git_status(tmp_path)
    assert ok is True
    assert "clean" in msg


def test_check_git_status_warns_on_dirty_tree(monkeypatch, tmp_path):
    monkeypatch.setattr(
        setup.subprocess, "run",
        lambda cmd, **k: mock.Mock(returncode=0, stdout=" M docs/foo.md\n", stderr=""),
    )
    ok, msg = setup.check_git_status(tmp_path)
    assert ok is False
    assert "uncommitted" in msg


def test_check_git_status_ok_when_not_a_git_repo(monkeypatch, tmp_path):
    # Not this check's job to flag "not a git repo" — repo detection (a
    # different, earlier step) surfaces that problem. This check must not
    # report a false warning here.
    monkeypatch.setattr(
        setup.subprocess, "run",
        lambda cmd, **k: mock.Mock(returncode=128, stdout="", stderr="fatal: not a git repository"),
    )
    ok, msg = setup.check_git_status(tmp_path)
    assert ok is True


def test_main_check_exits_zero_when_all_ok(monkeypatch):
    monkeypatch.setattr(setup, "check_python_version", lambda **k: (True, "ok"))
    monkeypatch.setattr(setup, "check_gh_auth", lambda: (True, "ok"))
    exit_code = setup.main(["--check"])
    assert exit_code == 0


def test_main_check_exits_nonzero_when_python_fails(monkeypatch):
    monkeypatch.setattr(setup, "check_python_version", lambda **k: (False, "need 3.11+"))
    monkeypatch.setattr(setup, "check_gh_auth", lambda: (True, "ok"))
    exit_code = setup.main(["--check"])
    assert exit_code != 0


def test_main_check_warns_but_does_not_block_on_dirty_tree(monkeypatch):
    # The git-status check is advisory — it must never turn a real,
    # otherwise-passing preflight into a blocked run.
    monkeypatch.setattr(setup, "check_python_version", lambda **k: (True, "ok"))
    monkeypatch.setattr(setup, "check_gh_auth", lambda: (True, "ok"))
    monkeypatch.setattr(
        setup, "check_git_status",
        lambda repo_root: (False, "working tree has uncommitted changes"),
    )
    exit_code = setup.main(["--check"])
    assert exit_code == 0
