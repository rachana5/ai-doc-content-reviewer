from __future__ import annotations

import json

from scripts import prepare
from scripts import profile as profile_mod


def _ctx(files, author="alice", title="feat: x", name="proxy"):
    return prepare.build_context(
        prof=profile_mod.load(name), pr="7", repo="o/r", files=files, author=author,
        title=title, base="main", head="feat")


def test_docs_pr_is_a_full_review_with_the_profile_scope():
    ctx, classify = _ctx(["docs/content/reference/a.md"])
    assert ctx["action"] == "full-review" and ctx["skip"] is False
    assert ctx["docs_changed"] == ["docs/content/reference/a.md"] and classify["action"] == "full-review"


def test_code_only_pr_runs_the_missing_docs_path():
    ctx, _ = _ctx(["pkg/middlewares/retry/retry.go"])
    assert ctx["action"] == "missing-docs-only" and ctx["user_facing_code"][0]["area"].startswith("Middleware")


def test_dependency_bot_pr_is_skipped_and_silent_even_with_docs():
    ctx, classify = _ctx(["docs/content/a.md"], author="app/renovate", title="chore(deps): bump x")
    assert ctx["skip"] is True and ctx["action"] == "silent" and classify["action"] == "silent"


def test_offline_main_writes_the_three_files(tmp_path):
    files = tmp_path / "files.txt"
    files.write_text("docs/content/reference/a.md\n")
    out = tmp_path / "out"
    rc = prepare.main(["--profile", "proxy", "--pr", "7", "--out-dir", str(out), "--files", str(files),
                       "--author", "alice", "--title", "docs: fix"])
    assert rc == 0
    assert json.loads((out / "context.json").read_text())["action"] == "full-review"
    assert json.loads((out / "changed-lines.json").read_text()) == {}
    assert (out / "classify.json").exists()


def test_resolve_base_falls_back_to_origin_and_fails_clearly(tmp_path):
    import subprocess
    from scripts import _git, prepare
    run = lambda *a, cwd=tmp_path: subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True)
    src, clone = tmp_path / "src", tmp_path / "clone"
    src.mkdir()
    run("init", "-q", "-b", "v2.11", cwd=src)
    run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "x", cwd=src)
    run("clone", "-q", str(src), str(clone))
    run("checkout", "-q", "--detach", cwd=clone)
    run("branch", "-q", "-D", "v2.11", cwd=clone)
    assert prepare.resolve_base(clone, "v2.11") == "origin/v2.11"
    import pytest
    with pytest.raises(_git.GitError, match="does not resolve"):
        prepare.resolve_base(clone, "nope")
