from __future__ import annotations

import json

from scripts import post_review


def _finding(file="docs/foo.md", line=10, severity="blocking", **overrides):
    base = {
        "layer": "accuracy", "layers": ["accuracy"], "file": file, "line": line,
        "quote": "some text", "reasoning": "why", "suggested_fix": "fix",
        "severity": severity, "confidence": 0.9, "auto_fixable": True,
    }
    base.update(overrides)
    return base


def test_all_as_suggestions_forces_every_finding_to_suggestion():
    findings = [_finding(line=3, severity="blocking"), _finding(line=50, severity="suggestion")]
    assert [f["severity"] for f in post_review.all_as_suggestions(findings)] == ["suggestion", "suggestion"]


def test_all_as_suggestions_does_not_mutate_input():
    findings = [_finding(line=50, severity="blocking")]
    post_review.all_as_suggestions(findings)
    assert findings[0]["severity"] == "blocking"


def test_render_comment_empty_findings_uses_friendly_special_case():
    body = post_review.render_comment([], "irrelevant template text")
    assert "no issues found" in body.lower()
    assert post_review.MARKER in body
    assert "blocking" not in body.lower().split("no issues found")[0]


def test_render_comment_nonempty_delegates_to_aggregate_render_report():
    template = "## {{blocking_count}} blocking\n{{#findings}}{{file}}:{{line}}\n{{/findings}}"
    findings = [_finding(file="docs/a.md", line=1, severity="blocking", layers=["accuracy"])]
    body = post_review.render_comment(findings, template)
    assert "1 blocking" in body
    assert "docs/a.md:1" in body


def test_render_comment_embeds_a_custom_marker_on_empty_findings():
    # --marker previously only changed what has_existing_comment searches
    # for, never what actually got posted -- a marker bump would silently
    # keep embedding the old sentinel, breaking "fires once per PR" the
    # moment the marker is ever changed.
    body = post_review.render_comment([], "irrelevant", marker="<!-- review-doc-pr:v2 -->")
    assert "<!-- review-doc-pr:v2 -->" in body
    assert post_review.MARKER not in body


def test_render_comment_embeds_a_custom_marker_on_nonempty_findings():
    template = f"## report\n{{{{#findings}}}}{{{{file}}}}{{{{/findings}}}}\n{post_review.MARKER}\n"
    findings = [_finding(file="docs/a.md", line=1, severity="blocking", layers=["accuracy"])]
    body = post_review.render_comment(findings, template, marker="<!-- review-doc-pr:v2 -->")
    assert "<!-- review-doc-pr:v2 -->" in body
    assert post_review.MARKER not in body


def test_has_existing_comment_true_when_marker_present(monkeypatch):
    monkeypatch.setattr(
        post_review._gh, "run",
        lambda args: json.dumps({"comments": [{"body": f"hello {post_review.MARKER}"}]}),
    )
    assert post_review.has_existing_comment("owner/repo", "42") is True


def test_has_existing_comment_false_when_absent(monkeypatch):
    monkeypatch.setattr(
        post_review._gh, "run",
        lambda args: json.dumps({"comments": [{"body": "unrelated comment"}]}),
    )
    assert post_review.has_existing_comment("owner/repo", "42") is False


def test_has_existing_comment_false_when_no_comments_at_all(monkeypatch):
    monkeypatch.setattr(post_review._gh, "run", lambda args: json.dumps({"comments": []}))
    assert post_review.has_existing_comment("owner/repo", "42") is False


def test_has_existing_comment_uses_pr_view_json_not_paginated_api(monkeypatch):
    calls = []

    def _run(args):
        calls.append(args)
        return json.dumps({"comments": []})

    monkeypatch.setattr(post_review._gh, "run", _run)
    post_review.has_existing_comment("owner/repo", "42")
    assert calls == [["pr", "view", "42", "--repo", "owner/repo", "--json", "comments"]]


def test_post_comment_calls_gh_pr_comment_with_a_body_file(monkeypatch, tmp_path):
    calls = []
    written_bodies = []

    def _run(args):
        calls.append(args)
        # simulate reading the --body-file argument's contents before cleanup
        body_file_path = args[args.index("--body-file") + 1]
        written_bodies.append(open(body_file_path).read())
        return ""

    monkeypatch.setattr(post_review._gh, "run", _run)
    post_review.post_comment("owner/repo", "42", "the rendered body")
    assert calls[0][:4] == ["pr", "comment", "42", "--repo"]
    assert written_bodies == ["the rendered body"]


def test_main_skips_posting_when_marker_already_present(monkeypatch, tmp_path, capsys):
    findings_path = tmp_path / "merged.json"
    findings_path.write_text(json.dumps([]))
    changed_lines_path = tmp_path / "changed.json"
    changed_lines_path.write_text(json.dumps({}))
    template_path = tmp_path / "template.md.tmpl"
    template_path.write_text("irrelevant")

    monkeypatch.setattr(post_review, "has_existing_comment", lambda repo, pr, marker=post_review.MARKER: True)

    posted = []
    monkeypatch.setattr(post_review, "post_comment", lambda repo, pr, body: posted.append((repo, pr, body)))

    exit_code = post_review.main([
        "--repo", "owner/repo", "--pr", "42",
        "--findings", str(findings_path),
        "--changed-lines", str(changed_lines_path),
        "--template", str(template_path),
    ])
    assert exit_code == 0
    assert posted == []
    assert "skipping" in capsys.readouterr().out


def test_main_posts_when_no_existing_comment(monkeypatch, tmp_path):
    findings_path = tmp_path / "merged.json"
    findings_path.write_text(json.dumps([]))
    changed_lines_path = tmp_path / "changed.json"
    changed_lines_path.write_text(json.dumps({}))
    template_path = tmp_path / "template.md.tmpl"
    template_path.write_text("irrelevant")

    monkeypatch.setattr(post_review, "has_existing_comment", lambda repo, pr, marker=post_review.MARKER: False)

    posted = []
    monkeypatch.setattr(post_review, "post_comment", lambda repo, pr, body: posted.append((repo, pr, body)))

    exit_code = post_review.main([
        "--repo", "owner/repo", "--pr", "42",
        "--findings", str(findings_path),
        "--changed-lines", str(changed_lines_path),
        "--template", str(template_path),
    ])
    assert exit_code == 0
    assert len(posted) == 1
    assert posted[0][0] == "owner/repo"
    assert posted[0][1] == "42"
    assert "no issues found" in posted[0][2].lower()


def test_main_dry_run_prints_without_checking_marker_or_posting(monkeypatch, tmp_path, capsys):
    findings_path = tmp_path / "merged.json"
    findings_path.write_text(json.dumps([]))
    changed_lines_path = tmp_path / "changed.json"
    changed_lines_path.write_text(json.dumps({}))
    template_path = tmp_path / "template.md.tmpl"
    template_path.write_text("irrelevant")

    def _boom(*a, **k):
        raise AssertionError("dry-run must not check for an existing comment")

    monkeypatch.setattr(post_review, "has_existing_comment", _boom)
    monkeypatch.setattr(post_review, "post_comment", lambda *a, **k: (_ for _ in ()).throw(AssertionError("dry-run must not post")))

    exit_code = post_review.main([
        "--repo", "owner/repo", "--pr", "42",
        "--findings", str(findings_path),
        "--changed-lines", str(changed_lines_path),
        "--template", str(template_path),
        "--dry-run",
    ])
    assert exit_code == 0
    assert "no issues found" in capsys.readouterr().out.lower()


def test_main_applies_severity_cap_before_rendering(tmp_path, capsys):
    # line 99 is outside the [1, 5] changed range -- the finding starts
    # "blocking" but must render as capped to "suggestion" before the
    # template's counts are computed.
    findings_path = tmp_path / "merged.json"
    findings_path.write_text(json.dumps([_finding(file="docs/a.md", line=99, severity="blocking")]))
    changed_lines_path = tmp_path / "changed.json"
    changed_lines_path.write_text(json.dumps({"docs/a.md": [[1, 5]]}))
    template_path = tmp_path / "template.md.tmpl"
    template_path.write_text(
        "{{blocking_count}} blocking, {{suggestion_count}} suggestions"
    )

    exit_code = post_review.main([
        "--repo", "owner/repo", "--pr", "42",
        "--findings", str(findings_path),
        "--changed-lines", str(changed_lines_path),
        "--template", str(template_path),
        "--dry-run",
    ])
    assert exit_code == 0
    assert "0 blocking, 1 suggestion" in capsys.readouterr().out


def test_drop_outside_diff_removes_only_listed_layers_outside_the_diff():
    from scripts import post_review as pr
    ranges = {"a.md": [[10, 12]]}
    fs = [
        {"layer": "reference", "file": "a.md", "line": 99},   # outside, droppable
        {"layer": "reference", "file": "a.md", "line": 11},   # inside, kept
        {"layer": "accuracy", "file": "a.md", "line": 99},    # outside, other layer, kept
        {"layer": "reference", "layers": ["reference", "style"], "file": "a.md", "line": 99},  # mixed, kept
    ]
    kept = pr.drop_outside_diff(fs, ranges, ["reference"])
    assert [(f["layer"], f["line"]) for f in kept] == [("reference", 11), ("accuracy", 99), ("reference", 99)]


def test_classify_silent_posts_nothing(tmp_path, capsys):
    import json
    from scripts import post_review as pr
    for name, data in {"f.json": [], "c.json": {}, "k.json": {"action": "missing-docs-only"}}.items():
        (tmp_path / name).write_text(json.dumps(data))
    tmpl = tmp_path / "t.tmpl"; tmpl.write_text("x")
    rc = pr.main(["--repo", "o/r", "--pr", "1", "--findings", str(tmp_path / "f.json"),
                  "--changed-lines", str(tmp_path / "c.json"), "--template", str(tmpl),
                  "--classify", str(tmp_path / "k.json"), "--dry-run"])
    assert rc == 0 and "no comment posted" in capsys.readouterr().out


# --- new comment layout ----------------------------------------------------
def _f(layer, sev, line, quote="old text", fix="new text", reasoning="Rule one. Extra evidence."):
    return {"layer": layer, "file": "docs/content/a/b/page.md", "line": line, "quote": quote,
            "reasoning": reasoning, "suggested_fix": fix, "severity": sev,
            "confidence": 0.7, "auto_fixable": False}


def test_findings_are_ordered_by_impact_then_line_within_a_layer():
    from scripts import post_review as pr
    block = pr.render_findings_block([_f("style", "suggestion", 3), _f("accuracy", "suggestion", 90), _f("style", "suggestion", 1)])
    assert block.index(":90") < block.index(":1<") < block.index(":3<")


def test_simple_edit_renders_as_diff_and_has_no_headings_or_tables():
    from scripts import post_review as pr
    out = pr.render_findings_block([_f("style", "suggestion", 7)])
    assert "```diff\n- old text\n+ new text\n```" in out
    assert "\n#" not in out and "|---" not in out


def test_collapsed_row_shows_file_and_rule_and_body_has_labelled_parts():
    from scripts import post_review as pr
    f = _f("style", "suggestion", 7, reasoning="Replace leverages with uses.")
    f["rule"] = "Style guide: Words to avoid"
    out = pr.render_finding(f)
    summary = out.split("<summary>")[1].split("</summary>")[0]
    assert "page.md:7" in summary and "Style guide: Words to avoid" in summary
    assert "Replace leverages" not in summary          # reasoning is NOT in the collapsed row
    assert "**What's wrong:** Replace leverages with uses." in out and "**Suggested fix:**" in out


def test_rule_falls_back_to_the_layer_name_and_full_reasoning_is_never_cut():
    from scripts import post_review as pr
    long = "Sentence one is long. " * 30
    out = pr.render_finding(_f("accuracy", "blocking", 3, reasoning=long))
    assert "Accuracy" in out.split("</summary>")[0]
    assert " ".join(long.split()) in out


def test_multiline_fix_is_not_forced_into_a_diff():
    from scripts import post_review as pr
    out = pr.render_finding(_f("completeness", "suggestion", 1, quote="pkg/x.go: new option", fix="Add:\n\n```markdown\n| a |\n```"))
    assert "```diff" not in out and "**Code change:** pkg/x.go: new option" in out and "```markdown" in out


def test_oversized_comment_shortens_fixes_and_says_so():
    from scripts import post_review as pr
    big = [_f("completeness", "suggestion", i, fix="x" * 3000) for i in range(30)]
    out = pr.render_findings_block(big)
    assert len(out) < pr.COMMENT_SIZE_CAP + 2000 and "shortened" in out


def test_singular_suggestion_count():
    from scripts import post_review as pr
    tmpl = "## Docs review: {{blocking_count}} blocking, {{suggestion_count}} suggestions\n\n{{findings_block}}\n"
    out = pr.render_comment([_f("style", "suggestion", 1)], tmpl)
    assert "1 suggestion\n" in out.split("\n\n")[0] + "\n" and "1 suggestions" not in out


def test_extra_reasoning_is_plain_markdown_not_small_italic_html():
    from scripts import post_review as pr
    out = pr.render_finding(_f("accuracy", "blocking", 5, reasoning="Wrong default. The code sets `X` to 2 MB."))
    assert "The code sets `X` to 2 MB." in out
    assert "<sub>" not in out and "<i>" not in out


def _s(layer="style", line=1, group=None, file="docs/content/a/b/page.md"):
    f = _f(layer, "suggestion", line)
    f["file"] = file
    if group:
        f["group"] = group
    return f


def test_fewer_than_eight_suggestions_are_never_grouped():
    from scripts import post_review as pr
    fs = [_s(line=i, group="`maxBurst`") for i in range(1, 8)]
    assert all(len(u) == 1 for u in pr.group_findings(fs))
    assert "related suggestions" not in pr.render_findings_block(fs)


def test_eight_or_more_suggestions_group_by_shared_key():
    from scripts import post_review as pr
    fs = [_s(line=i, group="`maxBurst`") for i in range(1, 4)] + [_s(line=10 + i) for i in range(5)]
    units = pr.group_findings(fs)
    assert sorted(len(u) for u in units) == [1, 1, 1, 1, 1, 3]
    out = pr.render_findings_block(fs)
    assert "3 related suggestions" in out and "<code>maxBurst</code>" in out
    assert out.count("<details>") == 1 + 8 + 1   # one group, each finding its own row, plus the wording fold


def test_link_findings_group_by_default_and_a_lone_key_stays_single():
    from scripts import post_review as pr
    fs = [_s("reference", i) for i in range(1, 4)] + [_s(line=20 + i) for i in range(4)] + [_s(line=40, group="solo")]
    units = pr.group_findings(fs)
    assert sorted(len(u) for u in units) == [1, 1, 1, 1, 1, 3]
    assert "Links and references" in pr.render_findings_block(fs)


def test_a_high_impact_finding_is_never_buried_inside_a_group():
    from scripts import post_review as pr
    high = [dict(_s("completeness", i, group="`x`"), impact="high") for i in range(1, 3)]
    low = [_s("style", i, group="`x`") for i in range(1, 9)]
    units = pr.group_findings(low + high)
    assert len(units) == 1 and len(units[0]) == 10   # one key groups them all
    assert [f["impact"] for f in units[0][:2]] == ["high", "high"]   # but the high ones lead the group


def test_drop_outside_diff_keeps_affected_findings():
    from scripts import post_review as pr
    link = _f("reference", "suggestion", 50)
    link.update(layer="reference", layers=["reference"], affected=True)
    old = dict(link, affected=False)
    assert pr.drop_outside_diff([link, old], {"docs/foo.md": [[1, 5]]}, ["reference"]) == [link]


def test_suggestions_are_ordered_by_layer_importance_then_confidence_then_location():
    from scripts import post_review as pr
    def mk(layer, line, conf=0.7, file="docs/content/a/b/page.md"):
        d = _s(layer, line, file=file)
        d["confidence"] = conf
        return d
    fs = [mk("style", 1), mk("reference", 2), mk("completeness", 3, 0.5), mk("completeness", 4, 0.7),
          mk("accuracy", 90), mk("clarity", 5)]
    order = [u[0]["layer"] + str(u[0]["line"]) for u in pr.group_findings(fs)]
    assert order == ["accuracy90", "completeness4", "completeness3", "reference2", "clarity5", "style1"]


def test_explicit_impact_beats_the_layer_default():
    from scripts import post_review as pr
    # An upgrade-impact missing-docs finding (impact high) comes before a medium accuracy one.
    fs = [dict(_s("accuracy", 1), impact="low"), dict(_s("completeness", 50), impact="high"), _s("style", 3)]
    assert [u[0]["layer"] for u in pr.group_findings(fs)] == ["completeness", "accuracy", "style"]


def test_layer_default_impact_orders_findings_that_set_none():
    from scripts import post_review as pr
    fs = [_s("style", 1), _s("reference", 2), _s("completeness", 3), _s("accuracy", 4)]
    assert [u[0]["layer"] for u in pr.group_findings(fs)] == ["accuracy", "completeness", "reference", "style"]


def test_heading_has_no_blocking_count_and_singularizes(tmp_path):
    from scripts import post_review as pr
    tmpl = (pr.Path(__file__).parent.parent.parent / "templates" / "pr-comment.md.tmpl").read_text()
    out = pr.render_comment(pr.all_as_suggestions([_f("accuracy", "blocking", 3)]), tmpl)
    assert out.startswith("## Docs review: 1 suggestion\n")
    assert "blocking" not in out.split("<!--")[0].lower()
    two = pr.render_comment(pr.all_as_suggestions([_f("accuracy", "blocking", 3), _f("style", "suggestion", 5)]), tmpl)
    assert two.startswith("## Docs review: 2 suggestions\n")


def test_out_writes_the_comment_and_never_posts(monkeypatch, tmp_path, capsys):
    from scripts import post_review as pr
    import json
    called = []
    monkeypatch.setattr(pr, "post_comment", lambda *a, **k: called.append(a))
    monkeypatch.setattr(pr, "has_existing_comment", lambda *a, **k: called.append("marker-check") or False)
    f = tmp_path / "f.json"; f.write_text(json.dumps([_f("style", "suggestion", 1)]))
    c = tmp_path / "c.json"; c.write_text("{}")
    tmpl = tmp_path / "t.tmpl"; tmpl.write_text("## {{blocking_count}} blocking, {{suggestion_count}} suggestions\n\n{{findings_block}}\n")
    out = tmp_path / "comment.md"
    rc = pr.main(["--repo", "o/r", "--pr", "1", "--findings", str(f), "--changed-lines", str(c),
                  "--template", str(tmpl), "--out", str(out)])
    assert rc == 0 and called == [] and "1 suggestion" in out.read_text()


def test_drop_outside_diff_covers_style_and_clarity_and_keeps_whole_file_findings():
    from scripts import post_review as pr
    ranges = {"a.md": [[10, 12]]}
    layers = ["reference", "style", "clarity"]
    fs = [
        {"layer": "style", "file": "a.md", "line": 99},        # outside, dropped
        {"layer": "clarity", "file": "a.md", "line": 99},      # outside, dropped
        {"layer": "style", "file": "a.md", "line": 11},        # inside, kept
        {"layer": "style", "file": "a.md", "line": 0},         # whole file (a generated file edited by hand), kept
        {"layer": "accuracy", "file": "a.md", "line": 99},     # not a listed layer, kept
        {"layer": "style", "file": "a.md", "line": 99, "affected": True},  # kept
    ]
    kept = pr.drop_outside_diff(fs, ranges, layers)
    assert [(f["layer"], f["line"]) for f in kept] == [("style", 11), ("style", 0), ("accuracy", 99), ("style", 99)]


def test_the_shipped_profile_drops_style_and_clarity_outside_the_diff_too():
    from scripts import profile
    assert {"reference", "style", "clarity"} <= set(profile.load("proxy")["drop_outside_diff_layers"])


# --- noise, links and commit line (traefik/traefik review audit, 2026-11-21) ---

def _g(layer, line, rule=None, file="docs/a.md", **kw):
    f = _f(layer, "suggestion", line, **kw)
    f["file"] = file
    if rule:
        f["rule"] = rule
    return f


def _style(line, rule="Style guide: Clarity Rules", **kw):
    return _g("style", line, rule=rule, **kw)


def test_relative_links_in_prose_are_neutralized_but_urls_and_anchors_are_kept():
    from scripts import post_review as pr
    text = "See [tracing](./tracing.md#opt-x), [site](https://example.com/a) and [here](#top)."
    out = pr.neutralize_links(text)
    assert "tracing (`./tracing.md#opt-x`)" in out
    assert "[site](https://example.com/a)" in out and "[here](#top)" in out
    assert "](./tracing.md" not in out


def test_reasoning_and_completeness_code_change_are_neutralized():
    from scripts import post_review as pr
    f = _f("accuracy", "suggestion", 3, reasoning="Wrong, see [x](../x.md).")
    assert "](../x.md)" not in pr.render_finding(f)
    c = _f("completeness", "suggestion", 1, quote="a: see [x](../x.md)", fix="Add it.")
    assert "](../x.md)" not in pr.render_finding(c)


def test_block_quote_and_prose_fix_are_fenced_so_links_survive_verbatim():
    from scripts import post_review as pr
    q = "Text with [link](../a.md) over\nthree\nlines"
    f = _f("accuracy", "suggestion", 3, quote=q, fix="Line one\nSee [link](../a.md)")
    out = pr.render_finding(f)
    assert "```\n" + q + "\n```" in out
    assert "```markdown\nLine one\nSee [link](../a.md)\n```" in out
    assert "> Text" not in out


def test_fence_grows_to_contain_a_fence_inside_the_fix():
    from scripts import post_review as pr
    out = pr.fenced("Add:\n```yaml\na: 1\n```", "markdown")
    assert out.startswith("````markdown\n") and out.endswith("\n````")


def test_commit_line_links_the_short_sha_and_is_empty_without_a_commit():
    from scripts import post_review as pr
    sha = "e75dd61a661f8745bde7e92618e317cc1a1e21f0"
    assert pr.commit_line(sha, "traefik/traefik") == (
        f"Reviewed at commit [`e75dd61`](https://github.com/traefik/traefik/commit/{sha}).")
    assert pr.commit_line(sha) == "Reviewed at commit `e75dd61`."
    assert pr.commit_line(None, "traefik/traefik") == ""


def test_comment_shows_the_commit_under_the_heading_and_omits_the_slot_without_one():
    from scripts import post_review as pr
    tmpl = open("templates/pr-comment.md.tmpl").read()
    f = [_f("accuracy", "suggestion", 3)]
    with_commit = pr.render_comment(f, tmpl, reviewed="Reviewed at commit `abc1234`.")
    lines = with_commit.splitlines()
    assert lines[0].startswith("## Docs review") and lines[2] == "Reviewed at commit `abc1234`."
    assert "{{" not in with_commit
    without = pr.render_comment(f, tmpl)
    assert "{{" not in without and "Reviewed at" not in without and "\n\n\n\n" not in without
    empty = pr.render_comment([], tmpl, reviewed="Reviewed at commit `abc1234`.")
    assert "no issues found" in empty and "Reviewed at commit `abc1234`." in empty and "{{" not in empty
    assert "{{" not in pr.render_comment([], tmpl)


def test_same_rule_in_one_file_is_one_finding_with_every_occurrence():
    from scripts import post_review as pr
    fs = [_style(369, quote="the EntryPoint", fix="the entry point"),
          _style(398, quote="EntryPoint option", fix="entry point option"),
          _style(399, quote="(EntryPoint)", fix="(entry point)")]
    merged = pr.merge_same_rule(fs)
    assert len(merged) == 1 and len(merged[0]["occurrences"]) == 2
    out = pr.render_finding(merged[0])
    assert "a.md:369" in out and "(+2 more)" in out
    for line in ("369", "398", "399"):
        assert f"Line {line}:" in out
    assert pr.render_comment(merged, open("templates/pr-comment.md.tmpl").read()).startswith("## Docs review: 1 suggestion\n")


def test_merge_keeps_different_rules_files_and_non_style_layers_apart():
    from scripts import post_review as pr
    fs = [_style(1), _style(2, rule="Style guide: Voice"),
          _g("style", 3, rule="Style guide: Clarity Rules", file="docs/b.md"),
          _g("accuracy", 4, rule="Accuracy: x"),
          _g("accuracy", 5, rule="Accuracy: x")]
    assert len(pr.merge_same_rule(fs)) == 5


def test_merge_does_not_mutate_its_input():
    from scripts import post_review as pr
    fs = [_style(1), _style(2)]
    pr.merge_same_rule(fs)
    assert "occurrences" not in fs[0]


def test_wording_beyond_three_units_folds_into_one_row_and_nothing_is_dropped():
    from scripts import post_review as pr
    fs = [_style(i, rule=f"Style guide: Rule {i}") for i in range(1, 7)]
    out = pr.render_findings_block(fs)
    assert "3 more wording suggestions" in out
    for i in range(1, 7):
        assert f"Rule {i}</summary>" in out
    assert pr.render_findings_block(fs[:3]).count("more wording") == 0


def test_a_fold_never_swallows_accuracy_or_missing_docs():
    from scripts import post_review as pr
    fs = [_style(i, rule=f"Style guide: Rule {i}") for i in range(1, 6)]
    fs.append(_g("accuracy", 50, rule="Accuracy: default"))
    out = pr.render_findings_block(fs)
    head = out.split("more wording")[0]
    assert "Accuracy: default" in head


def test_completeness_without_a_rule_is_labelled_completeness_not_missing_docs():
    from scripts import post_review as pr
    f = _f("completeness", "suggestion", 1, quote="x", fix="y")
    f.pop("rule", None)
    assert "Completeness" in pr.render_finding(f).split("</summary>")[0]
