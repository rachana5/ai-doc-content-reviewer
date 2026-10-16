# Affected-docs checklist

Goal: for every page `find_affected_docs.py` returned, decide whether the PR's change makes
something on it wrong, incomplete, or newly linkable. The PR does not have to edit the page.
A contributor who updates a middleware guide and forgets its reference table is the case this
checklist exists for.

Stay inside the change set. A page is in scope only for what it says about the terms this PR
changes. Do not report an unrelated error, a style nit, or an unclear sentence elsewhere on the
page, even if you see one. If the PR already edits the page (`in_pr: true`), the same rule
applies to the lines it did not change.

## For each candidate page

1. **Read the hits in context**, not just the matched line. Open the page and read the section
   around each hit. Skip a hit that only names the term in passing.
2. **Contradiction (accuracy).** Does the page state a default, valid value, type, behavior,
   requirement, or deprecation that the PR's code diff now makes false? A removed or renamed
   option still documented here counts. Verify against the code at the PR head, never against
   what the PR description says. `severity: blocking` only when the page is in the PR's
   changed lines; findings on pages or lines the PR did not change are capped to `suggestion`
   in Step 4.
3. **Gap (completeness).** Does this page list the same kind of thing (an options table, a
   per-format example, a supported-values list) where the new or changed item belongs but is
   missing? Check every format the page shows. Never suggest text for a generated file
   (`generated: true`): the fix is the Go struct comment plus `make generate`.
4. **Pointer (reference).** If the PR renamed or removed a heading or page, does this page link
   or anchor to it? Run `check_links.py` on this page and keep only findings whose broken target
   this PR changed; set `affected: true` on them. Leave every other dead link alone.
5. **Same fact, same finding.** If the PR's own page and an affected page share one problem (the
   old default written in both), emit one finding per page, and give them the same `group`
   value (the option name in backticks) so they can be grouped when the comment gets long.

## Setting `group`

Set `group` to the option, field, or middleware the finding is about, in backticks (for example
`` `maxBurst` ``), whenever the PR changes that item and you raise more than one finding about
it. Use the same string for every finding about it. Leave it unset otherwise. Link findings from
the reference layer group together without it. Grouping only happens when the comment has eight or more
suggestions, and it never hides a finding.

## Calibration

- 0.8+: the page states the old value verbatim and the code diff shows the change.
- 0.5 to 0.79: the page covers the feature but not the changed detail, or the code evidence is indirect.
- Below 0.5: do not report.
- Never report that an affected page is correct.

## Example

The PR changes the `maxBackoff` default from `5s` to `10s` in the retry middleware and edits only
the retry guide. The reference page still lists the old default.

```json
{
  "layer": "accuracy",
  "file": "docs/content/reference/routing-configuration/http/middlewares/retry.md",
  "line": 58,
  "quote": "| maxBackoff | Upper bound for the wait between attempts. | 5s | No |",
  "rule": "Accuracy: default value",
  "reasoning": "The PR changes the default to 10s (pkg/middlewares/retry/retry.go:41), but this table still lists 5s. This page is not part of the PR.",
  "suggested_fix": "| maxBackoff | Upper bound for the wait between attempts. | 10s | No |",
  "severity": "suggestion",
  "confidence": 0.9,
  "auto_fixable": false,
  "group": "`maxBackoff`",
  "affected": true
}
```
