# Clarity layer checklist

Goal: judge prose quality against the Reader ID — beginners, DevOps,
platform engineers, who scan rather than read linearly, looking for
headings, bold terms, and code blocks.

## What to check

- **Passive voice** that obscures who/what does the action ("the request is
  processed" → "the middleware processes the request").
- **Sentence complexity**: long sentences with multiple subordinate clauses
  that could be split for scanability.
- **Ambiguous pronouns**: "it," "this," "that" with no clear antecedent
  within the same sentence or the immediately preceding one.
- **Scanability**: does a paragraph bury a key term in prose that should be
  bolded or pulled into a code block/list, given how this Reader ID
  actually reads docs (scan for headings/bold/code, not full read-through)?

## Confidence calibration

- 0.8+: an unambiguous passive-voice or run-on-sentence rewrite with no
  loss of meaning.
- 0.5–0.79: a scanability improvement that's a matter of taste (e.g.
  whether to bullet-list something that's currently prose).
- Never report a finding purely because a sentence is long — check whether
  it is actually hard to parse, not just above some word count.

## Example

**Doc text:** "When a request is received, it is checked against the rate
limit that has been configured, and if it exceeds this, it is rejected by
the middleware, which then returns a 429 status code to the caller."
**Reasoning:** passive voice throughout, ambiguous "it"/"this," one
overloaded sentence doing three things.

```json
{
  "layer": "clarity",
  "quote": "When a request is received, it is checked against the rate limit that has been configured, and if it exceeds this, it is rejected by the middleware, which then returns a 429 status code to the caller.",
  "reasoning": "Passive voice throughout and one sentence doing three jobs (check, reject, respond) makes this hard to scan.",
  "suggested_fix": "The middleware checks each request against the configured rate limit. If the request exceeds the limit, the middleware rejects it and returns a 429 status code.",
  "severity": "suggestion",
  "confidence": 0.8
}
```
