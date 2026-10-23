# 自动学术速递

每天按用户设定的关键词，从文献源与 GitHub 收集新内容，筛成一份中文日报并推送到微信。

## Parallel work

When more than one implementation session runs at once, give each its own worktree:
`git worktree add out/worktrees/<ticket>`, then work there, so each commit covers one
ticket. A single session may work in the main worktree.

## Agent skills

### Issue tracker

Issues and specs live as local Markdown under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` + `docs/adr/`. See `docs/agents/domain.md`.

### Daily digest skill

The shipped end-user workflow lives in `.dsh/skills/academic-digest/SKILL.md` (also linked at the repo root as `SKILL.md` for humans); setup and the digest contract are its `references/`. The daily task card runs collect → write digest → push from that skill.

### Code review

Before dispatching, read `docs/agents/code-review.md`: grep every new or changed payload key across `README.md`, `CODING_STANDARDS.md`, the ADR, and the ticket, then freeze with `scripts/review-patch.sh --base <fixed-point>`.
