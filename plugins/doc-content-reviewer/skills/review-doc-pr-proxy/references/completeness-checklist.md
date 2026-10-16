# Completeness layer checklist

Goal: judge whether what this PR changes is documented completely, and in the way this repo
documents such changes. This is not a prose check (`clarity`), not a claim-versus-code check
(`accuracy`), and not a check of whether a page is thorough overall.

## Scope

The change set only. Raise a gap the PR creates or widens; never one that was already there.
For a page the PR does not edit, `references/affected-docs-checklist.md` covers it. Readers are
beginners, DevOps, and platform engineers who scan for headings, bold terms, and code blocks.

## What to check

1. **A usable example.** Does the changed or new option appear in a copy-paste-level example, or
   only in a description of its shape? Does the page leave the obvious next question about the
   change unanswered ("what happens to my existing setup?")?
2. **Convention adherence.** Does this repo already have a pattern for this kind of change that
   the PR skips?
   - **Version-gating and experimental features.** If the change documents something not yet
     generally available, is it flagged the way other experimental content is (see
     `docs/content/reference/install-configuration/experimental/`)? Only raise this with a
     concrete signal that the feature is gated (an issue or PR that says so, an `experimental`
     config path). Never guess at release status, and state version-specific behavior only for
     versions you verified.
   - **Migration and deprecation notes.** If the change alters behavior existing users rely on (a
     changed default, a stricter validation, a removed or renamed option), is there a note under
     `docs/content/migrate/` (or `docs/content/deprecation/` for deprecations), the way earlier
     behavior changes got one? Silence on a user-visible breaking change is the failure mode.
   - **Every supported format.** If an option is added to an example, is it added to every
     format the page shows (Structured YAML/TOML, Labels, Tags, Kubernetes, CLI/Helm for install
     configuration)? Every format must produce the same configuration.
   - **Generated reference.** If the change touches an option documented in a generated file
     (`configuration-options.md`, the CRD YAMLs), the fix is the Go struct comment plus
     `make generate`, not a hand edit. Say so instead of drafting text for the generated file.
3. **Symmetry.** When the new content describes two or more parallel things of the same kind (two
   credentials, two connection types), does it treat them alike? One getting a security or
   configuration paragraph while its sibling gets none is a gap.

## What not to check here

- A missing link to a page that exists: that is `reference`.
- Sentence-level rewrites: that is `clarity`.
- Anything without a concrete repo convention or a specific reader question behind it. "This could
  be more thorough" is not a finding.

## Process

1. Read the changed content in full, plus the reference page and any linked prerequisite.
2. For each check, note what is missing with concrete evidence: the convention it should match
   (`file:line`) or the specific unanswered question.
3. Anchor `line` and `quote` to the nearest existing text the addition attaches to (a heading, or
   the sentence before the gap). A completeness finding is about absence, so there is no exact span
   to quote.
4. No anchor, no finding.

## Confidence calibration

- 0.6 to 0.8: a real repo convention exists and the change clearly falls under it, though
  applying it needs judgment (where, how much).
- 0.4 to 0.6: the gap is real (an unanswered reader question, asymmetric treatment) but no
  convention exists to cite.
- Never above 0.8. `severity` is always `suggestion`; `auto_fixable` is always `false`.

## Example

The PR adds a third way to configure a credential next to two existing ones, and explains how to
secure the first new field but never mentions the second new field.

```json
{
  "layer": "completeness",
  "file": "docs/content/reference/install-configuration/example.md",
  "line": 42,
  "rule": "Missing docs: second connection type has no security note",
  "quote": "<heading or sentence the addition attaches to>",
  "reasoning": "The new section explains how to secure connection A (credentials, TLS) but says nothing about connection B, introduced in the same section with equivalent risk.",
  "suggested_fix": "Add a paragraph covering authentication and TLS for connection B, next to the one for connection A.",
  "severity": "suggestion",
  "confidence": 0.7,
  "auto_fixable": false
}
```
