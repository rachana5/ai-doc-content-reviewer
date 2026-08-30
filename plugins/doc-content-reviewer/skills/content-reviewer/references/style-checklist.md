# Style layer checklist

Goal: catch style-guide and consistency violations that Vale/alex (the
mechanical part of this layer, already run before you see this) can't catch
on their own — the qualitative rules.

## What this layer does NOT need to re-check

Don't re-derive Vale/alex's own rules (wordiness, passive-voice patterns
they already catch, insensitive terms) — those findings arrive pre-computed.
This pass is for what a linter structurally can't judge.

## What to check

- **Terminology consistency**: does this page use the same term for the same
  concept as the rest of the docs (e.g. always "middleware," never
  "plugin," for this concept)? Check `style-guide.md`'s terminology table
  (bundled in the `hub-doc-pr-generator` plugin, referenced via the
  target repo's own conventions) for the canonical term.
- **Voice**: second person ("you configure...") not first person plural
  ("we recommend...") — matches the Reader ID's expectation of direct,
  task-oriented address.
- **Structural convention**: headings in sentence case, code blocks fenced
  with a language tag, parameter tables following the established column
  order for this doc type.

## Confidence calibration

- 0.85+: a clear, checkable rule violation (wrong term for an already
  cataloged concept, wrong heading case).
- 0.5–0.84: a stylistic judgment call where a human writer might reasonably
  disagree.
- Below 0.5: don't report it — this isn't a case for a low-confidence flag,
  it's noise.

## Example

**Doc text:** "We recommend you utilize the retry plugin for this."
**Reasoning:** first person ("We recommend"), and "plugin" should be
"middleware" per the terminology table.

```json
{
  "layer": "style",
  "quote": "We recommend you utilize the retry plugin for this.",
  "reasoning": "First-person voice ('We recommend') instead of second person; 'plugin' should be 'middleware' per the terminology table.",
  "suggested_fix": "Use the retry middleware for this.",
  "severity": "suggestion",
  "confidence": 0.85
}
```
