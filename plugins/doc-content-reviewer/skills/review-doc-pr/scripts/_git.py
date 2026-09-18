"""_git.py — thin subprocess wrapper around `git -C <repo_path> ...`."""
from __future__ import annotations
import subprocess

# A CI runner with a C locale (LANG=C / no locale configured, common on
# minimal container images) makes Python's text-mode subprocess decode
# via ASCII instead of UTF-8 — a raw UnicodeDecodeError on any non-ASCII
# byte in git's output (entirely plausible: doc content routinely has
# accented names, smart quotes, emoji) instead of the clean GitError this
# wrapper exists to produce. Pinning the encoding removes the dependence
# on the calling environment's locale entirely.
_ENCODING = "utf-8"

# Without a timeout, a stalled git invocation (a hung network fetch behind
# --unified=0's implicit history walk, a wedged credential helper) blocks
# forever instead of failing fast — turning one bad call into a hung CI
# job rather than a reported error.
_TIMEOUT_SECONDS = 30


class GitError(RuntimeError):
    pass


def run(repo_path: str, args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, *args],
            capture_output=True, text=True, encoding=_ENCODING, timeout=_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as e:
        raise GitError(f"git {args} timed out after {_TIMEOUT_SECONDS}s") from e
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or f"git {args} failed")
    return result.stdout.strip()
