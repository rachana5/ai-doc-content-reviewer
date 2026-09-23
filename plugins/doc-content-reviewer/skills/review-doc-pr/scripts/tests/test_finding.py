from __future__ import annotations
import json
import pytest
from scripts import _finding
from scripts._finding import make_finding, validate_finding, AUTO_FIX_THRESHOLD


def test_make_finding_builds_expected_shape():
    f = make_finding(
        layer="accuracy", file="docs/foo.md", line=42,
        quote="The default is 3.", reasoning="Source says 5.",
        suggested_fix="The default is 5.", severity="blocking", confidence=0.9,
    )
    assert f == {
        "layer": "accuracy", "file": "docs/foo.md", "line": 42,
        "quote": "The default is 3.", "reasoning": "Source says 5.",
        "suggested_fix": "The default is 5.", "severity": "blocking",
        "confidence": 0.9, "auto_fixable": True,
    }


def test_make_finding_auto_fixable_false_below_threshold():
    f = make_finding(
        layer="clarity", file="docs/foo.md", line=1, quote="q", reasoning="r",
        suggested_fix="s", severity="suggestion", confidence=AUTO_FIX_THRESHOLD - 0.01,
    )
    assert f["auto_fixable"] is False


def test_make_finding_explicit_auto_fixable_overrides_confidence():
    f = make_finding(
        layer="style", file="docs/foo.md", line=1, quote="q", reasoning="r",
        suggested_fix="s", severity="suggestion", confidence=0.99, auto_fixable=False,
    )
    assert f["auto_fixable"] is False


def test_make_finding_rejects_unknown_layer():
    with pytest.raises(ValueError, match="layer"):
        make_finding(
            layer="nonsense", file="f.md", line=1, quote="q", reasoning="r",
            suggested_fix="s", severity="blocking", confidence=0.5,
        )


def test_make_finding_rejects_unknown_severity():
    with pytest.raises(ValueError, match="severity"):
        make_finding(
            layer="accuracy", file="f.md", line=1, quote="q", reasoning="r",
            suggested_fix="s", severity="nonsense", confidence=0.5,
        )


def test_validate_finding_passes_for_well_formed_dict():
    f = make_finding(
        layer="reference", file="f.md", line=1, quote="q", reasoning="r",
        suggested_fix="s", severity="suggestion", confidence=0.5,
    )
    assert validate_finding(f) == []


def test_validate_finding_reports_missing_keys():
    errors = validate_finding({"layer": "accuracy"})
    assert any("file" in e for e in errors)
    assert any("confidence" in e for e in errors)


def test_validate_finding_reports_bad_confidence_range():
    f = make_finding(
        layer="accuracy", file="f.md", line=1, quote="q", reasoning="r",
        suggested_fix="s", severity="blocking", confidence=0.5,
    )
    f["confidence"] = 1.5
    errors = validate_finding(f)
    assert any("confidence" in e for e in errors)


def test_validate_finding_reports_auto_fixable_true_below_threshold():
    # finding-schema.md: "auto_fixable: true only when confidence >= 0.8".
    # Hand-authored findings (accuracy/clarity/completeness write JSON
    # directly, not through make_finding()) can set both fields
    # independently of each other -- nothing upstream stops this.
    f = make_finding(
        layer="accuracy", file="f.md", line=1, quote="q", reasoning="r",
        suggested_fix="s", severity="blocking", confidence=0.3,
        auto_fixable=True,
    )
    errors = validate_finding(f)
    assert any("auto_fixable" in e and "confidence" in e for e in errors)


def test_validate_finding_allows_auto_fixable_false_regardless_of_confidence():
    f = make_finding(
        layer="accuracy", file="f.md", line=1, quote="q", reasoning="r",
        suggested_fix="s", severity="blocking", confidence=0.3,
        auto_fixable=False,
    )
    assert validate_finding(f) == []


def test_validate_finding_rejects_completeness_finding_with_blocking_severity():
    f = make_finding(
        layer="completeness", file="f.md", line=1, quote="q", reasoning="r",
        suggested_fix="s", severity="blocking", confidence=0.5, auto_fixable=False,
    )
    errors = validate_finding(f)
    assert any("completeness" in e and "severity" in e for e in errors)


def test_validate_finding_rejects_completeness_finding_with_auto_fixable_true():
    f = make_finding(
        layer="completeness", file="f.md", line=1, quote="q", reasoning="r",
        suggested_fix="s", severity="suggestion", confidence=0.5, auto_fixable=True,
    )
    errors = validate_finding(f)
    assert any("completeness" in e and "auto_fixable" in e for e in errors)


def test_validate_finding_passes_for_well_formed_completeness_finding():
    f = make_finding(
        layer="completeness", file="f.md", line=1, quote="q", reasoning="r",
        suggested_fix="s", severity="suggestion", confidence=0.7, auto_fixable=False,
    )
    assert validate_finding(f) == []


def test_main_validates_json_file_of_findings(tmp_path, capsys):
    findings = [make_finding(
        layer="accuracy", file="f.md", line=1, quote="q", reasoning="r",
        suggested_fix="s", severity="blocking", confidence=0.9,
    )]
    findings_path = tmp_path / "accuracy.json"
    findings_path.write_text(json.dumps(findings))

    exit_code = _finding.main([str(findings_path)])
    assert exit_code == 0
    assert "OK" in capsys.readouterr().out


def test_main_reports_errors_for_invalid_findings(tmp_path, capsys):
    findings_path = tmp_path / "bad.json"
    # Missing required keys (quote, reasoning, suggested_fix, severity,
    # confidence, auto_fixable) — this is exactly the kind of malformed
    # hand-authored finding this CLI exists to catch before aggregate.py does.
    findings_path.write_text(json.dumps([{"layer": "accuracy"}]))

    exit_code = _finding.main([str(findings_path)])
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "finding[0]" in out


def test_main_rejects_json_that_is_not_a_list(tmp_path, capsys):
    findings_path = tmp_path / "not-a-list.json"
    findings_path.write_text(json.dumps({"layer": "accuracy"}))
    exit_code = _finding.main([str(findings_path)])
    assert exit_code == 1
    assert "list" in capsys.readouterr().out
