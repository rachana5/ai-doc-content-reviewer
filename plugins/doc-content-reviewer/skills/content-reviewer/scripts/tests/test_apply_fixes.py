# scripts/tests/test_apply_fixes.py
from __future__ import annotations
from pathlib import Path
from scripts._finding import make_finding
from scripts import apply_fixes


def test_build_diff_shows_line_change():
    diff = apply_fixes.build_diff("line one\nline two\n", "line one\nline TWO\n", "foo.md")
    assert "-line two" in diff
    assert "+line TWO" in diff
    assert "foo.md" in diff


def test_apply_finding_to_text_replaces_quoted_line():
    text = "Header\nThe default value for maxRetries is 3.\nFooter\n"
    finding = make_finding(
        layer="accuracy", file="f.md", line=2,
        quote="The default value for maxRetries is 3.",
        reasoning="r", suggested_fix="The default value for maxRetries is 5.",
        severity="blocking", confidence=0.95,
    )
    result, applied = apply_fixes.apply_finding_to_text(text, finding)
    assert applied is True
    assert "maxRetries is 5" in result
    assert "maxRetries is 3" not in result


def test_apply_finding_to_text_skips_when_quote_no_longer_matches():
    # The doc may have been edited between when the report was generated
    # and when the fix is applied, or the finding's line number may have
    # drifted upstream. Never silently overwrite content the quote no
    # longer matches — that would destroy whatever is actually there.
    text = "Header\nSomeone already changed this line.\nFooter\n"
    finding = make_finding(
        layer="accuracy", file="f.md", line=2,
        quote="The default value for maxRetries is 3.",
        reasoning="r", suggested_fix="The default value for maxRetries is 5.",
        severity="blocking", confidence=0.95,
    )
    result, applied = apply_fixes.apply_finding_to_text(text, finding)
    assert applied is False
    assert result == text  # unchanged, not silently overwritten


def test_apply_finding_to_text_skips_when_line_out_of_range():
    text = "Header\nFooter\n"
    finding = make_finding(
        layer="accuracy", file="f.md", line=99,
        quote="The default value for maxRetries is 3.",
        reasoning="r", suggested_fix="The default value for maxRetries is 5.",
        severity="blocking", confidence=0.95,
    )
    result, applied = apply_fixes.apply_finding_to_text(text, finding)
    assert applied is False
    assert result == text


def test_stage_all_never_writes_to_disk(tmp_path):
    doc = tmp_path / "foo.md"
    doc.write_text("The default value for maxRetries is 3.\n")
    finding = make_finding(
        layer="accuracy", file=str(doc), line=1,
        quote="The default value for maxRetries is 3.",
        reasoning="r", suggested_fix="The default value for maxRetries is 5.",
        severity="blocking", confidence=0.95,
    )
    diff = apply_fixes.stage_all([finding], tmp_path)
    assert "maxRetries is 5" in diff
    # File on disk must be untouched.
    assert doc.read_text() == "The default value for maxRetries is 3.\n"


def test_stage_all_skips_non_auto_fixable_findings(tmp_path):
    doc = tmp_path / "foo.md"
    doc.write_text("Some text.\n")
    finding = make_finding(
        layer="clarity", file=str(doc), line=1, quote="Some text.",
        reasoning="r", suggested_fix="Some clearer text.",
        severity="suggestion", confidence=0.3,  # below AUTO_FIX_THRESHOLD
    )
    diff = apply_fixes.stage_all([finding], tmp_path)
    assert diff == ""


def test_stage_all_skips_findings_with_low_confidence_even_if_auto_fixable_true(tmp_path):
    # Isolates the confidence check from the auto_fixable check.
    # A finding with auto_fixable=True explicitly set but confidence below
    # AUTO_FIX_THRESHOLD must still be excluded from staging. This verifies
    # that _fixable() checks BOTH conditions independently — not just one or
    # the other — by constructing a finding where auto_fixable is explicitly
    # True but confidence is below the threshold.
    doc = tmp_path / "foo.md"
    doc.write_text("Some text.\n")
    finding = make_finding(
        layer="clarity", file=str(doc), line=1, quote="Some text.",
        reasoning="r", suggested_fix="Some clearer text.",
        severity="suggestion", confidence=0.5,  # below AUTO_FIX_THRESHOLD (0.8)
        auto_fixable=True,  # explicitly set, not derived
    )
    diff = apply_fixes.stage_all([finding], tmp_path)
    assert diff == ""


def test_apply_confirmed_writes_files_and_returns_paths(tmp_path):
    doc = tmp_path / "foo.md"
    doc.write_text("The default value for maxRetries is 3.\n")
    finding = make_finding(
        layer="accuracy", file=str(doc), line=1,
        quote="The default value for maxRetries is 3.",
        reasoning="r", suggested_fix="The default value for maxRetries is 5.",
        severity="blocking", confidence=0.95,
    )
    modified = apply_fixes.apply_confirmed([finding], tmp_path)
    assert modified == [str(doc)]
    assert "maxRetries is 5" in doc.read_text()


def test_apply_confirmed_does_not_report_file_modified_when_quote_stale(tmp_path):
    # If the on-disk content no longer matches the finding's quote (doc
    # edited since the report was generated), apply_confirmed must not
    # claim the file was modified when nothing was actually written.
    doc = tmp_path / "foo.md"
    doc.write_text("Someone already changed this line.\n")
    finding = make_finding(
        layer="accuracy", file=str(doc), line=1,
        quote="The default value for maxRetries is 3.",
        reasoning="r", suggested_fix="The default value for maxRetries is 5.",
        severity="blocking", confidence=0.95,
    )
    modified = apply_fixes.apply_confirmed([finding], tmp_path)
    assert modified == []
    assert doc.read_text() == "Someone already changed this line.\n"


def test_stage_all_excludes_diff_for_finding_with_stale_quote(tmp_path):
    doc = tmp_path / "foo.md"
    doc.write_text("Someone already changed this line.\n")
    finding = make_finding(
        layer="accuracy", file=str(doc), line=1,
        quote="The default value for maxRetries is 3.",
        reasoning="r", suggested_fix="The default value for maxRetries is 5.",
        severity="blocking", confidence=0.95,
    )
    diff = apply_fixes.stage_all([finding], tmp_path)
    assert diff == ""


def test_apply_confirmed_handles_multiline_fix_without_breaking_later_findings(tmp_path):
    # A multi-line suggested_fix (e.g. a clarity rewrite splitting one long
    # line into two) shifts every later line's index if applied top-down —
    # the finding below it would then look for its quote at the wrong,
    # shifted line and get skipped. Applying bottom-up (highest line first)
    # avoids this: process line 3's finding while the file still has its
    # original line numbering, THEN expand line 2.
    doc = tmp_path / "foo.md"
    doc.write_text("line1\nline2 original\nline3 original\n")
    finding_multiline = make_finding(
        layer="clarity", file=str(doc), line=2,
        quote="line2 original",
        reasoning="r", suggested_fix="line2a\nline2b",
        severity="suggestion", confidence=0.95,
    )
    finding_below = make_finding(
        layer="accuracy", file=str(doc), line=3,
        quote="line3 original",
        reasoning="r", suggested_fix="line3 fixed",
        severity="blocking", confidence=0.95,
    )
    modified = apply_fixes.apply_confirmed([finding_multiline, finding_below], tmp_path)
    assert modified == [str(doc)]
    text = doc.read_text()
    assert "line2a" in text and "line2b" in text
    assert "line3 fixed" in text
    assert "line3 original" not in text  # must not have been silently skipped


def test_main_stage_mode_prints_diff_without_writing(tmp_path, capsys):
    import json
    doc = tmp_path / "foo.md"
    doc.write_text("The default value for maxRetries is 3.\n")
    finding = make_finding(
        layer="accuracy", file=str(doc), line=1,
        quote="The default value for maxRetries is 3.",
        reasoning="r", suggested_fix="The default value for maxRetries is 5.",
        severity="blocking", confidence=0.95,
    )
    findings_path = tmp_path / "findings.json"
    findings_path.write_text(json.dumps([finding]))

    exit_code = apply_fixes.main(["--findings", str(findings_path), "--repo-root", str(tmp_path)])
    assert exit_code == 0
    assert "maxRetries is 5" in capsys.readouterr().out
    assert "maxRetries is 3" in doc.read_text()  # untouched — stage mode never writes


def test_main_apply_mode_writes_files(tmp_path, capsys):
    import json
    doc = tmp_path / "foo.md"
    doc.write_text("The default value for maxRetries is 3.\n")
    finding = make_finding(
        layer="accuracy", file=str(doc), line=1,
        quote="The default value for maxRetries is 3.",
        reasoning="r", suggested_fix="The default value for maxRetries is 5.",
        severity="blocking", confidence=0.95,
    )
    findings_path = tmp_path / "findings.json"
    findings_path.write_text(json.dumps([finding]))

    exit_code = apply_fixes.main(
        ["--findings", str(findings_path), "--repo-root", str(tmp_path), "--apply"]
    )
    assert exit_code == 0
    assert "maxRetries is 5" in doc.read_text()
