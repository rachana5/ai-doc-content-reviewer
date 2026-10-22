# Missing-docs check

Goal: for each user-facing code change in the PR (from `scripts.missing_docs`'s
`user_facing_code` list), decide whether documentation is needed, whether the PR
already provides it, and if not, draft what to write.

Findings use the `completeness` layer, always `severity: suggestion`,
`auto_fixable: false`. Calibrate `confidence` between 0.4 and 0.79, never 0.8 or
above: there is no ground truth for "docs are needed", only the code evidence.
Emit one finding per user-facing change, plus the upgrade-impact finding (step 3b) and the task guide
(step 7) when they apply. If one change needs several edits (a
rule page and a priority sentence, for example), put them all in that finding's
`suggested_fix`. A new validation error or stricter input check is part of the
same finding as the option it guards.

## Steps, per entry in `user_facing_code`

1. **Read the code diff** for that file (`git diff <base>...<head> -- <file>`, with `base` and `head` from
   `context.json`; `gh pr diff` takes no file argument), not just the file.
   Identify what a user can now do, configure, or observe differently:
   - a new or renamed option, flag, label, or field
   - a changed default value
   - changed middleware, provider, or routing behavior a user would notice
   - a removed or deprecated option
   Also read the same file at the base (`git show <base>:<file>`). What the code did before decides what
   changes for an existing setup (step 3b).
2. **Skip what isn't user-facing**: refactors, renames of unexported identifiers, logging text,
   performance changes with no behavior difference, test-only helpers. Emit nothing for these.
3. **Check whether the docs already cover it, anywhere.** Use `affected.json` (Step 2b), not
   only the PR's changed doc files. If the option name is documented in the PR's changed files
   and on its reference page, it is covered: leave accuracy to the accuracy layer. If it is
   documented in some places but missing from others (the guide has it, the reference table
   does not), report the places that are missing, one finding for the change.
3b. **Upgrade impact.** If the change alters what an existing setup does (a field that was ignored is now
   applied, a changed default, a stricter check, an error or status text a user reads), confirm the old
   behavior in the base and raise a separate finding with `impact: high`. It suggests a note under
   `docs/content/migrate/` in the section of the version this change ships in, and a `!!! warning` on the
   page where the new behavior is documented (when another finding already covers that page, put the
   warning in that finding and name it here). Take the version from the milestone (`gh pr view <pr> --json
   milestone`) or the base branch. If neither says, write "confirm the version" in the suggestion and
   never guess one. Additive changes that no existing setup can notice need no note.
4. **If not covered**, find the right page from `doc_targets` (read the page; `doc_targets` may
   be a directory, then pick the page that documents the option's group). Decide where in the
   page it belongs (the options table, a configuration example, a new section).
   If the page that should hold the text never documents the parent concept (a `BackendTLSPolicy` option
   on a page with no `BackendTLSPolicy` section), say so in the finding, draft the minimal parent section
   together with the new content, and link the upstream specification page.
5. **Draft the text** following `references/proxy-style-guide.md`: option table row
   (Field, Description, Default, Required), one example per supported format, Title Case
   headings, no em dashes. Base every value on the code (struct tags, defaults in the
   code, tests). Never invent a default or an error message. Then run Step 3c of `SKILL.md` over the
   draft. In the draft:
   - put a prerequisite before the action that needs it, and name the resources the feature needs to work;
   - show behavior that differs by state as a table of cases (cause, result, status reason);
   - say how to see a status or error (the `kubectl describe` command) next to the sentence that mentions it;
   - name a task with a verb ("Secure the Connection to a gRPC Backend"), not a gerund;
   - use the term a reader searches for in the first sentence, and only a term the feature really matches
     (`mTLS` only when Traefik sends a client certificate; `CA certificate` for server validation).
6. **Where it lands.** Say in the finding that the documentation goes in the PR's own branch (`base` in
   `context.json`), next to the code. Never suggest a separate pull request to a maintenance branch for
   something that branch does not have. If the PR is an enhancement that targets a maintenance branch,
   add one sentence that the pull request template sends enhancements to `master`.
7. **Task guide.** If the feature needs several resources to work (a Secret, a policy, a route) and no page
   under `expose/` or `secure/` covers the task, add one more finding, `impact: low`, with the outline of
   a guide: a verb title, Prerequisites, one H2 per step, and the result. At most one per PR.
8. **Generated files**: if the doc target is generated
   (`configuration-options.md`, CRD YAMLs), the fix is the Go struct field comment plus
   `make generate`. Say so; do not draft text for the generated file.

## Finding shape

- `file`: the doc page that should change (a `doc_targets` entry, resolved to a real file).
- `line`: the line of the heading or table the new text follows or extends. Use 1 only when the page
  is new.
- `impact`: `high` for an upgrade-impact finding, `medium` for missing docs of a capability, `low` for a
  task guide (`references/finding-schema.md`).
- `quote`: the code change that creates the gap, for example
  `pkg/middlewares/ratelimiter/rate_limiter.go: new option "maxBurst" (default 1)`.
- `rule`: `Missing docs: <what changed>`, for example `Missing docs: new maxBackoff option`.
- `reasoning`: what changed for the user, why it needs docs, and the code `file:line` evidence.
- `suggested_fix`: the drafted doc text, ready to paste, preceded by one line naming the section
  ("Add a row to the Configuration Options table:").

If you cannot tell whether a change is user-facing, emit one `suggestion` that says so with
confidence 0.4 rather than guessing. Never emit two findings of the same kind for one change.
