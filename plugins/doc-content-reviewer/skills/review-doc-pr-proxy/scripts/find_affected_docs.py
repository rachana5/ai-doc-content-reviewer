"""find_affected_docs.py: find every doc page that mentions what a PR changed.

Input: terms (identifiers the PR changes: an option or field name, a middleware,
a flag, a renamed or removed term, a changed default's option) and a product
profile. Output (JSON): each doc page under the profile's docs root that mentions
a term, with the matching lines, flagged `in_pr` when the PR already edits it and
`generated` when it is a generated file.

This only finds candidates. Whether a mention is now wrong, incomplete, or still
fine is the agent's judgment (references/affected-docs-checklist.md). The search
covers the whole docs tree on purpose: the page a contributor forgot (a reference
table, a migration note, a sibling guide) is exactly the one the PR did not touch.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path

from scripts import profile as profile_mod

MIN_TERM_LEN = 3        # shorter terms match too much to mean anything
MAX_HITS_PER_FILE = 15
MAX_FILES = 40


def find_affected(
    repo_root: Path, prof: dict, terms: list[str], docs_changed: list[str],
    seeds: list[str] | None = None,
) -> dict:
    terms = sorted({t.strip() for t in terms if len(t.strip()) >= MIN_TERM_LEN})
    patterns = {t: re.compile(rf"(?<![A-Za-z0-9_]){re.escape(t)}(?![A-Za-z0-9_])") for t in terms}
    exts = tuple(prof.get("doc_extensions", [".md"]))
    generated = prof.get("generated_files", [])
    in_pr = set(docs_changed)
    docs_root = repo_root / prof["docs_root"]

    files = []
    for path in sorted(docs_root.rglob("*")):
        if not path.is_file() or not path.name.endswith(exts):
            continue
        rel = path.relative_to(repo_root).as_posix()
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        hits = []
        for n, text in enumerate(lines, start=1):
            for term, pat in patterns.items():
                if pat.search(text):
                    hits.append({"line": n, "term": term, "text": text.strip()[:200]})
        if hits:
            files.append({
                "file": rel,
                "in_pr": rel in in_pr,
                "generated": any(fnmatch.fnmatch(rel, g) for g in generated),
                "seed": any(rel == s or rel.startswith(s) for s in (seeds or [])),
                "hit_count": len(hits),
                "hits": hits[:MAX_HITS_PER_FILE],
            })
    # Pages the PR does not touch first (the point of this search), seeds before the rest,
    # then by how many mentions, so the cap drops the weakest candidates.
    files.sort(key=lambda f: (f["in_pr"], not f["seed"], -f["hit_count"], f["file"]))
    truncated = len(files) > MAX_FILES
    return {"terms": terms, "files": files[:MAX_FILES], "truncated": truncated}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--profile", required=True)
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--terms", required=True, help="comma-separated identifiers the PR changes")
    ap.add_argument("--classify", help="classify.json: supplies docs_changed and the profile's doc_targets as seeds")
    args = ap.parse_args(argv)

    docs_changed, seeds = [], []
    if args.classify:
        c = json.loads(Path(args.classify).read_text())
        docs_changed = c.get("docs_changed", [])
        seeds = [t for e in c.get("user_facing_code", []) for t in e.get("doc_targets", [])]
    result = find_affected(
        Path(args.repo_root), profile_mod.load(args.profile),
        args.terms.split(","), docs_changed, seeds,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
