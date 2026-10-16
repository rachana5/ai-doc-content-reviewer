# Missing-docs check

Goal: for each user-facing code change in the PR (from `scripts.missing_docs`'s
`user_facing_code` list), decide whether documentation is needed, whether the PR
already provides it, and if not, draft what to write.

Findings use the `completeness` layer, always `severity: suggestion`,
`auto_fixable: false`. Calibrate `confidence` between 0.4 and 0.79, never 0.8 or
above: there is no ground truth for "docs are needed", only the code evidence.
Emit one finding per user-facing change. If one change needs several edits (a
rule page and a priority sentence, for example), put them all in that finding's
`suggested_fix`. A new validation error or stricter input check is part of the
same finding as the option it guards.

## Steps, per entry in `user_facing_code`

1. **Read the code diff** for that file (`gh pr diff <pr> -- <file>`), not just the file.
   Identify what a user can now do, configure, or observe differently:
   - a new or renamed option, flag, label, or field
   - a changed default value
   - changed middleware, provider, or routing behavior a user would notice
   - a removed or deprecated option
2. **Skip what isn't user-facing**: refactors, renames of unexported identifiers, logging text,
   performance changes with no behavior difference, test-only helpers. Emit nothing for these.
3. **Check whether the docs already cover it, anywhere.** Use `affected.json` (Step 2b), not
   only the PR's changed doc files. If the option name is documented in the PR's changed files
   and on its reference page, it is covered: leave accuracy to the accuracy layer. If it is
   documented in some places but missing from others (the guide has it, the reference table
   does not), report the places that are missing, one finding for the change.
4. **If not covered**, find the right page from `doc_targets` (read the page; `doc_targets` may
   be a directory, then pick the page that documents the option's group). Decide where in the
   page it belongs (the options table, a configuration example, a new section).
5. **Draft the text** following `references/proxy-style-guide.md`: option table row
   (Field, Description, Default, Required), one example per supported format, Title Case
   headings, no em dashes. Base every value on the code (struct tags, defaults in the
   code, tests). Never invent a default or an error message.
6. **Generated files**: if the doc target is generated
   (`configuration-options.md`, CRD YAMLs), the fix is the Go struct field comment plus
   `make generate`. Say so; do not draft text for the generated file.

## Finding shape

- `file`: the doc page that should change (a `doc_targets` entry, resolved to a real file).
- `line`: 1 if the page needs a new section; otherwise the line of the table or heading to extend.
- `quote`: the code change that creates the gap, for example
  `pkg/middlewares/ratelimiter/rate_limiter.go: new option "maxBurst" (default 1)`.
- `rule`: `Missing docs: <what changed>`, for example `Missing docs: new maxBackoff option`.
- `reasoning`: what changed for the user, why it needs docs, and the code `file:line` evidence.
- `suggested_fix`: the drafted doc text, ready to paste, preceded by one line naming the section
  ("Add a row to the Configuration Options table:").

If you cannot tell whether a change is user-facing, emit one `suggestion` that says so with
confidence 0.4 rather than guessing. Never emit more than one finding per change.
