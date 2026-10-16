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
import unicodedata
import urllib.request
import urllib.error
from pathlib import Path

from scripts._finding import make_finding

# The target group allows one level of balanced parens so a URL containing
# a literal "(" / ")" (real-world example: a Wikipedia-style URL, or a path
# segment with a parenthetical) isn't truncated at the first ")" — matching
# CommonMark, which allows one level of nested parens in an unquoted link
# destination.
_LINK_RE = re.compile(r"\[[^\]]*\]\(((?:[^()]|\([^()]*\))*)\)")
_INLINE_CODE_SPAN_RE = re.compile(r"`[^`]*`")

# Findings from this module never carry real replacement text — a broken
# link needs a human to identify the correct target/URL, there is no safe
# machine-generated fix. These must never be auto-applied regardless of how
# high their confidence is, so every make_finding() call here passes this
# explicitly rather than relying on the confidence-threshold default.
_NO_SAFE_AUTOFIX = False


_LINK_TITLE_RE = re.compile(r'''\s+(?:"[^"]*"|'[^']*'|\([^)]*\))$''')


def _strip_link_title(target: str) -> str:
    # CommonMark allows an optional title after the URL, e.g.
    # [text](url "Link title") or [text](url 'Link title') — real content
    # uses this for accessible link text (see docs/content/index.md in the
    # traefik/traefik demo fork). Left in, the "url" half of the match
    # includes the quoted title, which corrupts both internal-path
    # resolution and (worse) crashes external HEAD requests with
    # http.client.InvalidURL — an uncaught exception, not the graceful
    # unchecked-on-network-failure path this module otherwise guarantees.
    return _LINK_TITLE_RE.sub("", target)


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
            links.append((_strip_link_title(match.group(1)), lineno))
    return links


def _is_external(target: str) -> bool:
    return target.startswith("http://") or target.startswith("https://")


# Schemes with no filesystem or HTTP target to check — a link like this
# falling through to check_internal_link (the only other branch) gets
# joined onto source_file.parent as if it were a relative path, which
# never exists on disk, producing a guaranteed false "broken link" finding
# for every single occurrence. Found via mailto: links in real hub-doc
# content (docs/api-gateway/setup/kubernetes/installation.md).
_NON_CHECKABLE_SCHEMES = ("mailto:", "tel:")

# Any OTHER explicit scheme (ftp:, data:, etc.) has the exact same failure
# mode as mailto:/tel: above -- it's not http(s), so _is_external misses
# it, and it's not a real filesystem path, so check_internal_link
# guarantees a false "broken link." This module has no way to check a
# non-http(s) scheme's target, so treat any of them as non-checkable
# rather than silently mis-resolving as a relative path.
_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def _is_non_checkable(target: str) -> bool:
    if target.startswith(_NON_CHECKABLE_SCHEMES):
        return True
    if target.startswith("//"):
        # Protocol-relative (e.g. "//cdn.example.com/foo.js") -- an
        # explicit external reference with no filesystem target, same
        # reasoning as the schemes above; distinct from a root-relative
        # internal link ("/docs/foo.md"), which check_internal_link
        # already resolves against repo_root correctly.
        return True
    if _SCHEME_RE.match(target) and not _is_external(target):
        return True
    return False


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
    # A root-relative link ("/docs/foo.md") resolves against repo_root, not
    # the source file's directory — joining an absolute path onto
    # source_file.parent would silently discard the parent (pathlib drops
    # everything before an absolute right-hand operand) and resolve against
    # the filesystem root instead, false-flagging every root-relative link
    # as broken.
    if path_part.startswith("/"):
        resolved = (repo_root / path_part.lstrip("/")).resolve()
    else:
        resolved = (source_file.parent / path_part).resolve()
    if resolved.exists():
        return None
    try:
        shown = resolved.relative_to(repo_root.resolve())  # repo-relative: no runner/home paths in a public comment
    except ValueError:
        shown = resolved
    return make_finding(
        layer="reference", file=str(source_file), line=0,
        quote=link_target,
        reasoning=f"Relative link target does not exist on disk: {shown}",
        suggested_fix="(needs a human to identify the correct target)",
        severity="blocking", confidence=0.95, auto_fixable=_NO_SAFE_AUTOFIX, rule="Broken link",
    )


# --- MkDocs mode -----------------------------------------------------------
# MkDocs (use_directory_urls, the default) serves docs/a/b/page.md at /a/b/page/
# and docs/a/b/index.md at /a/b/. Only links ending in ".md" are rewritten by
# MkDocs; any other relative link is left as-is and resolved by the BROWSER
# against the page's rendered URL. Resolving those against the source file's
# directory (the default mode above) false-flags every directory-style link.
_INDEX_NAMES = ("index.md", "README.md")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_ID_ATTR_RE = re.compile(r"""\bid\s*=\s*["']([^"']+)["']""")
_ATTR_LIST_RE = re.compile(r"\{[^}]*#([A-Za-z0-9_\-:.]+)[^}]*\}")
_INCLUDE_RE = re.compile(r"""\{%\s*include(?:-markdown)?\s+["']([^"']+)["'][^%]*%\}|--8<--\s*["']([^"']+)["']""")
_OTHER_TEMPLATE_RE = re.compile(r"\{%|\{\{")  # any template syntax left after includes are resolved


def _slugify(text: str) -> str:
    """python-markdown toc slugify: NFKD to ascii, drop non-word chars, lowercase, hyphenate."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text)


def _heading_text(raw: str) -> str:
    raw = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", raw)   # [text](url) -> text
    raw = re.sub(r"<[^>]+>", "", raw)                         # inline html
    raw = raw.replace("`", "")
    raw = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", raw)    # emphasis
    return _ATTR_LIST_RE.sub("", raw).strip()


def _strip_fences(text: str) -> str:
    out, in_fence = [], False
    for line in text.splitlines():
        if line.strip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def _resolve_includes(text: str, page_dir: Path | None, docs_root: Path | None) -> str | None:
    """Inline include-markdown / snippet includes so their anchors count.
    Returns None if any include cannot be found or other template syntax
    remains, because then a missing anchor can't be proven missing."""
    def find(name: str) -> str | None:
        for base in (docs_root, page_dir):
            if base is not None and (base / name).is_file():
                return (base / name).read_text(encoding="utf-8")
        return None

    for _ in range(2):  # includes inside includes, one extra level
        missing = False

        def sub(m: re.Match) -> str:
            nonlocal missing
            body = find(m.group(1) or m.group(2))
            if body is None:
                missing = True
                return ""
            return body

        text = _INCLUDE_RE.sub(sub, text)
        if missing:
            return None
    if _OTHER_TEMPLATE_RE.search(_strip_fences(text)):
        return None
    return text


def collect_anchors(markdown_text: str, *, page_dir: Path | None = None,
                    docs_root: Path | None = None) -> set[str] | None:
    """All anchors a page defines: heading slugs (with python-markdown's _1, _2
    duplicate suffixes), explicit id="..." attributes, and {#id} attr lists,
    including those from include-markdown / snippet includes. Returns None when
    the page uses template syntax this checker can't expand."""
    resolved = _resolve_includes(markdown_text, page_dir, docs_root)
    if resolved is None:
        return None
    markdown_text = resolved
    anchors: set[str] = set(_ID_ATTR_RE.findall(markdown_text))
    seen: dict[str, int] = {}
    in_fence = False
    for line in markdown_text.splitlines():
        if line.strip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING_RE.match(line)
        if not m:
            continue
        explicit = _ATTR_LIST_RE.search(m.group(2))
        if explicit:
            anchors.add(explicit.group(1))
            continue
        slug = _slugify(_heading_text(m.group(2)))
        if not slug:
            continue
        n = seen.get(slug, 0)
        seen[slug] = n + 1
        anchors.add(slug if n == 0 else f"{slug}_{n}")
    return anchors


def _mkdocs_page_dir(source_file: Path) -> Path:
    """Directory the browser resolves relative URLs against for this page."""
    if source_file.name in _INDEX_NAMES:
        return source_file.parent
    return source_file.parent / source_file.stem


def _mkdocs_target_file(path_part: str, source_file: Path, docs_root: Path) -> Path | None:
    """Resolve a link path to the markdown file (or asset) it serves, or None."""
    if path_part.startswith("/"):
        base = docs_root / path_part.lstrip("/")
    elif path_part.endswith(".md"):
        base = source_file.parent / path_part              # rewritten by MkDocs
    elif (source_file.parent / path_part.rstrip("/")).resolve().is_file():
        # Media/asset files (png, yml, ...) are also rewritten by MkDocs,
        # relative to the SOURCE file, not the rendered page URL.
        return (source_file.parent / path_part.rstrip("/")).resolve()
    else:
        base = _mkdocs_page_dir(source_file) / path_part   # resolved by the browser
    base = Path(str(base).rstrip("/")) if path_part.endswith("/") else base
    candidates = [base]
    if base.suffix != ".md":
        candidates += [Path(str(base) + ".md")] + [base / n for n in _INDEX_NAMES]
    for c in candidates:
        c = c.resolve()
        if c.is_file():
            return c
    return None


def check_internal_link_mkdocs(link_target: str, source_file: Path, repo_root: Path,
                               docs_root: Path) -> dict | None:
    path_part, _, fragment = link_target.partition("#")
    if path_part:
        target = _mkdocs_target_file(path_part, source_file, docs_root)
        if target is None:
            # An existing directory with no index page still means the link is wrong in MkDocs.
            return make_finding(
                layer="reference", file=str(source_file), line=0, quote=link_target,
                reasoning=f"Link does not resolve to a page in the built site: {path_part}",
                suggested_fix="(needs a human to identify the correct target)",
                severity="blocking", confidence=0.9, auto_fixable=_NO_SAFE_AUTOFIX, rule="Broken link",
            )
    else:
        target = source_file.resolve()
    if not fragment or target.suffix != ".md":
        return None
    try:
        anchors = collect_anchors(target.read_text(encoding="utf-8"),
                                  page_dir=target.parent, docs_root=docs_root)
    except (OSError, UnicodeDecodeError):
        return None
    if anchors is None or fragment in anchors or fragment.lower() in anchors:
        return None
    try:
        shown = target.relative_to(repo_root.resolve())
    except ValueError:
        shown = target
    near = sorted(a for a in anchors if fragment.lower()[:6] in a)[:3]
    hint = f" Similar anchors on that page: {', '.join(near)}." if near else ""
    return make_finding(
        layer="reference", file=str(source_file), line=0, quote=link_target,
        reasoning=f"Anchor #{fragment} does not exist in {shown}.{hint}",
        suggested_fix="(needs a human to pick the correct anchor)",
        severity="blocking", confidence=0.8, auto_fixable=_NO_SAFE_AUTOFIX, rule="Broken anchor",
    )


# urllib's default User-Agent ("Python-urllib/x.y") gets a flat 403 from
# some sites' bot protection (confirmed against https://traefik.io itself —
# curl with a browser UA gets a clean 308 redirect, urllib with no UA gets
# 403). Without this, every link into such a domain reads as "broken"
# regardless of the retry-on-403 logic below, since the GET retry would hit
# the same UA-based block. A generic browser UA is enough to pass; this
# isn't trying to impersonate a specific browser, just avoid looking like a
# bot to a WAF that only checks for one.
_USER_AGENT = "Mozilla/5.0 (compatible; doc-content-reviewer-link-check/1.0)"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    # Confirmed against a real doc link (hub.traefik.io): urllib follows
    # redirects by default, all the way through a dashboard's OAuth login
    # flow, and judges the link "broken" based on wherever that chain
    # happens to land (a 404 at the auth boundary) — not whether the link
    # itself resolves. A 3xx response IS a working link (that's what a
    # redirect to a login-gated page looks like for any anonymous client,
    # docs reader included); it should never be chased. Returning None here
    # tells urllib not to follow — the 3xx then surfaces as an HTTPError
    # that check_external_link's `else: return None` branch below already
    # treats as "not broken," so no other change was needed.
    def redirect_request(self, *args, **kwargs):
        return None


_opener = urllib.request.build_opener(_NoRedirect)


def _http_head(url: str, timeout: float):
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": _USER_AGENT})
    return _opener.open(request, timeout=timeout)


def _http_get(url: str, timeout: float):
    request = urllib.request.Request(url, method="GET", headers={"User-Agent": _USER_AGENT})
    return _opener.open(request, timeout=timeout)


def _broken_link_finding(url: str, status: int) -> dict:
    return make_finding(
        layer="reference", file="", line=0, quote=url,
        reasoning=f"External URL returned HTTP {status}",
        suggested_fix="(needs a human to find the current URL)",
        severity="blocking", confidence=0.9, auto_fixable=_NO_SAFE_AUTOFIX, rule="Broken link",
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


def run(target_files: list[Path], repo_root: Path, *, engine: str = "files",
        docs_root: Path | None = None) -> list[dict]:
    findings: list[dict] = []
    # Cache external-link results per URL for this run: the same third-party
    # reference commonly appears across many pages, and re-checking it once
    # per occurrence multiplies slow network calls and rate-limit risk for
    # no benefit — the answer doesn't change within a single run.
    external_cache: dict[str, dict | None] = {}
    for file in target_files:
        try:
            # Pin the encoding explicitly: a C-locale CI box (LANG=C / no
            # locale configured, common on minimal container images) would
            # otherwise decode via ASCII instead of UTF-8 -- a raw
            # UnicodeDecodeError on any non-ASCII byte in doc content
            # (accented names, smart quotes, emoji are all routine here)
            # instead of degrading gracefully like every other failure mode
            # in this module.
            text = file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            print(f"[check_links] WARNING: could not read {file} ({exc!r}) — skipping this file, continuing")
            continue
        for target, lineno in extract_links(text):
            if _is_non_checkable(target):
                continue
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
                if engine == "mkdocs":
                    finding = check_internal_link_mkdocs(target, file, repo_root, docs_root or repo_root)
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
    parser.add_argument("--engine", choices=["files", "mkdocs"], default="files",
                        help="'mkdocs' resolves directory-style URLs like the built site and checks #anchors")
    parser.add_argument("--docs-root", default=None, help="docs directory (mkdocs mode), e.g. docs/content")
    args = parser.parse_args(argv)
    root = Path(args.repo_root)
    findings = run([Path(f) for f in args.files], root, engine=args.engine,
                   docs_root=(root / args.docs_root) if args.docs_root else root)
    print(json.dumps(findings))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
