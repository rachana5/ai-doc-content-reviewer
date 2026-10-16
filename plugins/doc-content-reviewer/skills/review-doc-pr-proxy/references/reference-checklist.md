# Reference layer checklist

Goal: catch missing cross-links the mechanical link checker (already run —
its findings arrive pre-computed) can't detect, since it only knows whether
a link resolves, not whether one is missing.

## What to check

- Does this page discuss a concept that has a canonical deeper reference
  page elsewhere in the docs, without linking to it? (E.g. a guide that
  attaches the `forwardAuth` middleware to a router, with no link to the
  `forwardAuth` reference page.)
- Are there existing crosslink policies for specific topic pairs that apply
  here? Check the target repo for any documented crosslink rules before
  inventing new judgment calls. The Proxy style guide only says to name the
  destination in link text and use relative `.md` paths; it sets no
  topic-pair policy, so most findings here are judgment calls (0.5-0.84).
- Only report links the PR's own changed lines should have. A missing link on
  a line the PR did not touch is not this PR's problem.
- Exception, broken links: if the PR renamed or removed a heading or moved a page, a link or
  anchor to it on another page is this PR's problem. Report it with `affected: true`.
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

**Doc text:** "Attach the forwardAuth middleware to the router."
**Reasoning:** The page never links to the `forwardAuth` reference page, where
the options used in the example are described.

```json
{
  "layer": "reference",
  "quote": "Attach the forwardAuth middleware to the router.",
  "reasoning": "First mention of forwardAuth on this page with no link to its reference page, which documents the options the example sets.",
  "suggested_fix": "Attach the [forwardAuth](../reference/routing-configuration/http/middlewares/forwardauth.md) middleware to the router.",
  "severity": "suggestion",
  "confidence": 0.6
}
```
