# Reference layer checklist

Goal: catch missing cross-links the mechanical link checker (already run —
its findings arrive pre-computed) can't detect, since it only knows whether
a link resolves, not whether one is missing.

## What to check

- Does this page discuss a concept that has a canonical deeper reference
  page elsewhere in the docs, without linking to it? (E.g. a page mentioning
  the Messages API in passing, with no link to the Messages API reference.)
- Are there existing crosslink policies for specific topic pairs that apply
  here? Check the target repo for any documented crosslink rules before
  inventing new judgment calls (e.g. hub-doc's Messages API/Bedrock Mantle
  crosslink rules).
- Is a "See also" section present where the doc type convention expects one,
  and does it list the right pages?

## Confidence calibration

- 0.85+: an established, repo-documented crosslink rule applies here and
  isn't followed.
- 0.5–0.84: a link that would clearly help the reader but isn't governed by
  an explicit rule — your own judgment call.
- Don't invent a "missing link" finding just because a topic is mentioned
  once in passing with no deeper relevance.

## Example

**Doc text:** "...responses are returned in the standard Messages API shape."
**Reasoning:** No link to the Messages API reference page exists anywhere on
this page, and the target repo's crosslink rules say this phrase should link.

```json
{
  "layer": "reference",
  "quote": "...responses are returned in the standard Messages API shape.",
  "reasoning": "Repo crosslink policy requires a Messages API reference link on first mention; none present on this page.",
  "suggested_fix": "...responses are returned in the standard [Messages API](../reference/messages-api.md) shape.",
  "severity": "suggestion",
  "confidence": 0.85
}
```
