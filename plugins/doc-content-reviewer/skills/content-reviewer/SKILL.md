---
name: content-reviewer
description: Use when someone wants an existing hub-doc or traefik (Proxy) doc section audited for accuracy against source code, style-guide consistency, reference/link correctness, or prose clarity — either a full-section review or a targeted check of one claim/parameter. Invoke as `/content-reviewer <path-or-topic>`.
allowed-tools: "AskUserQuestion Read Grep Glob Bash(python3:*) Bash(git:*) Bash(gh:*) Bash(vale:*) Bash(alex:*)"
---

# content-reviewer

Audits existing documentation content across four independent layers —
accuracy, style, reference, clarity — and produces one report with
confidence-gated auto-fix and an optional PR. See
`docs/superpowers/specs/2026-08-28-content-reviewer-design.md` for the full
design rationale.

## Bundled resources

- Scripts: `${CLAUDE_SKILL_DIR}/scripts/` — invoke as a package:
  `PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts.<name>`. What's there:
  - `setup.py` — preflight (Python/`gh`/lint-tool checks, Step 0)
  - `_git.py`, `_gh.py` — generic subprocess wrappers, no CLI of their own
  - `_discover.py` — locates the `traefik-hub` source clone / current repo root (Step 1)
  - `_finding.py` — the shared finding schema, plus a validator CLI (Step 3)
  - `check_links.py` — reference layer, mechanical part (Step 3)
  - `run_style_lint.py` — style layer, mechanical part (Step 3)
  - `aggregate.py` — merges layer findings into one report (Step 4)
  - `apply_fixes.py` — stages/applies confidence-gated fixes (Step 5)
  - `open_pr.py` — branch/commit/push/PR, only after explicit confirm (Step 6)
- References: `${CLAUDE_SKILL_DIR}/references/*.md` — load only the file(s)
  for the layer(s) actually running.
- Templates: `${CLAUDE_SKILL_DIR}/templates/*.md.tmpl`

Never `cd` into the skill directory — the user's cwd is their own repo
checkout.

## Step 0: Preflight

```bash
PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts.setup --check
```

If this fails on Python or `gh` auth, stop and report the exact fix. If
`vale`/`alex` are reported missing, continue — the style layer degrades to
agent-only judgment (see `references/style-checklist.md`); note this in the
final report rather than silently treating style as "clean." If the
working tree is reported dirty, mention it to the user and continue — it's
advisory, not a blocker, but the user should know before this run's fixes
land in the same working tree as their own uncommitted changes.

## Step 1: Resolve repo and scope

Detect the target **docs** repo from cwd (`hub-doc/` → Hub docs; `traefik/`
→ Proxy docs) or an explicit `--repo` argument. If ambiguous, ask — never
guess.

Then resolve the **source root** the accuracy layer will read against —
this is a separate repo for Hub docs, so it needs real discovery, not an
assumption:

- **Hub docs** (source = `traefik-hub`, a separate private repo):
  ```bash
  PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts._discover traefik-hub
  ```
  Exit 0 → use the printed path. Exit 2 (not found) → ask the user via
  `AskUserQuestion` for their local `traefik-hub` clone path, then persist
  it so future runs skip discovery:
  ```bash
  PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts._discover save-traefik-hub <path>
  ```
- **Proxy docs** (source = `traefik/traefik` itself, docs and code in one
  repo — no separate discovery needed):
  ```bash
  PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts._discover repo-root
  ```
  This is just "what repo is cwd already inside" — exit 2 means cwd isn't
  a git repo at all, which is a hard stop (ask the user where their
  `traefik/traefik` checkout is).

## Step 2: Detect mode — full review vs. targeted check

Classify the user's request:

- **Full review** — a path/section named with no narrow technical term.
  Examples: "review the getting-started section," "audit
  docs/api-gateway/middlewares." → run **all four layers** against every
  file in scope.
- **Targeted check** — a specific claim/term/parameter named. Examples:
  "check docs for mentions of maxRetries against source code," "is the
  rate-limiting default documented correctly?" → run only the layer(s) the
  question implicates (accuracy, almost always; reference joins if
  links/citations are the actual ask), scoped to just the files/paragraphs
  mentioning that term — not the whole section.

If genuinely ambiguous which mode applies, ask the user rather than
guessing at scope.

## Step 3: Run each layer in scope

Every layer's output ends up as one JSON file — a plain list of finding
dicts matching `references/finding-schema.md` — at a path like
`<scope-slug>/<layer>.json` (e.g. `getting-started/accuracy.json`) in a
scratch directory. For each layer that applies (per Step 2):

1. **Accuracy** — load `references/accuracy-checklist.md`. Read the target
   text's claims, grep/read the matching source in the resolved source root
   (Step 1), and **write `accuracy.json` directly** — a JSON list built by
   hand from what you found, one dict per finding, matching the schema.
2. **Style** — run the mechanical part first:
   `PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts.run_style_lint <files> --repo-root <root>`
   That prints a JSON list. Then load `references/style-checklist.md` for
   the qualitative pass, and **append your own findings to that same
   list** — the combined list, mechanical + judgment together, is what
   gets written as `style.json`. `aggregate.py` only takes one file per
   layer, so this merge has to happen before you write the file, not after.
3. **Reference** — same pattern as style: run the mechanical part first,
   `PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts.check_links <files> --repo-root <root>`,
   then load `references/reference-checklist.md` for the missing-crosslink
   judgment pass, append those findings to the mechanical list, and write
   the combined result as `reference.json`.
4. **Clarity** — load `references/clarity-checklist.md`. Agent-only, no
   mechanical part — write `clarity.json` directly, same as accuracy.

**Before moving to Step 4, validate every layer file you just wrote:**
```bash
PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts._finding <layer>.json
```
Exit 0 means every finding in that file matches the schema. A nonzero exit
prints exactly which finding (by list index) and which field is wrong — fix
that layer's JSON and re-validate before proceeding. This is what makes
hand-authoring the JSON safe enough for an MVP: a malformed finding fails
loudly here, at the layer boundary, instead of breaking `aggregate.py` or
silently vanishing from the report.

## Step 4: Aggregate and report

```bash
PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts.aggregate \
  --accuracy <accuracy.json> --style <style.json> --reference <reference.json> --clarity <clarity.json> \
  --template templates/review-report.md.tmpl --out <merged.json> \
  --repo <hub-doc|traefik> --scope <the-path-or-topic-from-step-1> \
  --date <today's-date> --mode <"full review"|"targeted check"> \
  --layers-run <comma-separated list of layers actually run, e.g. "accuracy, style">
```
(Any layer that didn't run for this mode — e.g. style/clarity skipped in a
targeted check — simply omits its flag; `aggregate.py` treats a missing
layer as no findings from that layer. The `--repo`/`--scope`/`--date`/
`--mode`/`--layers-run` flags fill the report template's top-level fields —
`blocking_count`/`suggestion_count`/`auto_fixable_count` are computed
automatically from the findings and need no flag.)

Show the user the full rendered report (`templates/review-report.md.tmpl`),
but lead with a one-line summary before the numbered findings — e.g.
"Found 12 issues across 5 files: 3 blocking, 9 suggestions, 7
auto-fixable." — so there's an at-a-glance read before the detail, whether
this is you running it or a teammate seeing it for the first time. Every
finding keeps its layer badge and reasoning visible below that — this is
the whole point of running layers separately instead of one blended pass.

## Step 5: Stage fixes, show diff, wait for confirmation

```bash
PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts.apply_fixes --findings <merged.json> --repo-root <root>
```

Without `--apply`, this **only prints a diff and never writes to disk**.

**Don't paste the raw diff as one flat blob.** Group the review by file: for
each file with at least one staged fix, show a one-line summary per
finding (layer + reasoning — already in the Step 4 report) immediately
followed by that file's own diff hunk, then move to the next file. The
reasoning explains the change; the diff just confirms it matches — this is
what keeps the review scannable instead of a wall of text, for a run of
any size. If the combined diff is genuinely large (several files or many
hunks — a judgment call, not a fixed threshold), write the full diff to a
scratch file instead of pasting it all inline, and show only the per-file
summary lines directly, naming the file path for anyone who wants to open
the whole thing in an editor.

Lead the confirmation with the fast path: **"Apply all N auto-fixable
fixes across M files? [yes] — or pick specific ones by #, or none."** Yes
is the one-word answer for the common case; subset-by-id (e.g. "apply 2
and 4") stays available but isn't presented as equally weighted with "all."
If the user approves only a subset, write `<approved.json>` as the entries
from `<merged.json>` whose `id` is in the approved set — the id from
`aggregate()`'s output is exactly what makes this an unambiguous filter
instead of a guess at which finding "the third one in the diff" refers to.
Only then re-run with `--apply`:

```bash
PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts.apply_fixes --findings <approved.json> --repo-root <root> --apply
```

This mirrors the project's standing "show me a diff before making changes"
rule — nothing is written until this explicit second call, after approval.

## Step 6: PR gate

After fixes are applied to the working tree (if any were), ask explicitly:
**"Open a PR with these changes?"** Only on a clear yes:

First check `git -C <root> remote -v` for the remotes. A repo checked out
from a fork commonly carries two: `origin` (the real upstream, e.g.
`traefik/hub-doc`) and a fork remote (the user's own copy). `open_pr`
defaults `--remote` to `origin` — **if a fork remote exists, `--remote`
must be passed explicitly**, or the branch pushes straight to the real
upstream repo instead of the fork. If it's ambiguous which remote is the
fork, ask rather than guessing.

```bash
PYTHONPATH="${CLAUDE_SKILL_DIR}" python3 -m scripts.open_pr --repo-root <root> \
  --branch content-review/<date>-<scope-slug> \
  --title "docs: content review fixes for <scope>" \
  --body "<rendered from templates/pr-body.md.tmpl>" \
  --files <modified-file-paths-from-the---apply-step...> \
  --remote <fork-remote-name-if-one-exists>
```

If no, leave the applied fixes in the working tree (or ask whether to
revert) and stop. Never call `open_pr` without this explicit confirmation —
no code path in this skill does so automatically.

## Error handling

- Repo/target ambiguous → ask, don't guess.
- Accuracy layer can't locate matching source → emit a finding with
  `severity: suggestion`, low confidence, reasoning noting it's
  unverifiable — never silently skip, never crash.
- Vale/alex missing → `run_style_lint.py` reports `vale_ran`/`alex_ran` as
  `False`; note this in the report rather than treating the layer as clean.
- Link-check network failure → `check_links.py` returns no finding for that
  URL (unchecked), never a false "broken" finding.
- Working tree dirty at Step 0 → `check_git_status` reports it as advisory
  only; mention it and continue, never block the run over it.
