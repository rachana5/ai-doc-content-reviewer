"""_finding.py — the shared finding schema every review layer emits.

See references/finding-schema.md for the human-readable version of this
contract (loaded by SKILL.md when instructing each layer's agent pass).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

VALID_LAYERS = {"accuracy", "style", "reference", "clarity", "completeness"}
VALID_SEVERITIES = {"blocking", "suggestion"}
AUTO_FIX_THRESHOLD = 0.8

REQUIRED_KEYS = {
    "layer", "file", "line", "quote", "reasoning",
    "suggested_fix", "severity", "confidence", "auto_fixable",
}


def make_finding(
    *, layer: str, file: str, line: int, quote: str, reasoning: str,
    suggested_fix: str, severity: str, confidence: float,
    auto_fixable: bool | None = None,
) -> dict:
    if layer not in VALID_LAYERS:
        raise ValueError(f"unknown layer: {layer!r} (must be one of {VALID_LAYERS})")
    if severity not in VALID_SEVERITIES:
        raise ValueError(f"unknown severity: {severity!r} (must be one of {VALID_SEVERITIES})")
    if auto_fixable is None:
        auto_fixable = confidence >= AUTO_FIX_THRESHOLD
    return {
        "layer": layer, "file": file, "line": line, "quote": quote,
        "reasoning": reasoning, "suggested_fix": suggested_fix,
        "severity": severity, "confidence": confidence, "auto_fixable": auto_fixable,
    }


def validate_finding(finding: dict) -> list[str]:
    errors: list[str] = []
    missing = REQUIRED_KEYS - finding.keys()
    for key in sorted(missing):
        errors.append(f"missing required key: {key}")
    if "layer" in finding and finding["layer"] not in VALID_LAYERS:
        errors.append(f"invalid layer: {finding['layer']!r}")
    if "severity" in finding and finding["severity"] not in VALID_SEVERITIES:
        errors.append(f"invalid severity: {finding['severity']!r}")
    if "confidence" in finding:
        c = finding["confidence"]
        if not isinstance(c, (int, float)) or not (0.0 <= c <= 1.0):
            errors.append(f"confidence must be a number in [0, 1], got {c!r}")
    # finding-schema.md: "auto_fixable: true only when confidence >= 0.8".
    # make_finding() derives this automatically when auto_fixable isn't
    # passed explicitly, but hand-authored findings (accuracy/clarity/
    # completeness write JSON directly, not through make_finding()) can set
    # both fields independently -- nothing upstream of this validator
    # stops a low-confidence finding from claiming auto_fixable: true.
    if (
        finding.get("auto_fixable") is True
        and isinstance(finding.get("confidence"), (int, float))
        and finding["confidence"] < AUTO_FIX_THRESHOLD
    ):
        errors.append(
            f"auto_fixable is true but confidence ({finding['confidence']!r}) "
            f"is below AUTO_FIX_THRESHOLD ({AUTO_FIX_THRESHOLD})"
        )
    # SKILL.md's completeness step: "every finding's severity is suggestion
    # and auto_fixable is false" -- there's no ground truth to confirm a
    # completeness finding against, only a repo convention or a plausible
    # reader question, so it must never be treated as a mechanically-safe
    # auto-apply the way a high-confidence accuracy fix can be.
    if finding.get("layer") == "completeness":
        if "severity" in finding and finding["severity"] != "suggestion":
            errors.append(
                f"completeness findings must have severity 'suggestion', got {finding['severity']!r}"
            )
        if "auto_fixable" in finding and finding["auto_fixable"] is not False:
            errors.append(
                f"completeness findings must have auto_fixable false, got {finding['auto_fixable']!r}"
            )
    return errors


def main(argv: list[str] | None = None) -> int:
    """Validate a JSON file containing a list of findings.

    This is the concrete step behind "every finding must validate before
    moving on" in SKILL.md: each layer (accuracy/clarity always, style/
    reference for their judgment half) writes its findings as one JSON file
    — e.g. accuracy.json — and this CLI is run against that file before it's
    passed to aggregate.py. A malformed hand-authored finding fails loudly
    here, at the layer boundary, instead of breaking aggregation silently or
    producing a confusing downstream error.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("findings_file")
    args = parser.parse_args(argv)

    findings = json.loads(Path(args.findings_file).read_text())
    if not isinstance(findings, list):
        print(f"[_finding] ERROR: {args.findings_file} must contain a JSON list of findings")
        return 1

    all_errors: list[str] = []
    for i, finding in enumerate(findings):
        for error in validate_finding(finding):
            all_errors.append(f"finding[{i}]: {error}")

    if all_errors:
        print(f"[_finding] INVALID — {len(all_errors)} error(s) in {args.findings_file}:")
        for error in all_errors:
            print(f"  - {error}")
        return 1

    print(f"[_finding] OK — {len(findings)} finding(s) in {args.findings_file} all valid")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
