# Accuracy layer checklist

Goal: verify the doc's factual/behavioral claims against the actual source
code (`traefik-hub` for Hub docs, `traefik/traefik` for Proxy docs).

## What counts as a claim to check

- Default values, valid ranges, and types for any configuration field, flag,
  or parameter.
- Statements about what a feature does, when it triggers, and what it
  depends on (e.g. "requires a license," "only available in Kubernetes mode").
- Statements that something is deprecated, experimental, or GA.
- Code samples that must actually compile/run against the current API.
- A diagram depicting an interaction sequence (a sign-in flow, a token
  exchange, a handshake) — check each arrow against the source the same way
  a prose claim gets checked, and cross-check it against any diagram of the
  same established flow already published elsewhere in the doc set. A new,
  shortened diagram that doesn't match either source is a common way an
  inaccuracy slips in, since a compressed version of a flow is easy to get
  wrong in a way the full version wouldn't be.
- In a multi-step chained example, whether the heading number, the code
  example's own identifier (a Kubernetes `metadata.name`, a config key),
  and every later reference to that step by number all agree with each
  other — this is a direct, checkable-without-source-code comparison, not
  a judgment call, so treat a mismatch as a real finding on its own.

## Process

1. Identify every checkable claim in the target text (see above).
2. For each claim, locate the corresponding source: grep for the config
   struct/flag/field name, read the relevant function or default-value
   assignment, and note the exact `file:line`.
3. Compare. If they match, no finding. If they don't, or the field/flag no
   longer exists at all, produce a finding.
4. If no matching source can be found after a reasonable search (renamed,
   removed, or genuinely undocumented in code), still produce a finding —
   category "unverifiable" — rather than silently skipping it. Use
   `severity: suggestion` and `confidence` low enough that it won't
   auto-fix (an unverifiable claim should never be auto-rewritten).
5. Check the branch the feature actually ships from, not just the repo's
   default branch. A Hub feature documented under an Early Access badge
   often lives on a release branch (e.g. `v3.21`) ahead of, or diverged
   from, `main` — a field, default, or behavior can differ between them,
   and `main` can even be missing a fix that already shipped on the
   release branch. Confirm which branch the doc's own version/badge
   targets before treating `main` as ground truth.
6. If a claim traces back to a reviewer's or generator's own suggested
   wording rather than the doc author's, verify it against source
   independently rather than trusting it at face value — a suggestion
   written to fix one problem can introduce a new inaccuracy of its own,
   most often by merging two behaviorally distinct cases into one sentence
   that's only accurate for one of them. Treat every claim the same way
   regardless of who proposed the wording.
7. A claim about a specific third-party service's or identity provider's
   runtime behavior (accepts/rejects a parameter, requires a particular
   field) is not checkable against `traefik-hub` or `traefik/traefik`
   source at all — the source shows what Hub sends, not how an external
   server responds. Category it "unverifiable" per step 4 unless the doc
   itself cites where the behavior was confirmed (a dated test against a
   named vendor, a linked vendor doc) — a claim with that kind of citation
   can be treated as sourced, not unverifiable, since the citation is
   itself the independent source.

## Confidence calibration

- 0.9+: you found the exact field/default in source and it unambiguously
  contradicts the doc.
- 0.5–0.8: behavior looks likely wrong but involves some interpretation
  (e.g. a version-gated default, or docs describing a superset of configs).
- <0.5: you couldn't find corroborating source at all — flag as
  unverifiable, do not guess at a fix.

## Example

**Doc text:** "The default value for `maxRetries` is 3."
**Source:** `traefik-hub/middleware/retry.go:88` — `DefaultMaxRetries = 5`

```json
{
  "layer": "accuracy",
  "quote": "The default value for maxRetries is 3.",
  "reasoning": "traefik-hub source (middleware/retry.go:88) sets the default to 5, not 3.",
  "suggested_fix": "The default value for maxRetries is 5.",
  "severity": "blocking",
  "confidence": 0.9
}
```
