# Finding schema

Every review layer (accuracy, style, reference, clarity) emits findings in
exactly this shape. This is the contract `aggregate.py` merges and
`apply_fixes.py` stages fixes from — don't invent a different shape per layer.

```json
{
  "layer": "accuracy",
  "file": "docs/api-gateway/middlewares/retry.md",
  "line": 42,
  "quote": "The default value for maxRetries is 3.",
  "reasoning": "traefik-hub source (middleware/retry.go:88) sets the default to 5, not 3.",
  "suggested_fix": "The default value for maxRetries is 5.",
  "severity": "blocking",
  "confidence": 0.9,
  "auto_fixable": true
}
```

- `layer`: one of `accuracy`, `style`, `reference`, `clarity`.
- `quote`: the exact doc text the finding is about — copy it verbatim, don't paraphrase. This is what makes a finding checkable at a glance instead of a vague flag.
- `reasoning`: why this is wrong, with a concrete pointer (a `file:line` in source, the specific style rule, the missing link target) — never just "this seems off."
- `suggested_fix`: the literal replacement text. Every finding needs one, even flag-only ones — a human still benefits from seeing the proposed fix even if it isn't auto-applied.
- `severity`: `blocking` (factual/structural — wrong value, broken link, missing required section) vs `suggestion` (style/clarity nits).
- `confidence`: your calibrated confidence this finding is correct and the fix is right, 0.0-1.0. Be conservative — a wrong auto-applied fix is worse than a missed one.
- `auto_fixable`: `true` only when confidence ≥ 0.8 (`AUTO_FIX_THRESHOLD` in `_finding.py`). This is evaluated per finding, not per layer — a style layer can produce a low-confidence flag-only finding just as an accuracy layer can produce a high-confidence auto-fixable one.
