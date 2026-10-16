# Finding schema

Every review layer (accuracy, style, reference, clarity, completeness) emits findings in
exactly this shape. This is the contract `aggregate.py` merges and `post_review.py`
renders; don't invent a different shape per layer. This skill never applies fixes, so
`auto_fixable` is always `false`.

```json
{
  "layer": "accuracy",
  "file": "docs/content/reference/routing-configuration/http/middlewares/retry.md",
  "line": 101,
  "quote": "| 1MB | No |",
  "rule": "Accuracy: default value",
  "reasoning": "The default is 2 MB (pkg/config/dynamic/middlewares.go:17), not 1 MB.",
  "suggested_fix": "| 2MB | No |",
  "severity": "blocking",
  "confidence": 0.95,
  "auto_fixable": false
}
```

- A finding describes a **problem** the author should act on. Never emit a finding that confirms something is correct, and never emit one whose fix is a matter of taste with no rule or evidence behind it. If a layer finds nothing, it writes `[]`.
- `layer`: one of `accuracy`, `style`, `reference`, `clarity`, `completeness`.
- `quote`: the exact doc text the finding is about — copy it verbatim, don't paraphrase. This is what makes a finding checkable at a glance instead of a vague flag. For a missing-docs finding there is no doc text yet: quote the code change that creates the gap (`path:line: what changed`).
- `rule`: a short label (at most 80 characters) naming the rule or check this finding breaks. It is the only text shown next to the file name in the collapsed row of the comment, so make it specific: `Style guide: Words and Phrases to Avoid`, `Style guide: Voice`, `Accuracy: default value`, `Broken link`, `Missing docs: new maxBackoff option`. Use the style guide's own section names. Optional (falls back to the layer name), but always set it.
- `reasoning`: what is wrong, in one to three plain sentences, shown under "What's wrong" in the expanded comment and never truncated. Include the concrete pointer (a `file:line` in source, the missing link target). Don't repeat the rule label, don't start with "Style guide, ...", and don't write the fix here.
- `suggested_fix`: the literal replacement text for `quote`, never an instruction like "Change X to Y". The comment shows a single-line `quote` and `suggested_fix` as a before/after diff, so an instruction would read as text to paste. For a missing-docs finding, or a fix that needs surrounding explanation, write ready-to-paste prose or markdown instead (it is shown as a quote plus the text). When there is no safe replacement, use `(needs a human to ...)`. Every finding needs one, even flag-only ones — a human still benefits from seeing the proposed fix even if it isn't auto-applied.
- `severity`: `blocking` (factual/structural — wrong value, broken link, missing required section) vs `suggestion` (style/clarity nits).
- `confidence`: your calibrated confidence, 0.0 to 1.0, that this finding is correct and the fix is right. Be conservative.
- `auto_fixable`: always `false`.
- `group` (optional): a short label naming the option, field, or middleware the finding is about, in backticks (`` `maxBurst` ``). Findings that share the value can be shown as one collapsed row when the comment has eight or more suggestions. Blocking findings are never grouped, whatever their `group`. Link findings from the reference layer group together without it.
- `affected` (optional boolean): `true` when the finding is on a page, or about a link, that the PR did not change but the PR's change makes wrong. It keeps a reference finding outside the diff from being dropped. Severity outside the diff is still capped to `suggestion`.
