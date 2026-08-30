# doc-content-reviewer

MVP Claude Code plugin: a single `content-reviewer` skill that audits existing
`hub-doc` / `traefik` (Proxy) documentation across four independent layers —
accuracy (vs. source code), style, reference/link checks, and clarity — and
produces one report with confidence-gated auto-fix and an optional PR.

Design: `docs/superpowers/specs/2026-08-28-content-reviewer-design.md` in the
`automation` workspace. Plan: `docs/superpowers/plans/2026-08-28-content-reviewer-implementation.md`.

## Development

```bash
make test
```
