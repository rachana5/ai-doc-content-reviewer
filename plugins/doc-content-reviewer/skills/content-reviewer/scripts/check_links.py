"""check_links.py — reference layer, mechanical part.

Resolves internal relative links against the filesystem and checks external
URLs return a non-error status. Network failures are marked unchecked, never
reported as broken (see spec's error-handling section) — a flaky network
must never produce a false "dead link" finding.
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
import urllib.error
from pathlib import Path

from scripts._finding import make_finding

_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_INLINE_CODE_SPAN_RE = re.compile(r"`[^`]*`")

# Findings from this module never carry real replacement text — a broken
# link needs a human to identify the correct target/URL, there is no safe
# machine-generated fix. These must never be auto-applied regardless of how
# high their confidence is, so every make_finding() call here passes this
# explicitly rather than relying on the confidence-threshold default.
_NO_SAFE_AUTOFIX = False


def extract_links(markdown_text: str) -> list[tuple[str, int]]:
    links: list[tuple[str, int]] = []
    in_fence = False
    for lineno, line in enumerate(markdown_text.splitlines(), start=1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        # Strip inline code spans first so link syntax shown as a literal
        # example (docs-about-docs, config snippets) isn't mistaken for a
        # real link.
        searchable = _INLINE_CODE_SPAN_RE.sub("", line)
        for match in _LINK_RE.finditer(searchable):
            links.append((match.group(1), lineno))
    return links


def _is_external(target: str) -> bool:
    return target.startswith("http://") or target.startswith("https://")


def check_internal_link(link_target: str, source_file: Path, repo_root: Path) -> dict | None:
    # Strip a #fragment before resolving against the filesystem — "./foo.md#heading"
    # is a valid link to foo.md, not a literal path ending in "#heading", and a
    # pure "#heading" same-page anchor has no filesystem target to check at all.
    #
    # Known limitation, deliberately not handled: this only verifies the
    # FILE exists — it never checks that "#heading" is still a real heading
    # in that file. Verifying that would mean reproducing the target site
    # generator's slug algorithm (Docusaurus and MkDocs each slugify
    # headings differently), and getting that wrong would produce new false
    # "broken anchor" positives — worse than the current gap. Left as an
    # explicit, documented limitation rather than a best-effort heuristic.
    path_part, _, _fragment = link_target.partition("#")
    if not path_part:
        return None
    resolved = (source_file.parent / path_part).resolve()
    if resolved.exists():
        return None
    return make_finding(
        layer="reference", file=str(source_file), line=0,
        quote=link_target,
        reasoning=f"Relative link target does not exist on disk: {resolved}",
        suggested_fix="(needs a human to identify the correct target)",
        severity="blocking", confidence=0.95, auto_fixable=_NO_SAFE_AUTOFIX,
    )


def _http_head(url: str, timeout: float):
    request = urllib.request.Request(url, method="HEAD")
    return urllib.request.urlopen(request, timeout=timeout)


def _http_get(url: str, timeout: float):
    request = urllib.request.Request(url, method="GET")
    return urllib.request.urlopen(request, timeout=timeout)


def _broken_link_finding(url: str, status: int) -> dict:
    return make_finding(
        layer="reference", file="", line=0, quote=url,
        reasoning=f"External URL returned HTTP {status}",
        suggested_fix="(needs a human to find the current URL)",
        severity="blocking", confidence=0.9, auto_fixable=_NO_SAFE_AUTOFIX,
    )


def check_external_link(url: str, *, timeout: float = 10.0) -> dict | None:
    try:
        response = _http_head(url, timeout)
    except urllib.error.HTTPError as exc:
        if exc.code in (403, 405):
            # Some servers reject HEAD outright (GitHub and various
            # CDN-fronted doc sites among them) while GET works fine —
            # retry before concluding the link is actually broken.
            try:
                response = _http_get(url, timeout)
            except urllib.error.HTTPError as exc2:
                if 400 <= exc2.code < 600:
                    return _broken_link_finding(url, exc2.code)
                return None
            except OSError:
                return None
        elif 400 <= exc.code < 600:
            return _broken_link_finding(url, exc.code)
        else:
            return None
    except OSError:
        # Network unreachable, DNS failure, timeout, etc. — unchecked, not broken.
        return None
    status = getattr(response, "status", 200)
    if 400 <= status < 600:
        return _broken_link_finding(url, status)
    return None


def run(target_files: list[Path], repo_root: Path) -> list[dict]:
    findings: list[dict] = []
    # Cache external-link results per URL for this run: the same third-party
    # reference commonly appears across many pages, and re-checking it once
    # per occurrence multiplies slow network calls and rate-limit risk for
    # no benefit — the answer doesn't change within a single run.
    external_cache: dict[str, dict | None] = {}
    for file in target_files:
        text = file.read_text()
        for target, lineno in extract_links(text):
            if _is_external(target):
                if target not in external_cache:
                    external_cache[target] = check_external_link(target)
                cached = external_cache[target]
                # Copy before annotating with this occurrence's file/line —
                # the same cached dict is reused across every occurrence of
                # this URL, so mutating it in place would corrupt earlier
                # occurrences' recorded locations.
                finding = dict(cached) if cached is not None else None
            else:
                finding = check_internal_link(target, file, repo_root)
            if finding is not None:
                finding["file"] = str(file)
                finding["line"] = lineno
                findings.append(finding)
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+")
    parser.add_argument("--repo-root", required=True)
    args = parser.parse_args(argv)
    findings = run([Path(f) for f in args.files], Path(args.repo_root))
    print(json.dumps(findings))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
