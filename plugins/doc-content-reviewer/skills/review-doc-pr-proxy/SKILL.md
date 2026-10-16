---
name: review-doc-pr-proxy
description: Runs once per Traefik Proxy pull request and produces one advisory docs review comment. Scoped to what the PR changes: reviews the changed docs and every other page the implementation change affects (accuracy, style, reference, clarity, completeness), and, when user-facing code changed, checks whether docs are missing and drafts them. Read-only, never applies fixes, never blocks merge. Invoke non-interactively as `/review-doc-pr-proxy <pr-number> [--dry-run | --out <file>]`.
allowed-tools: "Read Grep Glob Bash(python3:*) Bash(git:*) Bash(gh:*)"
---

# review-doc-pr-proxy

Runs the five review layers over one `traefik/traefik` PR and produces a single comment. Settings
(docs location, doc engine, style guide, which code counts as user-facing, bot PRs to skip) come from
`profiles/proxy.json`.

**Scope rule:** every layer is scoped to the behavior this PR changes, never to a whole file. A page
is in scope only for claims about the changed behavior, whether or not the PR edits that page.
Anything else on the page is out of scope, even if it is wrong.

Read-only and advisory: never applies fixes, never edits the PR, never blocks merge. Fires once per
PR; the comment carries a marker so a CI retry skips instead of duplicating (no edit-in-place).

## Running the scripts

Scripts live in `${CLAUDE_SKILL_DIR}/scripts/` and run as
`PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts.<name>`. Never `cd` into the skill directory:
run from the PR's checked-out branch. References are in `${CLAUDE_SKILL_DIR}/references/`; the
comment template is `${CLAUDE_SKILL_DIR}/templates/pr-comment.md.tmpl`. Helpers the steps use
implicitly: `profile.py`, `missing_docs.py`, `changed_lines.py`, `pr_filter.py`, `_finding.py`,
`_gh.py`, `_git.py`.

## Step 0: Preflight

```bash
PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts.setup --check --skip-git-check
```

If this fails on Python or `gh` auth, stop and report the exact failure: nobody is at the keyboard,
so the run's log is the only diagnostic.

## Step 1: Prepare

```bash
PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts.prepare --pr <pr> --repo-root <root> --out-dir <dir>
```

This resolves the PR, skips dependency-bump PRs, classifies the changed files, and writes
`context.json`, `classify.json` and `changed-lines.json`. A workflow may already have run it and
supplied `context.json`; then skip the command. Read `context.json`:

| `action` | Run | Produce |
|---|---|---|
| `full-review` | Step 2, Step 3 (all layers), and Step 3b if `user_facing_code` is non-empty | one comment |
| `missing-docs-only` | Step 2, Step 3b, and the accuracy layer on affected pages only (code changed, no docs touched: a page that still states the old default is the typical finding) | a comment only if a finding exists |
| `silent` | nothing | nothing |

`skip: true` (a dependency-bump PR) means `silent`: run no layer and post nothing, not even the
"no issues" comment.

The code the accuracy layer checks against is this repository at the PR head. For anything the PR
did not touch, use the PR's base branch.

## Step 2: Find the change set and the affected pages

1. **Change set.** List the terms this PR changes: from the code diff of each `user_facing_code`
   file, every option, field, flag, label, middleware or provider name that is new, renamed, removed,
   or has a changed default or behavior. For a docs-only PR (no code diff), use the options and
   claims in the changed doc lines instead. Write them as one comma-separated list.
2. **Search the whole docs tree** for those terms. The profile's `doc_targets` seed the ranking;
   the search is what finds pages the map does not know:

```bash
PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts.find_affected_docs --profile proxy \
  --repo-root <root> --terms "<term1>,<term2>" --classify classify.json > affected.json
```

3. Read each candidate page in `affected.json` and apply `references/affected-docs-checklist.md`.
   Pages with `in_pr: false` are the ones the PR forgot: a reference table, a sibling guide, a
   migration note. Findings on pages the PR does not edit are always `suggestion` (Step 4).

## Step 3: Review layers

"Changed lines" means `changed-lines.json`; "affected pages" means `affected.json`. Each layer loads
its checklist (`references/<layer>-checklist.md`; style also reads the Proxy style guide) and writes
`<layer>.json` in the shape of `references/finding-schema.md`. Write `[]` for a layer with no findings.

| Layer | Scope |
|---|---|
| Accuracy | Changed lines: every claim. Everywhere else (rest of a changed page, affected pages): only claims about the change set, including a sentence far from the edit that the change now contradicts. Evidence is the PR's code diff first, then surrounding code (struct, defaults, tests) |
| Reference: mechanical (`check_links.py`) and judgment | Changed lines. On affected pages: only a link or anchor this PR broke (a renamed or removed heading or page); mark it `affected: true` |
| Style (`references/style-checklist.md`, the Proxy style guide) | Changed lines only |
| Clarity | Changed lines only |
| Completeness | The change set: is it documented everywhere it should be (every format, reference page, migration note)? Not "is this page thorough". Always `suggestion`, `auto_fixable: false` |

No linter runs for Proxy, so style is agent-only and the comment says so.

Reference layer, mechanical part. Proxy docs are MkDocs, so pass the engine and docs root; the
default mode would false-flag every directory-style link and does not check anchors. Run it on the
changed doc files, then on affected pages and keep only findings whose broken target this PR changed
(set `affected: true`):

```bash
PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts.check_links --repo-root <root> \
  --engine mkdocs --docs-root docs/content <doc files> > reference.json
```

Append your judgment findings (missing links on changed lines) to that list. Validate every file:

```bash
PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts._finding <layer>.json
```

A finding that fails validation: re-prompt with the validator error, max 3 attempts, then replace it
with an `unverifiable` finding at the same location. Never fail the run over one finding.

## Step 3b: Missing-docs check (user-facing code changed)

Follow `references/missing-docs-checklist.md` for each `user_facing_code` entry, using
`affected.json` to see what the docs already say anywhere in the tree. Write the results as
`completeness` findings (merge into `completeness.json` when both exist). If `generated_touched` is
non-empty, report it as the top style finding.

## Step 4: Cap severity outside the diff

Findings whose line is outside the PR's changed lines, including every finding on a page the PR does
not edit, become `suggestion`. Nothing is dropped. `post_review.py` applies this right before rendering.

## Step 5: Aggregate

```bash
PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts.aggregate \
  --accuracy accuracy.json --style style.json --reference reference.json --clarity clarity.json \
  --completeness completeness.json --template templates/pr-comment.md.tmpl --out merged.json --quiet
```

Always pass `--quiet`: the console echo is built before the Step 4 cap, so its counts can disagree
with the comment that is produced.

## Step 6: Render and deliver

```bash
PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts.post_review \
  --repo <owner/repo> --pr <pr> --findings merged.json \
  --changed-lines changed-lines.json --template templates/pr-comment.md.tmpl \
  --profile proxy --classify classify.json [--dry-run | --out comment.md]
```

How the comment is delivered follows the invocation:

- no flag: post it as one PR comment (skips if the marker `<!-- review-doc-pr:v1 -->` is already on
  the PR: a duplicate invocation, not an update);
- `--dry-run`: print it, post nothing (use this first on any live repo, and for manual runs);
- `--out comment.md`: write it to the file, post nothing (for a workflow that posts it itself).

`--profile` drops `reference` findings on lines the PR did not change, unless the finding is
`affected: true`. `--classify` applies the silence rules: `silent`, or `missing-docs-only` with zero
findings, produces nothing and exits 0. A `full-review` with zero findings renders a short "no
issues found" comment. Findings are ordered blocking first, then accuracy, missing docs, links,
clarity, style. With 8 or more suggestions, related ones are grouped into one collapsed row (same
`group` value, or all link findings); blocking findings are never grouped.

## Error handling

- Style guide missing on the base branch: use the bundled copy and say so in the comment.
- Link-check network failure: no finding for that URL; never a false "broken".
- Comment over the size cap: shorten suggestions and state what was shortened.
