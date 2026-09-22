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
