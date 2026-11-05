# Accuracy layer checklist

Goal: verify the doc's factual and behavioral claims against the source code in this
repository (`traefik/traefik`).

## Scope

Check claims about what this PR changes, not every claim on the page. On the PR's changed
lines, check every claim. On the rest of a changed page and on pages the PR does not edit
(`references/affected-docs-checklist.md`), check only claims about the PR's change set,
including a sentence far from the edit that the change now contradicts. A wrong claim about
something the PR did not touch is out of scope: do not report it.

## What counts as a claim to check

- Default values, valid ranges, and types for any configuration field, flag,
  or parameter.
- Statements about what a feature does, when it triggers, and what it
  depends on (e.g. "only available in Kubernetes mode").
- Statements that something is deprecated, experimental, or GA.
- Code samples that must actually compile/run against the current API.
- A diagram of an interaction sequence: check each arrow against the source, like a prose claim.
- In a multi-step chained example, whether the heading number, the code
  example's own identifier (a Kubernetes `metadata.name`, a config key),
  and every later reference to that step by number all agree with each
  other — this is a direct, checkable-without-source-code comparison, not
  a judgment call, so treat a mismatch as a real finding on its own.

- A claim about what a user, a client or Traefik can do, forwards or applies: find the option or
  default that gates it and check the claim in the default configuration. When you cite a source line
  for a sentence or a table row, read the branch around that line and list the conditions the statement
  holds under. A statement that is true in only one case is a finding; name the case.
- A constant or type name that only config structs and tests reference is not evidence of behavior.
  Find a reader of it outside the tests before you cite it as the source.
- Several examples for one concept (the formats of a page, a set of snippets): check each against the
  same inputs the page's main example handles. A sibling that rejects or breaks an input the main
  example accepts is an accuracy finding, not a completeness one.
- A version the page states ("available since v3.6", "removed in v3.7"): find the commit that introduced
  or removed the behavior (`git log -S<symbol>`) and the first tag that contains it (`git tag --contains`),
  and check the page against it. When you cannot tell, report the claim as `unverifiable`.

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
5. Check the branch the PR targets, not just the default branch. Proxy
   fixes land on a maintenance branch (for example `v3.7`) and are merged
   forward into `master`, so a field, default, or behavior can differ
   between them. For a PR, the code at the PR head is the primary evidence;
   use the base branch for anything the PR didn't touch.
6. A claim about a third-party service's runtime behavior (a DNS provider or ACME server accepts or
   rejects something) cannot be checked against this repository. Treat it as "unverifiable" per
   step 4 unless the doc cites where the behavior was confirmed (a linked vendor doc).

## Confidence calibration

- 0.9+: you found the exact field/default in source and it unambiguously
  contradicts the doc. A finding below 0.8 is listed after the confirmed ones.
- 0.5–0.8: behavior looks likely wrong but involves some interpretation
  (e.g. a version-gated default, or docs describing a superset of configs).
- <0.5: you couldn't find corroborating source at all — flag as
  unverifiable, do not guess at a fix.

## Example

**Doc text:** "| `maxRequestBodyBytes` | ... | 1MB | No |"
**Source:** `pkg/config/dynamic/middlewares.go:17`: `RetryDefaultMaxRequestBodyBytes = 2 * 1024 * 1024`

```json
{
  "layer": "accuracy",
  "rule": "Accuracy: default value",
  "quote": "| 1MB | No |",
  "reasoning": "The default is 2 MB. RetryDefaultMaxRequestBodyBytes is 2 * 1024 * 1024 (pkg/config/dynamic/middlewares.go:17) and pkg/middlewares/retry/retry.go:109 uses it when the option is unset.",
  "suggested_fix": "| 2MB | No |",
  "severity": "suggestion",
  "impact": "high",
  "confidence": 0.95
}
```
