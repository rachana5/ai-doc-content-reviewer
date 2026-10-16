# Wiring `review-doc-pr-proxy` into a workflow

For the engineers who run `review-doc-pr-proxy` automatically. The agent never reads this file; its
instructions are in `plugins/doc-content-reviewer/skills/review-doc-pr-proxy/SKILL.md`.

## What the skill does

For one `traefik/traefik` pull request it reviews the documentation and produces one advisory
comment. It never edits the PR, never applies fixes, and never blocks merge.

It is scoped to what the PR changes: the changed lines, plus any claim about the changed behavior on
any page, including pages the PR does not edit (a reference table, a sibling guide, a migration
note). It does not audit the rest of a page. Product settings are in `profiles/proxy.json`.

## Inputs

| Input | Notes |
|---|---|
| PR number and repo | `--pr`, `--repo` |
| A checkout of the PR head | The skill runs from it and reads the source code from it |
| The PR's base branch fetched | `changed_lines` diffs `base...head` |
| `gh` authenticated | Read access to the PR; write access only if the skill posts the comment |

## The run, in two halves

1. **Deterministic half.** `python3 -m scripts.prepare --pr N --out-dir DIR` writes `context.json`
   (skip decision, `action`, doc and code lists), `classify.json` and `changed-lines.json`. No LLM.
   A workflow can run it itself and give `context.json` to the agent; an agent with a shell runs it
   as Step 1.
2. **Judgment half.** The agent reads `SKILL.md` and runs the review layers. Where it needs a script
   (the affected-docs search, the link check, aggregation, rendering), it runs it. An agent with no
   shell cannot, so run those as workflow steps or give the agent a shell.

`action` decides what happens: `silent` means do nothing, `missing-docs-only` means code changed and
no docs did, `full-review` means docs changed.

## Outputs and posting

The skill ends by rendering a comment. Delivery is a flag on `post_review`:

| Flag | Result |
|---|---|
| none | Posts one PR comment with `gh pr comment`; skips if the marker `<!-- review-doc-pr:v1 -->` is already there |
| `--dry-run` | Prints the comment, posts nothing |
| `--out comment.md` | Writes the file, posts nothing. Use this when the workflow posts the comment itself |

`AGENTS.md` in traefik/traefik says agents must not post comments for contributors. Use `--out` and a
maintainer-approved posting step, or agree the posting identity with the maintainers first.

## Safety to decide before enabling

- **Trigger.** Run on a maintainer label or `ready_for_review`, not on every push. A re-run on the
  same PR is a duplicate and skips.
- **Fork PRs.** The agent reads PR content (doc text and code) as data. Do not give a run on a fork
  PR secrets or write tokens beyond comment posting.
- **Cost.** One run is several agent passes (the layers) plus the affected-docs reads. Set a per-run
  limit in the workflow.
- **Skip rules.** Dependency-bot PRs are skipped by the profile (`skip_authors`, `skip_title_prefixes`).

## Running it by hand

```
/review-doc-pr-proxy 14123 --dry-run
```

Prints the comment. Nothing is posted.

## Open items for the team

- Whether the reviewer in `traefik/ai` can load a second skill besides `review`, and how it should
  hand inputs to a skill. hub-doc#1043 uses a `REVIEW_DOC_PR_INPUTS` directory for the Hub skill; this
  skill could follow the same convention.
- Findings are ordered by importance and grouped by `post_review.py`. An agent that renders the comment
  itself, with no shell, would have to follow those rules in prose. Running `post_review.py --out` as
  a workflow step avoids that.
- Who owns the posting identity and the credentials.
- The acceptable false-positive rate; none has been measured.
