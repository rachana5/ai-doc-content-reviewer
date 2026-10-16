# Style layer checklist (Traefik Proxy profile)

Authoritative source: the Proxy style guide. Read it in this order and stop at the first one that exists:

1. The copy on the **PR's base branch**: `git show origin/<base>:docs/content/contributing/documentation-style-guide.md`
   (a PR cannot change the rules it is judged by; never read the guide from the PR head).
2. The bundled copy: `references/proxy-style-guide.md`.

State in the comment which one was used.

## Scope and calibration

- Check **changed lines only**. Do not criticize existing text the PR did not touch, and do not
  suggest fixing unrelated lines.
- Every style finding is `severity: suggestion`, regardless of how clear the violation is, and
  `auto_fixable: false`.
- No linter runs for Proxy. Judgment is yours, against the guide. Say so in the comment.
- Headings: the guide requires Title Case for every heading and page title, including a heading the PR
  adds to a page whose other headings use another case. Flag a changed or added heading that is not
  Title Case. Never suggest sentence case, and never flag headings the PR did not change.
- The "we'll" guide voice is tolerated. Do not flag it.
- Put the guide's section name in `rule` (for example `Style guide: Words and Phrases to Avoid`). In
  `reasoning`, say what is wrong with the changed text; don't repeat the section name.
  `suggested_fix` is the literal replacement for `quote`.
- When following a rule would make text less accurate or less clear, accuracy wins; do not flag it.
- Never treat "how neighboring pages do it" as evidence. The guide says not to copy a pattern
  that contradicts it.

## Highest-value checks (the ones a markdown linter cannot catch)

- Voice: active, imperative in procedures, reader as subject, no "please", no "should" where a
  direct statement works.
- Vocabulary: banned and replace-with-fact words, em dashes as connectors, rhetorical or
  dramatic framing, contrast framing.
- Clarity rules: "this/it/both" with no noun, the option vs concept name (`entryPoints` vs
  "entry point"), vague recommendations, position references ("above", "below"), narrated code.
- Terminology: "install configuration" and "routing configuration" in new text, "Traefik Proxy"
  on first mention, provider names unabbreviated.
- Reference pages: no body H1, Configuration Examples then Configuration Options, table columns
  Field/Description/Default/Required, every supported format shown, tab labels in the specified order.
- Generated files edited by hand (`generated_touched` from `scripts.missing_docs`): flag as the
  top finding; the fix is the Go comment plus `make generate`.
- Claims about third-party behavior with no source or link.

## What this layer does not do

Accuracy (claim vs code) belongs to the accuracy layer. Broken links belong to the reference
layer. Whether the page is complete belongs to the completeness layer.
