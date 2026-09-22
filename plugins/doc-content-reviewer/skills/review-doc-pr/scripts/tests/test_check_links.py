from __future__ import annotations
import urllib.error
from pathlib import Path
from unittest import mock

from scripts import check_links


def test_extract_links_finds_markdown_links_with_line_numbers():
    text = "line one\n[foo](./foo.md)\nline three\n[bar](https://example.com)\n"
    links = check_links.extract_links(text)
    assert links == [("./foo.md", 2), ("https://example.com", 4)]


def test_http_head_and_get_send_a_user_agent(monkeypatch):
    # Confirmed against a real site (traefik.io): urllib's default
    # "Python-urllib/x.y" User-Agent gets a flat 403 from bot protection
    # that a browser-like UA sails through — without a UA header, the
    # 403-triggered GET retry below would hit the exact same block and
    # every link into such a domain would false-flag as broken.
    captured = {}

    def fake_open(request, timeout):
        captured["headers"] = request.headers
        return mock.Mock(status=200)

    monkeypatch.setattr(check_links._opener, "open", fake_open)
    check_links._http_head("https://example.com", 10.0)
    assert "User-agent" in captured["headers"]
    assert captured["headers"]["User-agent"] != ""

    check_links._http_get("https://example.com", 10.0)
    assert "User-agent" in captured["headers"]


def test_extract_links_strips_optional_link_title():
    # [text](url "title") is valid CommonMark — the title must not leak into
    # the extracted target, or it corrupts internal-path resolution and
    # crashes external HEAD requests (http.client.InvalidURL) instead of
    # degrading gracefully like every other unreachable-link case.
    text = (
        'Join our [Community Forum](https://community.traefik.io "Link to Traefik Community Forum").\n'
        "See [foo](./foo.md 'local title') for details.\n"
    )
    links = check_links.extract_links(text)
    assert links == [
        ("https://community.traefik.io", 1),
        ("./foo.md", 2),
    ]


def test_extract_links_ignores_fenced_code_blocks_and_inline_spans():
    # A doc that shows markdown link syntax as an example (common in
    # docs-about-docs, config snippets) must not be mistaken for a real link.
    text = (
        "Real link: [foo](./foo.md)\n"
        "Inline example: use `[text](./url.md)` syntax for links.\n"
        "```\n"
        "[fenced example](./should-not-count.md)\n"
        "```\n"
        "After fence: [bar](./bar.md)\n"
    )
    links = check_links.extract_links(text)
    assert links == [("./foo.md", 1), ("./bar.md", 6)]


def test_check_internal_link_ok_when_target_exists(tmp_path):
    (tmp_path / "foo.md").write_text("hi")
    (tmp_path / "bar.md").write_text("[foo](./foo.md)")
    result = check_links.check_internal_link("./foo.md", tmp_path / "bar.md", tmp_path)
    assert result is None


def test_check_internal_link_ok_when_target_with_fragment_exists(tmp_path):
    # ./foo.md#some-heading must resolve against foo.md on disk, not the
    # literal (nonexistent) path "foo.md#some-heading". Anchor links are
    # common in Docusaurus/MkDocs docs and must not false-flag.
    (tmp_path / "foo.md").write_text("# Some heading\n")
    (tmp_path / "bar.md").write_text("[foo](./foo.md#some-heading)")
    result = check_links.check_internal_link("./foo.md#some-heading", tmp_path / "bar.md", tmp_path)
    assert result is None


def test_check_internal_link_ok_for_same_page_anchor(tmp_path):
    # A pure "#anchor" link (no path) points within the same page — nothing
    # to resolve on disk, must not false-flag either.
    (tmp_path / "bar.md").write_text("[jump](#some-heading)")
    result = check_links.check_internal_link("#some-heading", tmp_path / "bar.md", tmp_path)
    assert result is None


def test_check_internal_link_root_relative_resolves_against_repo_root(tmp_path):
    # A root-relative link ("/docs/foo.md") must resolve against repo_root,
    # not source_file.parent — joining an absolute path onto a parent
    # directory silently drops the parent (pathlib semantics), so this used
    # to resolve against the filesystem root and false-flag as broken.
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "foo.md").write_text("hi")
    nested_source = tmp_path / "docs" / "guides" / "bar.md"
    nested_source.parent.mkdir()
    nested_source.write_text("[foo](/docs/foo.md)")
    result = check_links.check_internal_link("/docs/foo.md", nested_source, tmp_path)
    assert result is None


def test_check_internal_link_root_relative_finding_when_target_missing(tmp_path):
    (tmp_path / "bar.md").write_text("[foo](/docs/missing.md)")
    result = check_links.check_internal_link("/docs/missing.md", tmp_path / "bar.md", tmp_path)
    assert result is not None
    assert result["layer"] == "reference"


def test_check_internal_link_finding_when_target_missing(tmp_path):
    (tmp_path / "bar.md").write_text("[foo](./missing.md)")
    result = check_links.check_internal_link("./missing.md", tmp_path / "bar.md", tmp_path)
    assert result is not None
    assert result["layer"] == "reference"
    assert "missing.md" in result["quote"]
    assert result["severity"] == "blocking"
    # No machine-safe replacement text exists for a broken link — this must
    # never be eligible for auto-fix regardless of confidence.
    assert result["auto_fixable"] is False


def test_check_external_link_ok_on_200(monkeypatch):
    monkeypatch.setattr(
        check_links, "_http_head",
        lambda url, timeout: mock.Mock(status=200),
    )
    result = check_links.check_external_link("https://example.com")
    assert result is None


def test_check_external_link_finding_on_404(monkeypatch):
    monkeypatch.setattr(
        check_links, "_http_head",
        lambda url, timeout: mock.Mock(status=404),
    )
    result = check_links.check_external_link("https://example.com/dead")
    assert result is not None
    assert result["severity"] == "blocking"
    assert result["auto_fixable"] is False


def test_no_redirect_handler_never_follows():
    # Confirmed against a real doc link (hub.traefik.io): urllib follows
    # redirects by default, all the way through a dashboard's OAuth login
    # flow, and judges the link "broken" based on wherever that chain
    # happens to land (a 404 at the auth boundary) rather than whether the
    # link itself resolves. A redirect to a login-gated page is a working
    # link, not a broken one — it must never be chased.
    assert check_links._NoRedirect().redirect_request(None, None, None, None, None, None) is None


def test_check_external_link_treats_redirect_as_not_broken(monkeypatch):
    def fake_head(url, timeout):
        raise urllib.error.HTTPError(url, 307, "Temporary Redirect", None, None)

    monkeypatch.setattr(check_links, "_http_head", fake_head)
    result = check_links.check_external_link("https://hub.traefik.io")
    assert result is None


def test_check_external_link_falls_back_to_get_when_head_rejected(monkeypatch):
    # Some servers (GitHub, various CDN-fronted doc sites) reject HEAD with
    # 403/405 while GET works fine — must retry with GET before concluding
    # the link is actually dead.
    def fake_head(url, timeout):
        raise urllib.error.HTTPError(url, 405, "Method Not Allowed", None, None)

    monkeypatch.setattr(check_links, "_http_head", fake_head)
    monkeypatch.setattr(check_links, "_http_get", lambda url, timeout: mock.Mock(status=200))
    result = check_links.check_external_link("https://example.com/head-rejected")
    assert result is None


def test_check_external_link_reports_broken_when_get_fallback_also_fails(monkeypatch):
    def fake_head(url, timeout):
        raise urllib.error.HTTPError(url, 403, "Forbidden", None, None)

    def fake_get(url, timeout):
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)

    monkeypatch.setattr(check_links, "_http_head", fake_head)
    monkeypatch.setattr(check_links, "_http_get", fake_get)
    result = check_links.check_external_link("https://example.com/really-dead")
    assert result is not None
    assert result["auto_fixable"] is False


def test_check_external_link_marks_unchecked_on_network_error(monkeypatch):
    def _raise(url, timeout):
        raise OSError("network unreachable")
    monkeypatch.setattr(check_links, "_http_head", _raise)
    result = check_links.check_external_link("https://example.com")
    # Network failures must never be reported as broken links (spec error-handling rule).
    assert result is None


def test_is_non_checkable_recognizes_mailto_and_tel():
    assert check_links._is_non_checkable("mailto:sales@traefik.io") is True
    assert check_links._is_non_checkable("tel:+15555555555") is True
    assert check_links._is_non_checkable("./foo.md") is False
    assert check_links._is_non_checkable("https://example.com") is False


def test_run_skips_mailto_links_instead_of_false_flagging_as_broken(tmp_path):
    # mailto: has no filesystem or HTTP target to check — before this was
    # excluded, it fell through to check_internal_link (the only other
    # branch), which joined it onto the source file's directory as if it
    # were a relative path and always found nothing there. Found via real
    # mailto: links in hub-doc's kubernetes/installation.md.
    doc = tmp_path / "page.md"
    doc.write_text("Contact [sales](mailto:sales@traefik.io) for licensing.\n")
    findings = check_links.run([doc], tmp_path)
    assert findings == []


def test_run_aggregates_findings_across_files(tmp_path, monkeypatch):
    doc = tmp_path / "page.md"
    doc.write_text("[dead](./nope.md)\n")
    monkeypatch.setattr(check_links, "_http_head", lambda url, timeout: mock.Mock(status=200))
    findings = check_links.run([doc], tmp_path)
    assert len(findings) == 1
    assert findings[0]["file"] == str(doc)


def test_run_caches_external_link_checks_across_files(tmp_path, monkeypatch):
    # The same third-party reference commonly appears on many pages —
    # re-checking it once per occurrence multiplies network calls for no
    # benefit and risks rate-limiting on a real run.
    doc_a = tmp_path / "a.md"
    doc_b = tmp_path / "b.md"
    doc_a.write_text("[dup](https://example.com/shared)\n")
    doc_b.write_text("[dup again](https://example.com/shared)\n")

    call_count = {"n": 0}

    def fake_head(url, timeout):
        call_count["n"] += 1
        return mock.Mock(status=200)

    monkeypatch.setattr(check_links, "_http_head", fake_head)
    findings = check_links.run([doc_a, doc_b], tmp_path)
    assert findings == []
    assert call_count["n"] == 1  # checked once despite appearing in 2 files


def test_run_reports_cached_broken_link_at_each_occurrence(tmp_path, monkeypatch):
    # Caching the result must not corrupt per-occurrence file/line — a
    # broken link cached from file A still needs to be reported at its own
    # correct location when it recurs in file B.
    doc_a = tmp_path / "a.md"
    doc_b = tmp_path / "b.md"
    doc_a.write_text("[dup](https://example.com/dead)\n")
    doc_b.write_text("line one\n[dup again](https://example.com/dead)\n")

    monkeypatch.setattr(check_links, "_http_head", lambda url, timeout: mock.Mock(status=404))
    findings = check_links.run([doc_a, doc_b], tmp_path)
    assert len(findings) == 2
    locations = {(f["file"], f["line"]) for f in findings}
    assert locations == {(str(doc_a), 1), (str(doc_b), 2)}


def test_main_prints_json_findings(tmp_path, monkeypatch, capsys):
    import json
    doc = tmp_path / "page.md"
    doc.write_text("[dead](./nope.md)\n")
    monkeypatch.setattr(check_links, "_http_head", lambda url, timeout: mock.Mock(status=200))
    exit_code = check_links.main([str(doc), "--repo-root", str(tmp_path)])
    assert exit_code == 0
    findings = json.loads(capsys.readouterr().out)
    assert len(findings) == 1
