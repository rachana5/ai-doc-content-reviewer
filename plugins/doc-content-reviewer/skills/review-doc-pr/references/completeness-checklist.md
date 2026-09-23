# Completeness layer checklist

Goal: judge whether the page gives the Reader ID everything they need to complete the task or
make a decision, and whether it follows this repo's established conventions for the kind of change
it's making. This is not a prose-quality check (`clarity`'s job) and not a claim-vs-source check
(`accuracy`'s job) — it's "is anything missing that this Reader ID would need, or that this repo
already has a pattern for?"

## Reader ID and aims (always in scope)

- Readers are beginners, DevOps, and platform engineers. They scan and search rather than read
  linearly: they look for headings, bold terms, and code blocks, not paragraphs.
- Every feature set should read like it follows diataxis: a clear getting-started/task path,
  reference detail, and a place to land when something goes wrong.
- Aim for complete, concise, up-to-date, developer-friendly content that helps the reader build a
  mental model of the product, not just complete one step.

## What to check

1. **Task-completability.** Could the Reader ID finish this task using only this page and what it
   links to, with no other tribal knowledge? Look for: an option list that names fields but never
   shows a real, copy-paste-level usage of them (a full policy, a full command, a full snippet, not
   just a description of the shape of one); an obvious next question the page invites but doesn't
   answer ("what if I already have X set up, can I move to this?"); a "described in..." reference
   whose target doesn't actually cover what's being pointed at.
2. **Convention adherence.** Does this repo already have an established pattern for this situation
   that the new content skips? Specifically:
   - **Version-gating / Early Access.** If the change documents something not yet generally
     available, is it flagged the way other EA content in this repo is (see
     `docs/api-gateway/secure/middleware/oauth-token-exchange.md:15`, `:::warning Early Access`)?
     Only raise this when there's a concrete signal the feature is gated (an issue/PR that says so,
     a reference to an untagged version) — never guess at release status.
   - **Migration notes.** If the change adds a new way to do something the reader might already be
     doing another way, does it say whether/how to move from the old way (see
     `docs/api-gateway/secure/middleware/jwt.md:257` for the pattern), or at minimum say plainly
     that migration isn't covered yet? Silence is the failure mode, not the absence of a full guide.
   - **Troubleshooting.** For a page describing a multi-component or operationally involved setup,
     is there anywhere for the reader to land when a failure mode the page itself describes actually
     happens (see `docs/api-gateway/expose/multi-cluster.md:986` for the pattern)? A one-line
     pointer counts; total silence doesn't.
3. **Internal consistency.** When the new content describes two or more parallel things of the same
   kind (two credentials, two connection types, two failure modes), does it treat them
   symmetrically? One getting a security/configuration paragraph while its sibling gets none is a
   gap, even if every individual sentence is accurate and well written.

## What NOT to check here

- Anything `reference`'s missing-crosslinks judgment already covers: an option that exists in a
  reference table but isn't pointed to at all from the task page. That's a discoverability/
  cross-link problem, not a completeness one — leave it there so the two layers don't produce
  duplicate findings for the same gap.
- Sentence-level rewrites — that's `clarity`.
- Anything not actually implied by the Reader ID or a concrete repo convention. A completeness
  finding needs real evidence (a convention this repo already follows elsewhere, or a specific
  question the Reader ID would hit), never "this could be more thorough."

## Process

1. Read the new/changed content in full, plus whatever it links to (the reference page, any
   linked prerequisite section).
2. For each check above, note anything missing along with concrete evidence: the repo convention
   it should match (`file:line`), or the specific unanswered reader question.
3. Anchor `line`/`quote` to the nearest *existing* text the addition would attach to (a heading, or
   the sentence right before the gap) — a completeness finding is about absence, so there's no
   exact span to quote verbatim; anchor to what's already there instead.
4. Only produce a finding when there's an anchor and concrete evidence. No anchor, no finding.

## Confidence calibration

- 0.6–0.8: a real repo convention exists and the new content clearly falls into the situation that
  convention covers, but applying it involves some judgment (exactly where, how much to say).
- 0.4–0.6: the gap is real (an unanswered reader question, asymmetric treatment) but there's no
  established convention to cite — it's a judgment call about what the Reader ID needs.
- Never above 0.8 — there's no ground truth to confirm against, only a convention or a plausible
  reader question.
- `severity`: always `suggestion`. `auto_fixable`: always `false`, regardless of confidence — the
  fix is new content someone has to write and verify, not a mechanical correction to existing text.

## Example

**New content:** A page section adds a third way to configure a credential, alongside two existing
ones, and explains how to secure the first new field (auth, TLS) but never mentions whether the
second new field introduced in the same section carries the same concern.

```json
{
  "layer": "completeness",
  "quote": "<heading or sentence the addition would attach to>",
  "reasoning": "The new section explains how to secure connection A (credentials, TLS) but says nothing about connection B, introduced in the same section with equivalent risk. Same-kind items get asymmetric treatment.",
  "suggested_fix": "Add a parallel paragraph covering authentication and TLS for connection B, next to the existing paragraph for connection A.",
  "severity": "suggestion",
  "confidence": 0.7,
  "auto_fixable": false
}
```
