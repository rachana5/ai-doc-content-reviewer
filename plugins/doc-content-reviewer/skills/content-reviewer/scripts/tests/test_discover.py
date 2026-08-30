from __future__ import annotations
import json

from scripts import _discover, _git


def test_is_traefik_hub_clone_true_for_matching_origin(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(_discover._git, "run", lambda repo, args: "git@github.com:traefik/traefik-hub.git")
    assert _discover._is_traefik_hub_clone(tmp_path) is True


def test_is_traefik_hub_clone_false_for_non_matching_origin(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(_discover._git, "run", lambda repo, args: "git@github.com:someone/other-repo.git")
    assert _discover._is_traefik_hub_clone(tmp_path) is False


def test_is_traefik_hub_clone_false_when_not_a_git_repo(tmp_path):
    assert _discover._is_traefik_hub_clone(tmp_path) is False


def test_discover_traefik_hub_prefers_env_var(tmp_path, monkeypatch):
    clone = tmp_path / "my-clone"
    clone.mkdir()
    monkeypatch.setattr(_discover, "_is_traefik_hub_clone", lambda path: path == clone.resolve())
    result = _discover.discover_traefik_hub(env={"TRAEFIK_HUB_PATH": str(clone)})
    assert result == str(clone.resolve())


def test_discover_traefik_hub_falls_back_to_persisted_config(tmp_path, monkeypatch):
    clone = tmp_path / "saved-clone"
    clone.mkdir()
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"traefik_hub_path": str(clone)}))
    monkeypatch.setattr(_discover, "CONFIG_PATH", config_path)
    monkeypatch.setattr(_discover, "_is_traefik_hub_clone", lambda path: path == clone.resolve())
    result = _discover.discover_traefik_hub(env={})
    assert result == str(clone.resolve())


def test_discover_traefik_hub_falls_back_to_sibling_dir(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    (workspace / "hub-doc").mkdir(parents=True)
    sibling_clone = workspace / "traefik-hub"
    sibling_clone.mkdir()
    monkeypatch.setattr(_discover, "CONFIG_PATH", tmp_path / "no-config.json")
    monkeypatch.setattr(_discover, "_is_traefik_hub_clone", lambda path: path == sibling_clone.resolve())
    result = _discover.discover_traefik_hub(cwd=str(workspace / "hub-doc"), env={})
    assert result == str(sibling_clone.resolve())


def test_discover_traefik_hub_returns_none_when_nothing_matches(tmp_path, monkeypatch):
    monkeypatch.setattr(_discover, "CONFIG_PATH", tmp_path / "no-config.json")
    monkeypatch.setattr(_discover, "COMMON_PARENTS", [])
    monkeypatch.setattr(_discover, "_is_traefik_hub_clone", lambda path: False)
    result = _discover.discover_traefik_hub(cwd=str(tmp_path), env={})
    assert result is None


def test_persist_traefik_hub_writes_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(_discover, "CONFIG_PATH", config_path)
    clone = tmp_path / "my-clone"
    clone.mkdir()
    _discover.persist_traefik_hub(str(clone))
    saved = json.loads(config_path.read_text())
    assert saved["traefik_hub_path"] == str(clone.resolve())


def test_discover_repo_root_returns_git_toplevel(monkeypatch):
    monkeypatch.setattr(_discover._git, "run", lambda repo, args: "/repo/root\n")
    result = _discover.discover_repo_root(cwd="/repo/root/subdir")
    assert result == "/repo/root"


def test_discover_repo_root_returns_none_when_not_a_git_repo(monkeypatch):
    def _raise(repo, args):
        raise _git.GitError("not a git repository")
    monkeypatch.setattr(_discover._git, "run", _raise)
    result = _discover.discover_repo_root(cwd="/not/a/repo")
    assert result is None


def test_main_traefik_hub_not_found_exits_2(monkeypatch):
    monkeypatch.setattr(_discover, "discover_traefik_hub", lambda: None)
    exit_code = _discover.main(["traefik-hub"])
    assert exit_code == 2


def test_main_repo_root_prints_path(monkeypatch, capsys):
    monkeypatch.setattr(_discover, "discover_repo_root", lambda: "/repo/root")
    exit_code = _discover.main(["repo-root"])
    assert exit_code == 0
    assert capsys.readouterr().out.strip() == "/repo/root"


def test_main_save_traefik_hub_persists(tmp_path, monkeypatch):
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(_discover, "CONFIG_PATH", config_path)
    clone = tmp_path / "my-clone"
    clone.mkdir()
    exit_code = _discover.main(["save-traefik-hub", str(clone)])
    assert exit_code == 0
    assert json.loads(config_path.read_text())["traefik_hub_path"] == str(clone.resolve())
