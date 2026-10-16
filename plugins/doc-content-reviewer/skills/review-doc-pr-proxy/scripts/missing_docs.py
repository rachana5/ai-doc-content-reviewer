"""missing_docs.py — classify a PR's changed files for the two review paths.

Input: the PR's changed file names and a product profile. Output (JSON):

  docs_changed        doc files in the PR (profile docs_root + extensions)
  user_facing_code    code files that match a profile rule, each with the doc
                      area it maps to
  run_content_review  True when the PR changes docs
  run_missing_docs    True when user-facing code changed (whether or not docs
                      did; the agent then judges whether the PR's docs cover it)
  generated_touched   generated files edited by hand (should be regenerated)
  action              "full-review" | "missing-docs-only" | "silent"

This script only maps and filters. Whether docs are actually needed, and what
to write, is the agent's judgment (references/missing-docs-checklist.md).
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys

from scripts import profile as profile_mod


def classify(files: list[str], prof: dict) -> dict:
    docs_root = prof["docs_root"]
    exts = tuple(prof.get("doc_extensions", [".md"]))
    exclude = [re.compile(p) for p in prof.get("exclude_code", [])]
    generated = prof.get("generated_files", [])

    docs_changed = [f for f in files if f.startswith(docs_root) and f.endswith(exts)]
    generated_touched = [
        f for f in files if any(fnmatch.fnmatch(f, g) for g in generated)
    ]

    user_facing = []
    for f in files:
        if f.startswith(docs_root) or any(x.search(f) for x in exclude):
            continue
        for rule in prof.get("user_facing_code", []):
            m = re.search(rule["pattern"], f)
            if not m:
                continue
            aliases = prof.get("doc_aliases", {})
            groups = [aliases.get(g, g) for g in m.groups()]
            targets = [re.sub(r"\\(\d)", lambda n: groups[int(n.group(1)) - 1], d)
                       for d in rule["docs"]]
            entry = {"file": f, "area": rule["area"], "doc_targets": targets}
            if "also" in rule:
                entry["note"] = rule["also"]
            user_facing.append(entry)
            break  # first matching rule wins; list specific rules first

    run_content = bool(docs_changed)
    run_missing = bool(user_facing)
    action = (
        "full-review" if run_content
        else "missing-docs-only" if run_missing
        else "silent"
    )
    return {
        "docs_changed": docs_changed,
        "user_facing_code": user_facing,
        "generated_touched": generated_touched,
        "run_content_review": run_content,
        "run_missing_docs": run_missing,
        "action": action,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--profile", required=True, help="profile name or path")
    ap.add_argument("--files", help="file with one changed path per line (default: stdin)")
    args = ap.parse_args(argv)
    text = open(args.files).read() if args.files else sys.stdin.read()
    files = [l.strip() for l in text.splitlines() if l.strip()]
    print(json.dumps(classify(files, profile_mod.load(args.profile)), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
