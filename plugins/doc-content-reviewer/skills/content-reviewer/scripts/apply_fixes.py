"""apply_fixes.py — stages confidence-gated auto-fixes as a diff, and only
writes to disk when explicitly confirmed.

`stage_all` NEVER touches the filesystem beyond reading the original files —
it computes the would-be diff in memory. Only `apply_confirmed` writes, and
it's meant to be called only after the user has seen `stage_all`'s diff and
said yes (per the plugin's standing "show diff before changes" rule).
"""
from __future__ import annotations

import argparse
import difflib
import json
from pathlib import Path

from scripts._finding import AUTO_FIX_THRESHOLD


def build_diff(original_text: str, new_text: str, filename: str) -> str:
    diff_lines = difflib.unified_diff(
        original_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True),
        fromfile=f"a/{filename}", tofile=f"b/{filename}",
    )
    return "".join(diff_lines)


def apply_finding_to_text(text: str, finding: dict) -> tuple[str, bool]:
    """Returns (new_text, applied).

    `applied` is False — and `text` is returned unchanged — when the
    finding's line index is out of range, or the line no longer contains
    the finding's quote. The doc may have been edited since the report was
    generated, or a line number may have drifted upstream; either way this
    must never silently overwrite content the quote no longer matches, and
    the caller must be able to tell a fix was skipped rather than assume it
    landed.
    """
    lines = text.splitlines(keepends=True)
    idx = finding["line"] - 1
    if not (0 <= idx < len(lines)) or finding["quote"] not in lines[idx]:
        return text, False
    # Substitute the quoted span within the line, not the whole line.
    # `quote` is very often a phrase inside a longer sentence, not the
    # entire line (e.g. a markdown link's text, or a clause mid-sentence)
    # — confirmed against real hub-doc content, where replacing the whole
    # line silently ate everything else on it (the rest of the sentence,
    # a surrounding markdown link) even though the diff-before-write gate
    # meant nothing actually landed on disk unreviewed.
    line = lines[idx]
    newline = "\n" if line.endswith("\n") else ""
    body = line[: -len(newline)] if newline else line
    lines[idx] = body.replace(finding["quote"], finding["suggested_fix"]) + newline
    return "".join(lines), True


def _fixable(findings: list[dict]) -> list[dict]:
    return [f for f in findings if f.get("auto_fixable") and f["confidence"] >= AUTO_FIX_THRESHOLD]


def _apply_all_to_file(file_findings: list[dict], original: str, file_path: str) -> str:
    """Applies every fixable finding for one file, printing a warning (never
    a silent no-op) for any finding whose quote no longer matches.

    Findings are applied bottom-up (highest line number first), not in
    reading order. If a suggested_fix spans multiple lines (e.g. a clarity
    rewrite that splits one long line into two), applying top-down would
    shift every later line's index by the time its finding is processed —
    apply_finding_to_text would then look for that finding's quote at the
    wrong (stale) index and skip it, one silent-looking failure per finding
    below the expansion. Processing highest-line-first means an earlier
    finding's expansion only ever shifts indices for lines that have
    already been handled, never ones still pending.

    Returns the resulting text — identical to `original` if nothing could
    be applied."""
    text = original
    for finding in sorted(file_findings, key=lambda f: f["line"], reverse=True):
        text, applied = apply_finding_to_text(text, finding)
        if not applied:
            print(
                f"[apply_fixes] WARNING: skipped finding at {file_path}:{finding['line']} "
                f"— quote no longer matches that line (doc may have changed since "
                f"the report was generated)"
            )
    return text


def stage_all(findings: list[dict], repo_root: Path) -> str:
    fixable = _fixable(findings)
    by_file: dict[str, list[dict]] = {}
    for f in fixable:
        by_file.setdefault(f["file"], []).append(f)

    diffs = []
    for file_path, file_findings in by_file.items():
        path = Path(file_path)
        original = path.read_text()
        new_text = _apply_all_to_file(file_findings, original, file_path)
        if new_text != original:
            diffs.append(build_diff(original, new_text, path.name))
    return "".join(diffs)


def apply_confirmed(findings: list[dict], repo_root: Path) -> list[str]:
    fixable = _fixable(findings)
    by_file: dict[str, list[dict]] = {}
    for f in fixable:
        by_file.setdefault(f["file"], []).append(f)

    modified = []
    for file_path, file_findings in by_file.items():
        path = Path(file_path)
        original = path.read_text()
        new_text = _apply_all_to_file(file_findings, original, file_path)
        if new_text != original:
            path.write_text(new_text)
            modified.append(file_path)
    return modified


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--findings", required=True, help="path to merged findings JSON")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--apply", action="store_true", help="write files instead of just staging a diff")
    args = parser.parse_args(argv)

    findings = json.loads(Path(args.findings).read_text())
    repo_root = Path(args.repo_root)

    if args.apply:
        modified = apply_confirmed(findings, repo_root)
        print(json.dumps({"modified": modified}))
    else:
        print(stage_all(findings, repo_root))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
