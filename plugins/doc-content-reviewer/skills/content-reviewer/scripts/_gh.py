"""_gh.py — thin subprocess wrapper around the `gh` CLI."""
from __future__ import annotations
import subprocess

# Without a timeout, a stalled `gh` invocation (the GitHub API hanging, or
# `gh` itself blocking on interactive re-auth in a non-interactive CI
# environment) blocks forever instead of failing fast -- this is the
# only network-writing call site in review-doc-pr's unattended CI run
# (post_review.py posts the PR comment through here), so a hang here wedges
# the whole job rather than surfacing as a reported error.
_TIMEOUT_SECONDS = 30


class GhError(RuntimeError):
    pass


def run(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as e:
        raise GhError(f"gh {args} timed out after {_TIMEOUT_SECONDS}s") from e
    except OSError as e:
        # A missing gh binary (FileNotFoundError, e.g. a CI image that
        # never installed it) and other OS-level launch failures never
        # reach the returncode check below -- subprocess.run didn't get
        # far enough to produce a CompletedProcess at all. Same class of
        # gap _git.py is already hardened against.
        raise GhError(f"could not run gh {args}: {e}") from e
    if result.returncode != 0:
        raise GhError(result.stderr.strip() or f"gh {args} failed")
    return result.stdout.strip()
