"""run_style_lint.py — style layer, mechanical part.

Runs Vale and alex (if present on PATH) against target files and translates
their output into the shared finding schema. Missing tools degrade gracefully
— the style layer's agent-judgment pass still runs on the qualitative parts
of style-guide.md; this just means the report notes the mechanical check
didn't run rather than silently reporting zero findings as "clean."
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from scripts._finding import make_finding
from scripts.setup import check_lint_tools


def parse_vale_json(raw_json: str, *, file: str) -> list[dict]:
    data = json.loads(raw_json)
    findings = []
    for _, alerts in data.items():
        for alert in alerts:
            findings.append(make_finding(
                layer="style", file=file, line=alert["Line"],
                quote=alert.get("Match", ""),
                reasoning=f"[{alert.get('CheckID', 'vale')}] {alert['Message']}",
                suggested_fix="(see reasoning — Vale flags, doesn't rewrite)",
                severity="blocking" if alert.get("Severity") == "error" else "suggestion",
                confidence=0.85,
                # Vale flags a violation but never emits real replacement
                # text — never eligible for auto-fix regardless of confidence.
                auto_fixable=False,
            ))
    return findings


def parse_alex_json(raw_json: str, *, file: str) -> list[dict]:
    data = json.loads(raw_json)
    findings = []
    for entry in data:
        for message in entry.get("messages", []):
            findings.append(make_finding(
                layer="style", file=file, line=message["line"],
                quote=message.get("reason", ""),
                reasoning=message["message"],
                suggested_fix="(see reasoning — alex flags, doesn't rewrite)",
                severity="suggestion", confidence=0.85,
                # Same reasoning as parse_vale_json above — alex flags, it
                # doesn't rewrite, so this can never be auto-applied.
                auto_fixable=False,
            ))
    return findings


def run(target_files: list[Path], repo_root: Path) -> dict:
    tools = check_lint_tools(repo_root)
    findings: list[dict] = []

    if tools["vale"]:
        for file in target_files:
            try:
                result = subprocess.run(
                    ["vale", "--output=JSON", str(file)], capture_output=True, text=True,
                )
                if result.stdout.strip():
                    findings.extend(parse_vale_json(result.stdout, file=str(file)))
            except (subprocess.SubprocessError, OSError, json.JSONDecodeError) as exc:
                print(f"[run_style_lint] WARNING: vale failed on {file} ({exc!r}) — skipping this file for vale, continuing")

    if tools["alex"]:
        for file in target_files:
            try:
                result = subprocess.run(
                    ["alex", "--json", str(file)], capture_output=True, text=True,
                )
                if result.stdout.strip():
                    findings.extend(parse_alex_json(result.stdout, file=str(file)))
            except (subprocess.SubprocessError, OSError, json.JSONDecodeError) as exc:
                print(f"[run_style_lint] WARNING: alex failed on {file} ({exc!r}) — skipping this file for alex, continuing")

    return {"findings": findings, "vale_ran": tools["vale"], "alex_ran": tools["alex"]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+")
    parser.add_argument("--repo-root", required=True)
    args = parser.parse_args(argv)
    result = run([Path(f) for f in args.files], Path(args.repo_root))
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
