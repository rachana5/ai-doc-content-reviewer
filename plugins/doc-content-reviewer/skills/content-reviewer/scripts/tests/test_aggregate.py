from __future__ import annotations
from scripts._finding import make_finding
from scripts import aggregate


def _f(layer, file, line, confidence=0.9, quote="q"):
    return make_finding(
        layer=layer, file=file, line=line, quote=quote, reasoning="r",
        suggested_fix="s", severity="suggestion", confidence=confidence,
    )


def test_dedup_merges_same_file_line_and_quote():
    a = _f("style", "docs/foo.md", 10)
    b = _f("clarity", "docs/foo.md", 10)
    merged = aggregate.dedup_findings([a, b])
    assert len(merged) == 1
    assert set(merged[0]["layers"]) == {"style", "clarity"}


def test_dedup_leaves_distinct_locations_separate():
    a = _f("style", "docs/foo.md", 10)
    b = _f("style", "docs/foo.md", 20)
    merged = aggregate.dedup_findings([a, b])
    assert len(merged) == 2


def test_dedup_does_not_merge_different_findings_on_the_same_line():
    # Dense markdown (table rows, long single-line paragraphs) can put two
    # UNRELATED findings on the same line. Merging on (file, line) alone
    # would silently drop the lower-confidence finding's own reasoning and
    # suggested_fix — only the higher-confidence one's content would survive,
    # under a layers list that (wrongly) claims both layers agree on one
    # thing. Require the quote to match too before merging.
    a = _f("style", "docs/foo.md", 10, quote="first unrelated issue")
    b = _f("clarity", "docs/foo.md", 10, quote="second unrelated issue")
    merged = aggregate.dedup_findings([a, b])
    assert len(merged) == 2
    quotes = {f["quote"] for f in merged}
    assert quotes == {"first unrelated issue", "second unrelated issue"}


def test_dedup_is_a_noop_on_single_finding():
    a = _f("accuracy", "docs/foo.md", 5)
    merged = aggregate.dedup_findings([a])
    assert merged[0]["layers"] == ["accuracy"]


def test_sort_findings_orders_by_file_then_line():
    a = _f("style", "docs/b.md", 5)
    b = _f("style", "docs/a.md", 20)
    c = _f("style", "docs/a.md", 3)
    ordered = aggregate.sort_findings(aggregate.dedup_findings([a, b, c]))
    assert [(f["file"], f["line"]) for f in ordered] == [
        ("docs/a.md", 3), ("docs/a.md", 20), ("docs/b.md", 5),
    ]


def test_aggregate_merges_all_layers_and_sorts():
    layer_findings = {
        "accuracy": [_f("accuracy", "docs/a.md", 10)],
        "style": [_f("style", "docs/a.md", 10)],
        "reference": [_f("reference", "docs/b.md", 1)],
        "clarity": [],
    }
    result = aggregate.aggregate(layer_findings)
    assert len(result) == 2
    assert set(result[0]["layers"]) == {"accuracy", "style"}
    assert result[1]["file"] == "docs/b.md"


def test_aggregate_assigns_sequential_ids_in_sorted_order():
    # Findings have no other stable identifier — this id is what a user
    # references when approving a subset ("apply findings 2 and 4") in
    # SKILL.md's Step 5, so it must be assigned in the same order the
    # report displays them (sorted by location), not insertion order.
    layer_findings = {
        "style": [_f("style", "docs/b.md", 5), _f("style", "docs/a.md", 3)],
        "accuracy": [], "reference": [], "clarity": [],
    }
    result = aggregate.aggregate(layer_findings)
    assert result[0]["file"] == "docs/a.md"
    assert result[1]["file"] == "docs/b.md"
    assert [f["id"] for f in result] == [1, 2]


def test_render_report_includes_layer_badges_and_quotes():
    findings = aggregate.aggregate({
        "accuracy": [_f("accuracy", "docs/a.md", 10, quote="wrong default")],
        "style": [], "reference": [], "clarity": [],
    })
    template = "# Report\n{{#findings}}- [{{layers}}] {{file}}:{{line}} — {{quote}}\n{{/findings}}"
    rendered = aggregate.render_report(findings, template)
    assert "accuracy" in rendered
    assert "wrong default" in rendered
    assert "docs/a.md:10" in rendered


def test_main_merges_layers_writes_json_and_prints_report(tmp_path, capsys):
    import json
    accuracy_path = tmp_path / "accuracy.json"
    accuracy_path.write_text(json.dumps([_f("accuracy", "docs/a.md", 10, quote="wrong")]))
    out_path = tmp_path / "merged.json"
    template_path = tmp_path / "report.tmpl"
    template_path.write_text("{{#findings}}{{file}}:{{line}} {{quote}}\n{{/findings}}")

    exit_code = aggregate.main([
        "--accuracy", str(accuracy_path),
        "--template", str(template_path), "--out", str(out_path),
    ])
    assert exit_code == 0
    assert "docs/a.md:10 wrong" in capsys.readouterr().out
    written = json.loads(out_path.read_text())
    assert written[0]["file"] == "docs/a.md"
    assert written[0]["id"] == 1  # merged.json findings carry ids for subset approval


def test_render_report_substitutes_metadata_outside_findings_loop():
    """Test that top-level metadata placeholders are substituted outside the loop."""
    findings = aggregate.aggregate({
        "accuracy": [_f("accuracy", "docs/a.md", 10, quote="wrong default")],
        "style": [], "reference": [], "clarity": [],
    })
    template = "Repo: {{repo}} | Scope: {{scope}}\n{{#findings}}{{file}}: {{quote}}\n{{/findings}}"
    rendered = aggregate.render_report(findings, template, {"repo": "my-repo", "scope": "docs"})
    assert "Repo: my-repo | Scope: docs" in rendered
    assert "docs/a.md: wrong default" in rendered


def test_render_report_auto_computes_blocking_count():
    """Test that blocking_count is auto-computed from findings with severity=blocking."""
    findings_data = [
        make_finding(layer="accuracy", file="docs/a.md", line=1, quote="q1", reasoning="r", suggested_fix="s", severity="blocking", confidence=0.9),
        make_finding(layer="style", file="docs/a.md", line=2, quote="q2", reasoning="r", suggested_fix="s", severity="suggestion", confidence=0.9),
        make_finding(layer="reference", file="docs/a.md", line=3, quote="q3", reasoning="r", suggested_fix="s", severity="blocking", confidence=0.9),
    ]
    findings = aggregate.aggregate({
        "accuracy": [findings_data[0]],
        "style": [findings_data[1]],
        "reference": [findings_data[2]],
        "clarity": [],
    })
    template = "Blocking: {{blocking_count}}\n{{#findings}}{{severity}}\n{{/findings}}"
    rendered = aggregate.render_report(findings, template)
    assert "Blocking: 2" in rendered


def test_render_report_auto_computes_suggestion_count():
    """Test that suggestion_count is auto-computed from findings with severity=suggestion."""
    findings_data = [
        make_finding(layer="accuracy", file="docs/a.md", line=1, quote="q1", reasoning="r", suggested_fix="s", severity="blocking", confidence=0.9),
        make_finding(layer="style", file="docs/a.md", line=2, quote="q2", reasoning="r", suggested_fix="s", severity="suggestion", confidence=0.9),
        make_finding(layer="reference", file="docs/a.md", line=3, quote="q3", reasoning="r", suggested_fix="s", severity="suggestion", confidence=0.9),
    ]
    findings = aggregate.aggregate({
        "accuracy": [findings_data[0]],
        "style": [findings_data[1]],
        "reference": [findings_data[2]],
        "clarity": [],
    })
    template = "Suggestions: {{suggestion_count}}\n{{#findings}}{{severity}}\n{{/findings}}"
    rendered = aggregate.render_report(findings, template)
    assert "Suggestions: 2" in rendered


def test_render_report_auto_computes_auto_fixable_count():
    """Test that auto_fixable_count is auto-computed from findings with auto_fixable=true."""
    findings_data = [
        make_finding(layer="accuracy", file="docs/a.md", line=1, quote="q1", reasoning="r", suggested_fix="s", severity="suggestion", confidence=0.9, auto_fixable=True),
        make_finding(layer="style", file="docs/a.md", line=2, quote="q2", reasoning="r", suggested_fix="s", severity="suggestion", confidence=0.9, auto_fixable=False),
        make_finding(layer="reference", file="docs/a.md", line=3, quote="q3", reasoning="r", suggested_fix="s", severity="suggestion", confidence=0.9, auto_fixable=True),
    ]
    findings = aggregate.aggregate({
        "accuracy": [findings_data[0]],
        "style": [findings_data[1]],
        "reference": [findings_data[2]],
        "clarity": [],
    })
    template = "Auto-fixable: {{auto_fixable_count}}\n{{#findings}}{{auto_fixable}}\n{{/findings}}"
    rendered = aggregate.render_report(findings, template)
    assert "Auto-fixable: 2" in rendered


def test_render_report_metadata_overrides_auto_computed_counts():
    """Test that explicitly passed metadata can override auto-computed counts."""
    findings_data = [
        make_finding(layer="accuracy", file="docs/a.md", line=1, quote="q1", reasoning="r", suggested_fix="s", severity="blocking", confidence=0.9),
    ]
    findings = aggregate.aggregate({
        "accuracy": [findings_data[0]],
        "style": [], "reference": [], "clarity": [],
    })
    template = "Blocking: {{blocking_count}} | Suggestions: {{suggestion_count}}\n{{#findings}}{{severity}}\n{{/findings}}"
    # Override the auto-computed blocking_count
    rendered = aggregate.render_report(findings, template, {"blocking_count": 99, "suggestion_count": 5})
    assert "Blocking: 99 | Suggestions: 5" in rendered


def test_render_report_defaults_to_empty_string_when_metadata_missing():
    """Test that missing metadata keys default to empty strings."""
    findings = []
    template = "Repo: |{{repo}}| Scope: |{{scope}}|\n{{#findings}}{{quote}}\n{{/findings}}"
    rendered = aggregate.render_report(findings, template)
    assert "Repo: || Scope: ||" in rendered


def test_main_passes_metadata_flags_to_report(tmp_path, capsys):
    """Test that CLI flags flow through to render_report in main()."""
    import json
    accuracy_path = tmp_path / "accuracy.json"
    accuracy_path.write_text(json.dumps([_f("accuracy", "docs/a.md", 10, quote="wrong")]))
    out_path = tmp_path / "merged.json"
    template_path = tmp_path / "report.tmpl"
    template_path.write_text("Repo: {{repo}} | Scope: {{scope}} | Date: {{date}}\n{{#findings}}{{file}}\n{{/findings}}")

    exit_code = aggregate.main([
        "--accuracy", str(accuracy_path),
        "--template", str(template_path), "--out", str(out_path),
        "--repo", "test-repo",
        "--scope", "docs/guides",
        "--date", "2026-08-30",
    ])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Repo: test-repo | Scope: docs/guides | Date: 2026-08-30" in output


def test_main_passes_mode_and_layers_run_flags(tmp_path, capsys):
    """Test that --mode and --layers-run flags work correctly."""
    import json
    accuracy_path = tmp_path / "accuracy.json"
    accuracy_path.write_text(json.dumps([_f("accuracy", "docs/a.md", 10, quote="wrong")]))
    out_path = tmp_path / "merged.json"
    template_path = tmp_path / "report.tmpl"
    template_path.write_text("Mode: {{mode}} | Layers: {{layers_run}}\n{{#findings}}{{file}}\n{{/findings}}")

    exit_code = aggregate.main([
        "--accuracy", str(accuracy_path),
        "--template", str(template_path), "--out", str(out_path),
        "--mode", "strict",
        "--layers-run", "accuracy,style",
    ])
    assert exit_code == 0
    output = capsys.readouterr().out
    assert "Mode: strict | Layers: accuracy,style" in output
