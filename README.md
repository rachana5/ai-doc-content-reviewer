# doc-content-reviewer

A Claude Code plugin that audits *existing* documentation in `hub-doc`
(Traefik Hub) and `traefik/traefik` (Traefik Proxy) — not drafting new pages,
checking what's already published. Point it at a page, a section, or a
specific claim, and it reports back what's actually wrong, with sources.

## What it checks

Four independent layers, each looking for a different kind of problem:

- **Accuracy** — does the page's claim still match the source code? Default
  values, parameter types, "requires a license," "only available in
  Kubernetes mode" — anything checkable against `traefik-hub`'s or
  `traefik/traefik`'s actual Go source, not just plausible-sounding.
- **Style** — Vale/alex where a rule exists for it, plus a qualitative pass
  for what a linter can't judge (voice, terminology drift, whether a term
  the doc set uses inconsistently has a canonical answer anywhere).
- **Reference** — do the links actually resolve? Internal relative paths
  checked against the filesystem, external URLs checked live, with real
  network requests — not a static crawl that goes stale.
- **Clarity** — passive voice, ambiguous pronouns, one sentence doing three
  jobs, judged against how this docs' actual readers read (scanning for
  headings/bold/code, not reading start to finish).

## Two ways to invoke it

- **Full review** — `/content-reviewer docs/api-gateway/setup/kubernetes` —
  runs all four layers across every file in scope.
- **Targeted check** — `/content-reviewer is the rate-limiting default
  documented correctly?` — runs only the layer(s) the question actually
  implicates (usually accuracy), scoped to just the files that mention it.

## How a review actually goes

1. **Report.** One finding list, grouped by layer, each with its own
   confidence and severity — not one blended "here's what I think" pass.
   Leads with a one-line summary before the detail.
2. **Diff, not prose.** Every fix it can make is shown as an actual diff
   before anything is touched, grouped per file with the reasoning right
   next to the change it explains.
3. **Confirm.** "Apply all N auto-fixable fixes across M files?" is the
   fast path; picking specific ones by number or applying none are both
   just as available. Nothing lands on disk without this.
4. **PR, only on yes.** A separate, explicit gate after the fixes are
   applied — never bundled into the confirm step above.

Auto-fix is confidence-gated: a finding only gets offered as one-click-apply
when it's an exact, literal text swap the agent is highly confident about
(a wrong Helm chart name, a misspelled word, the wrong Kubernetes term).
Anything that needs actual judgment — an ambiguous pronoun, a passive-voice
rewrite — stays a suggestion for a human to act on by hand.

## Install

```bash
claude plugin marketplace add rachana5/ai-doc-content-reviewer
claude plugin install doc-content-reviewer
```

Needs Python 3.11+, `gh` authenticated, and (optionally — the style layer
degrades gracefully without them) `vale` and `alex` on `PATH`.

## Verified against real content

Beyond its own test suite, this has been run against real `hub-doc` and
`traefik` content, not just fixtures — a full review of hub-doc's API
Gateway Kubernetes setup pages went all the way through the confirm/apply/PR
steps and produced a real PR: 2 blocking findings (a Helm command
referencing a chart that doesn't exist), 4 suggestions, on
[rachana5/hub-doc#2](https://github.com/rachana5/hub-doc/pull/2). Those
runs, plus two earlier scoped checks, surfaced and fixed 7 real bugs along
the way — link-checker false positives against a real site's bot
protection, a crash on valid CommonMark syntax, and a line-vs-substring
replacement bug in the module that writes to disk. See `git log` for the
detail on each.

## Development

```bash
make test
```

Design: `docs/superpowers/specs/2026-08-28-content-reviewer-design.md` in the
`automation` workspace. Plan: `docs/superpowers/plans/2026-08-28-content-reviewer-implementation.md`.
