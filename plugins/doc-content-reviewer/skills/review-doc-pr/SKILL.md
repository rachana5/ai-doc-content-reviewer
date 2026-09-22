---
name: review-doc-pr
description: Runs once per hub-doc documentation PR, when it's marked ready_for_review, and posts an automated content review as a single PR comment. Read-only and advisory — never applies fixes, never opens a PR, never blocks merge. Invoke non-interactively as `/review-doc-pr <pr-number-or-url>`, or with no argument when checked out on the PR's own branch in CI.
allowed-tools: "Read Grep Glob Bash(python3:*) Bash(git:*) Bash(gh:*) Bash(vale:*) Bash(alex:*)"
---

# review-doc-pr

Runs `content-reviewer`'s five review layers — accuracy, style, reference,
clarity, completeness — over one PR's changed doc files and posts the
findings as a single PR comment. See
`docs/superpowers/plans/2026-09-17-per-pr-review-skill-plan.md` (in the
`automation` workspace) for the full design history and decisions this
SKILL.md implements.

**This is not `content-reviewer`.** It shares that skill's engine (finding
schema, checklists, mechanical checkers, aggregation) as byte-identical
duplicated files — see "Bundled resources" — but the shape is different in
every way that matters: no mode to detect (always all five layers), no
scope to ask about (always the PR's own changed files), no fixes, no PR,
no human confirmation anywhere in the pipeline. It runs once and reports.

## Bundled resources

- Scripts: `${CLAUDE_SKILL_DIR}/scripts/` — invoke as a package:
  `PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts.<name>`. What's there:
  - `setup.py` — preflight (Python/`gh`/lint-tool checks, Step 0)
  - `_git.py` — subprocess wrapper. **Not** the same file as
    `content-reviewer`'s own copy — this one pins an explicit encoding and
    a 30s timeout that content-reviewer's copy deliberately doesn't have
    (its own `open_pr.py` push is a different, network-bound call site;
    syncing that hardening back was tried once and reverted). Everything
    else in this list below the line IS expected to stay byte-identical
    with `content-reviewer`'s copy —
    `scripts/tests/test_content_reviewer_duplication_sync.py` enforces it.
  - `_discover.py` — locates the local `traefik-hub` clone the accuracy
    layer reads against (Step 1)
  - `changed_lines.py` — parses the PR diff into per-file changed-line
    ranges; the scope boundary between whole-file and diff-only layers
    (Step 2)
  - ---- everything below this line is a byte-identical duplicate of
    `content-reviewer`'s own copy ----
  - `_finding.py` — the shared finding schema, plus a validator CLI (Step 4)
  - `check_links.py` — reference layer, mechanical part (Step 4)
  - `run_style_lint.py` — style layer, mechanical part (Step 4)
  - `aggregate.py` — merges layer findings into one report (Step 5)
  - `_gh.py` — subprocess wrapper around the `gh` CLI, used only by
    `post_review.py` (Step 6). Byte-identical with `content-reviewer`'s
    copy — generic, no reason to diverge the way `_git.py` does.
- References: `${CLAUDE_SKILL_DIR}/references/*.md` — same six files
  `content-reviewer` uses (`finding-schema.md` + the five checklists),
  byte-identical duplicates, same sync test as above.
- Templates: `${CLAUDE_SKILL_DIR}/templates/pr-comment.md.tmpl` — **not**
  shared with `content-reviewer` at all; this is `review-doc-pr`'s own,
  built for a GitHub PR comment (collapsible findings) rather than a
  terminal-watching human. See the plan doc's "Comment format" section.

**`post_review.py` — built.** Renders the aggregated findings (after the
Step 4 severity cap), checks for the marker, and posts or skips. See
"Step 6" below for the full behavior.

Never `cd` into the skill directory — invocation happens from the PR's
checked-out branch.

## Step 0: Preflight

```bash
PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts.setup --check --skip-git-check
```

If this fails on Python or `gh` auth, stop and report the exact failure —
there's no human at the keyboard to fix it interactively, so a clean
failure message in the run's log is the only diagnostic anyone gets.
If `vale`/`alex` are reported missing, continue — the style layer degrades
to agent-only judgment (`references/style-checklist.md`); note this in the
comment rather than silently treating style as clean. Working-tree-dirty
is meaningless here (CI checks out the PR fresh) — `--skip-git-check` above skips
the check itself rather than just telling you to ignore its warning.

## Step 1: Resolve repo root and traefik-hub source

```bash
PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts._discover repo-root
PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts._discover traefik-hub
```

The first is always the checked-out `hub-doc` PR branch — exit 2 would
mean the CI checkout itself is broken, a hard stop, not a content problem.

The second is best-effort, via `$TRAEFIK_HUB_PATH` (the CI runner is
expected to set this to wherever it checked out `traefik-hub` with the
bot identity's read access — see the plan doc's "Credentials / identity"
section). **If it exits 2 (not found), do not ask** — there is no one to
ask. Route straight to the accuracy layer's existing degrade path: every
accuracy finding for this run gets `severity: suggestion`, low confidence,
and reasoning noting the source couldn't be located, using the same
`unverifiable` category `references/accuracy-checklist.md` already
defines for "couldn't find matching source." This is a reuse of an
existing fallback, not new logic.

## Step 2: Resolve scope from the PR's own diff

```bash
gh pr diff <pr-number> --name-only
PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts.changed_lines \
  --repo-root <root> --base <pr-base-branch> --head <pr-head-branch>
```

No mode to detect and nothing to ask — scope is always "every doc file
this PR changed," and `changed_lines.py`'s output is what makes the
per-layer scope split in Step 4 possible. Non-doc files (code, config) in
the diff are outside every layer's job here; skip them.

## Step 3: Run every layer, per the scope rules below

Unlike `content-reviewer` (which picks layers by mode), **all five layers
always run.** But they don't all see the same text — this is the one rule
that has no equivalent in `content-reviewer`'s own `SKILL.md`:

| Layer | Scope | Why |
|---|---|---|
| Accuracy | Whole file | Catches source drift in parts of the file this PR didn't touch — free value since the file's already open. |
| Reference — mechanical (`check_links.py`) | Whole file | Cheap, a script not an LLM call. |
| Reference — judgment (missing crosslinks) | Whole file | Same drift-detection logic as accuracy. |
| Style | Diff-scoped (changed lines only, via `changed_lines.py`) | No drift-detection upside to re-litigating prose the PR didn't touch. |
| Clarity | Diff-scoped (changed lines only) | Same reasoning as style. |
| Completeness | Whole file | A missing migration note, missing troubleshooting pointer, or asymmetric treatment can live anywhere on the page, not just in changed lines — same free-value reasoning as accuracy. |

For a brand-new file, the whole diff is "added," so diff-scoped and
whole-file scope end up identical automatically — no special-casing needed.

Each layer loads its own checklist — `references/accuracy-checklist.md`,
`references/style-checklist.md`, `references/reference-checklist.md`,
`references/clarity-checklist.md`, `references/completeness-checklist.md`
— and writes its own JSON file, same schema as `content-reviewer`
(`references/finding-schema.md`), same mechanical-then-judgment merge
pattern for style/reference (run `check_links.py`/`run_style_lint.py`
first, then append the checklist's own judgment findings to that same list
before writing it). Completeness has no mechanical part — write
`completeness.json` directly, same as accuracy/clarity, and set every
finding's `severity` to `suggestion` and `auto_fixable` to `false`
(the checklist's own calibration caps confidence below the auto-fix
threshold anyway, but set both explicitly). **Validate every layer file
before proceeding:**

```bash
PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts._finding <layer>.json
```

**A finding that fails validation has no human to fix it here.** Re-prompt
the agent pass that produced it with the exact validator error, bounded to
3 attempts. If it still doesn't validate after 3 attempts, drop that
specific finding and emit a replacement `unverifiable`-style finding at the
same location instead (same category Step 1 uses for a missing source) —
degrade that one finding, never fail the whole layer or the whole run over
one bad JSON object.

**Cost note (open item, not blocking):** whole-file accuracy, reference-
judgment, and completeness are all real LLM calls, and this retry budget
draws from the *same* per-PR cost cap once one exists — see the plan doc's
"Open items" section. No numeric cap is wired up yet, and no size-based
gate exists yet either (e.g. skipping completeness on a small PR to keep
cost down) — this paragraph exists so whoever adds either doesn't treat
retries, or completeness specifically, as free in the meantime.

## Step 4: Cap severity for out-of-diff findings

Completeness findings are already always `suggestion` (set in Step 3), so
this cap never has anything to lower for that layer — it only changes
behavior for accuracy/reference-judgment findings outside the diff.

Before aggregating: for every accuracy/reference-judgment finding whose
`line` falls outside `changed_lines.py`'s ranges for that file, force
`severity` to `suggestion` regardless of what the checklist assigned.
`blocking` is reserved for findings inside the PR's own changed lines —
the whole-file scan's value is surfacing drift the PR happens to touch,
not making an unrelated pre-existing issue this PR's problem. Nothing is
dropped; capped findings still appear in the comment.

## Step 5: Aggregate

```bash
PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts.aggregate \
  --accuracy <accuracy.json> --style <style.json> --reference <reference.json> --clarity <clarity.json> \
  --completeness <completeness.json> \
  --template templates/pr-comment.md.tmpl --out <merged.json>
```

No `--mode`/`--layers-run` flags — those describe `content-reviewer`'s two
modes, which don't exist here; `templates/pr-comment.md.tmpl` doesn't
reference them. This step does **not** apply the Step 4 severity cap —
that happens in Step 6, immediately before rendering.

## Step 6: Cap, render, and post the comment

```bash
PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts.post_review \
  --repo <owner/repo> --pr <pr-number> \
  --findings <merged.json> --changed-lines <changed-lines.json from Step 2> \
  --template templates/pr-comment.md.tmpl
```

`post_review.py`:

1. Loads `merged.json` and Step 2's changed-line-ranges JSON, then applies
   the Step 4 severity cap (`cap_severity_outside_diff`) — this is where
   that cap actually runs, right before rendering, so
   `render_report()`'s `blocking_count`/`suggestion_count` reflect the
   capped values.
2. Renders through `templates/pr-comment.md.tmpl` via the reused
   `aggregate.render_report()`, unless there are zero findings, in which
   case it renders a friendly "no issues found" comment instead — the
   template's `{{#findings}}` loop alone would otherwise produce an empty,
   awkward "0 blocking · 0 suggestions" body.
3. Checks the PR's existing comments (`gh pr view --json comments`) for
   the `<!-- review-doc-pr:v1 -->` marker. **This skill fires once per PR,
   on `ready_for_review` — a marker match means a duplicate invocation
   (e.g. a CI retry), not a legitimate update.** Skips posting if found,
   posts new otherwise. (An earlier draft of this plan described
   edit-in-place here, which contradicted the once-only trigger —
   corrected 2026-09-21.)
4. Posts via `gh pr comment --body-file` (a temp file, not an inline
   argument — avoids both shell-escaping and argument-length concerns for
   a body that can run to several KB), using the same bot identity
   `content-reviewer`'s own `open_pr.py` runs as (needs `issues:write`
   added if it doesn't already have it).

Pass `--dry-run` to print the rendered body instead of checking the
marker or posting — useful for testing this pipeline against a fork PR
(Sequencing step 6) before it ever writes a real comment.

## Explicitly not reused from `content-reviewer`

`apply_fixes.py`, `open_pr.py`, and the diff-and-confirm human-in-the-loop
flow (Steps 5/6 of `content-reviewer`'s own `SKILL.md`) are skipped
entirely — read-only advisory, full stop. `auto_fixable`/
`AUTO_FIX_THRESHOLD` still appear on every finding (the schema requires
them) but are never acted on here.

`content-reviewer`'s own `SKILL.md`, `AskUserQuestion` calls, and plugin
distribution are untouched by any of this — it keeps serving on-demand
human-invoked review exactly as before.

## Error handling

- `traefik-hub` not found → degrade accuracy findings to `unverifiable`
  (Step 1). Never ask, never crash.
- A layer's finding fails schema validation after 3 retries → drop and
  replace with an `unverifiable`-style finding at the same location
  (Step 3). Never fail the whole run over one finding.
- Vale/alex missing → `run_style_lint.py` reports `vale_ran`/`alex_ran` as
  `False`; the comment should note this rather than imply style was
  checked and came back clean.
- Link-check network failure → `check_links.py` returns no finding for
  that URL (unchecked), never a false "broken" finding.
- Zero findings → the friendly special case in `post_review.py` (Step 6),
  not the raw template.
