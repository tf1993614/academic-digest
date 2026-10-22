# 自动学术速递

每天按用户设定的关键词，从文献源与 GitHub 收集新内容，筛成一份中文日报并推送到微信。

## Parallel work

Run one implementation session per worktree: `git worktree add out/worktrees/<ticket>`, then work there. Each commit then covers one ticket, and the pre-commit hook checks that ticket's index.

## Agent skills

### Issue tracker

Issues and specs live as local Markdown under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `GLOSSARY.md` + `docs/adr/`. See `docs/agents/domain.md`.

### Code review

Freeze the diff before dispatching reviewers. See `docs/agents/code-review.md`.
