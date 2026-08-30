from __future__ import annotations
from pathlib import Path
from unittest import mock

from scripts._finding import make_finding
from scripts import check_links, aggregate, apply_fixes

FIXTURES = Path(__file__).parent / "fixtures"


def test_full_pipeline_reference_layer_through_report_and_stage(tmp_path):
    # Set up a doc file with one broken internal link and one accurate line.
    doc = tmp_path / "retry.md"
    doc.write_text(
        "The default value for maxRetries is 3.\n"
        "See [related](./missing-page.md) for more.\n"
    )

    # Reference layer (mechanical, real): should find the broken link.
    with mock.patch.object(check_links, "_http_head", return_value=mock.Mock(status=200)):
        reference_findings = check_links.run([doc], tmp_path)
    assert len(reference_findings) == 1
    assert reference_findings[0]["layer"] == "reference"

    # Accuracy layer (agent-judgment in production; fixture stand-in here):
    # simulates what the accuracy layer would emit after reading sample_source.go
    # and finding DefaultMaxRetries = 5 contradicts the doc's "3".
    accuracy_findings = [make_finding(
        layer="accuracy", file=str(doc), line=1,
        quote="The default value for maxRetries is 3.",
        reasoning="sample_source.go sets DefaultMaxRetries = 5, not 3.",
        suggested_fix="The default value for maxRetries is 5.",
        severity="blocking", confidence=0.9,
    )]

    # Aggregate both layers. Note: reference_findings[0] already carries
    # auto_fixable=False from check_links.py itself (a broken link has no
    # machine-safe replacement text, regardless of how high its confidence
    # is — see check_links.py's _NO_SAFE_AUTOFIX). No manual override needed
    # here; this is exercising the real behavior, not working around it.
    merged = aggregate.aggregate({
        "accuracy": accuracy_findings, "reference": reference_findings,
        "style": [], "clarity": [],
    })
    assert len(merged) == 2
    assert reference_findings[0]["auto_fixable"] is False

    report_template = (
        Path(__file__).parent.parent.parent / "templates" / "review-report.md.tmpl"
    ).read_text()
    report = aggregate.render_report(merged, report_template)
    assert "maxRetries is 3" in report
    assert "missing-page.md" in report

    # Stage fixes: only the high-confidence accuracy finding is auto-fixable;
    # the reference finding is excluded because it's not auto_fixable, not
    # because of a low confidence score.
    diff = apply_fixes.stage_all(merged, tmp_path)
    assert "maxRetries is 5" in diff
    # non-auto-fixable finding never staged: its suggested_fix text should not appear
    assert "(needs a human" not in diff
    # Disk must still be untouched at this point.
    assert "maxRetries is 3" in doc.read_text()

    # Only after "confirmation" does anything get written.
    modified = apply_fixes.apply_confirmed(merged, tmp_path)
    assert modified == [str(doc)]
    assert "maxRetries is 5" in doc.read_text()
