"""aggregate.py — merges the four layers' findings into one sorted, deduped
list, then renders the review report.

Dedup key is (file, line, quote): two layers flagging the same location collapse
into one entry that lists both layers, rather than the reader seeing the
same sentence flagged twice. Sort is by location, not by layer, because
that's how a diff actually reads.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def dedup_findings(findings: list[dict]) -> list[dict]:
    # Key on (file, line, quote), not just (file, line): dense markdown
    # (table rows, long single-line paragraphs) can put two UNRELATED
    # findings on the same line. Merging on location alone would silently
    # drop the lower-confidence finding's own reasoning/suggested_fix while
    # its layer name stayed listed as if it agreed with the other finding.
    # Requiring the quote to match too means two layers only merge when
    # they're actually describing the same text.
    by_location: dict[tuple[str, int, str], dict] = {}
    for finding in findings:
        key = (finding["file"], finding["line"], finding["quote"])
        if key not in by_location:
            merged = dict(finding)
            merged["layers"] = [finding["layer"]]
            by_location[key] = merged
        else:
            existing = by_location[key]
            if finding["layer"] not in existing["layers"]:
                existing["layers"].append(finding["layer"])
            # Keep the higher-confidence reasoning/suggested_fix when merging.
            if finding["confidence"] > existing["confidence"]:
                existing["reasoning"] = finding["reasoning"]
                existing["suggested_fix"] = finding["suggested_fix"]
                existing["confidence"] = finding["confidence"]
    return list(by_location.values())


def sort_findings(findings: list[dict]) -> list[dict]:
    return sorted(findings, key=lambda f: (f["file"], f["line"]))


def assign_ids(findings: list[dict]) -> list[dict]:
    """Assigns a stable, sequential 1-based id to each finding, in the given
    order. Findings otherwise have no unique identifier, and the fix-review
    step (SKILL.md Step 5) needs one so a user can approve a subset by
    number ("apply 2 and 4") instead of all-or-nothing."""
    for i, finding in enumerate(findings, start=1):
        finding["id"] = i
    return findings


def aggregate(layer_findings: dict[str, list[dict]]) -> list[dict]:
    all_findings = [f for findings in layer_findings.values() for f in findings]
    return assign_ids(sort_findings(dedup_findings(all_findings)))


def render_report(findings: list[dict], template_text: str) -> str:
    """Minimal mustache-ish renderer: expands a single {{#findings}}...{{/findings}}
    block once per finding, substituting {{key}} placeholders. Enough for this
    plugin's fixed report shape — not a general templating engine."""
    match = re.search(r"\{\{#findings\}\}(.*?)\{\{/findings\}\}", template_text, re.DOTALL)
    if not match:
        return template_text
    row_template = match.group(1)
    rows = []
    for finding in findings:
        row = row_template
        row = row.replace("{{layers}}", ", ".join(finding.get("layers", [finding["layer"]])))
        for key, value in finding.items():
            row = row.replace("{{" + key + "}}", str(value))
        rows.append(row)
    return template_text[:match.start()] + "".join(rows) + template_text[match.end():]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--accuracy", default=None)
    parser.add_argument("--style", default=None)
    parser.add_argument("--reference", default=None)
    parser.add_argument("--clarity", default=None)
    parser.add_argument("--template", required=True)
    parser.add_argument("--out", required=True, help="path to write merged findings JSON")
    args = parser.parse_args(argv)

    def _load(path: str | None) -> list[dict]:
        if not path:
            return []
        return json.loads(Path(path).read_text())

    layer_findings = {
        "accuracy": _load(args.accuracy), "style": _load(args.style),
        "reference": _load(args.reference), "clarity": _load(args.clarity),
    }
    merged = aggregate(layer_findings)
    Path(args.out).write_text(json.dumps(merged))
    template_text = Path(args.template).read_text()
    print(render_report(merged, template_text))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
