# doc-content-reviewer

MVP Claude Code plugin: a single `content-reviewer` skill that audits existing
`hub-doc` / `traefik` (Proxy) documentation across four independent layers —
accuracy (vs. source code), style, reference/link checks, and clarity — and
produces one report with confidence-gated auto-fix and an optional PR.

Design: `docs/superpowers/specs/2026-08-28-content-reviewer-design.md` in the
`automation` workspace. Plan: `docs/superpowers/plans/2026-08-28-content-reviewer-implementation.md`.

## Development

```bash
make test
```

## What the test suite protects

114 tests, organized by what breaks if each one fails, not just "does it
pass":

| File | What it protects against |
|---|---|
| `check_links.py` | The reference layer wrongly calling a real link broken, or missing an actually broken one |
| `run_style_lint.py` | Vale/alex output getting mistranslated into findings, or a crashed lint tool silently reporting "clean" instead of "didn't run" |
| `aggregate.py` | Findings from the four layers merging into a wrong report: miscounted totals, a dropped finding, wrong dedup |
| `apply_fixes.py` | The highest-stakes module, since it's the one that writes to real files. Confirms it does nothing without `--apply`, and only ever touches auto-fixable, high-confidence findings |
| `open_pr.py` | The plugin ever opening a PR without an explicit yes from the user |
| `_discover.py` | Finding the wrong `traefik-hub` clone or repo root, and grading a page's accuracy against the wrong source |
| `_finding.py` | A malformed finding sneaking past validation and breaking the report silently, instead of failing loudly at the layer boundary |
| `setup.py`, `_git.py`/`_gh.py` | Preflight wrongly reporting "all good" when Python, `gh`, Vale, or alex aren't actually usable |
| structure/token-budget tests | `SKILL.md` staying internally consistent, and the bundled reference files staying small enough that loading them doesn't blow the agent's context |

The short version: the write path (`apply_fixes`, `open_pr`) can't act
without explicit user confirmation, and the read path (links, style,
discovery, aggregation) can't silently misreport.

## Verified against real content

Tests alone don't catch everything a linter can't simulate: a real WAF, real
CommonMark edge cases, real doc prose. Two demo runs against actual
`hub-doc`/`traefik` content surfaced 3 real bugs, all fixed with regression
tests added:

- **Root-relative links** (`/docs/foo.md`) were resolved against the
  filesystem root instead of the repo root, false-flagging every one as
  broken.
- **Markdown link titles** (`[text](url "title")`, valid CommonMark and used
  in real traefik docs) leaked into the link target, crashing the checker
  instead of degrading gracefully like every other failure mode.
- **Missing User-Agent header** on external link checks meant `urllib`'s
  default UA got a flat 403 from `traefik.io`'s own bot protection,
  false-flagging every link into that domain as broken.

Same two runs also produced clean, correct results where the content was
actually fine: a full defaults table on hub-doc's RateLimit middleware
page, checked against the real Go source, came back with zero findings.
