# Style layer checklist

Goal: catch style-guide and consistency violations that Vale/alex (the
mechanical part of this layer, already run before you see this) can't catch
on their own — the qualitative rules.

## What this layer does NOT need to re-check

Don't re-derive Vale/alex's own rules (wordiness, passive-voice patterns
they already catch, insensitive terms) — those findings arrive pre-computed.
This pass is for what a linter structurally can't judge.

## What to check — and the one rule that governs all of it

**Never treat "how the rest of the doc set does it" as evidence of what's
correct.** The doc set is exactly what this skill exists to check — it may
itself be inconsistent, and "most pages do X" is not proof X is right. Every
item below either checks against a source genuinely independent of the
corpus, or — where no such source exists yet — reports an inconsistency
without asserting which side is correct. This distinction is not optional;
it's the difference between catching drift and quietly enforcing it.

- **Terminology consistency**: check the **target repo's own** Vale config
  first — `.github/vale/traefik/*.yml` may already encode a canonical term
  via Vale's `Substitution` rule type, and `run_style_lint.py` will have
  already surfaced any violation of that as a mechanical finding (real
  authority, real confidence).
  **If no Vale rule covers the term**, do not resolve it by majority usage.
  Report the inconsistency itself — "this page uses both X and Y for what
  looks like the same concept, and no Vale rule or documented glossary says
  which is canonical" — as a low-confidence, suggestion-only finding with
  no `suggested_fix` that picks a winner. A human decides; this checklist
  flags, it doesn't silently enforce whichever term is more common.
- **Voice**: second person ("you configure...") not first person plural
  ("we recommend...") — this standard comes from the Reader ID's own
  definition (direct, task-oriented address), not from how other pages
  currently write. A page that's already first-person elsewhere is not
  evidence that first-person is acceptable — report it anyway, with real
  confidence, since the Reader ID is the independent standard here.
- **Structural convention**: headings in sentence case, code blocks fenced
  with a language tag — these are checkable against Markdown/Docusaurus
  conventions independent of the corpus, so report them with real
  confidence. Parameter-table column order is different: there is no
  documented "established order" yet (that's part of the doc-type taxonomy
  retrofit that hasn't landed) — if you notice inconsistent column order
  across pages, report the inconsistency at low confidence, same treatment
  as uncovered terminology. Don't invent an authoritative order and enforce
  it as if one existed.

## Confidence calibration

- 0.85+: a violation against a genuinely **authoritative, corpus-independent**
  source — a Vale rule, the Reader ID's own definition, or a documented
  Markdown/Docusaurus convention. Never corpus-majority usage on its own.
- 0.5–0.84: either a stylistic judgment call a human writer might reasonably
  disagree with, **or** an inconsistency you've noticed with no
  authoritative source to resolve which side is correct — in the latter
  case, report the inconsistency, not a corrected term, and keep
  `suggested_fix` free of an asserted "right" answer.
- Below 0.5: don't report it — this isn't a case for a low-confidence flag,
  it's noise.

## Examples

**Confident, authoritative source (Reader ID, not corpus):**

**Doc text:** "We recommend you utilize the retry middleware for this."
**Reasoning:** first-person voice; the Reader ID calls for second-person,
task-oriented address — independent of what any other page does.

```json
{
  "layer": "style",
  "quote": "We recommend you utilize the retry middleware for this.",
  "reasoning": "First-person voice ('We recommend') instead of second person, per the Reader ID's direct, task-oriented address standard.",
  "suggested_fix": "Use the retry middleware for this.",
  "severity": "suggestion",
  "confidence": 0.85
}
```

**Uncovered terminology — flag the inconsistency, don't pick a winner:**

**Doc text:** "Configure the rate-limit plugin here."
**Reasoning:** this doc set also calls the same mechanism "middleware"
elsewhere, and no Vale rule or documented glossary says which is canonical.

```json
{
  "layer": "style",
  "quote": "Configure the rate-limit plugin here.",
  "reasoning": "This doc set uses both 'plugin' and 'middleware' for what appears to be the same concept, and no Vale rule or documented glossary establishes which is canonical — flagging for a human to resolve, not asserting 'plugin' is wrong.",
  "suggested_fix": "(needs a human to decide the canonical term)",
  "severity": "suggestion",
  "confidence": 0.6,
  "auto_fixable": false
}
```
