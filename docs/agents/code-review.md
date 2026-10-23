# Code review

Review a frozen diff, never a moving working tree. A reviewer that sees the tree change while it reads has to re-read or wait; during the 03 implementation two review subagents burned their runs polling `git diff` and never reported.

## Before you freeze

- Walk the ticket checklist and confirm every item has a test or fixture that fails without it.
- Check every documented default and every "no update means no block" claim.
- Grep `README.md`, `CODING_STANDARDS.md`, the ADR, and the ticket for every payload key you added, renamed, or removed.
- Fix these before dispatching. A review round costs two subagent runs.

## Freeze the diff

1. Stop editing. A commit is cleanest; uncommitted changes are fine as long as they stay still. For a committed range, commit or stash first: `--base` refuses a dirty working tree.
2. Run one of:

   ```bash
   scripts/review-patch.sh                 # uncommitted work: working tree vs HEAD
   scripts/review-patch.sh --base 08def36  # committed work: 08def36...HEAD
   ```

   It writes `out/review/current.diff`, plus `.stat`, `.status`, `.base`, `.head`, and prints `frozen files: N`. `--base` reviews the committed range and fails on a dirty tree or an empty diff; only the working-tree mode includes untracked files.
3. Verify the freeze before dispatching:

   ```bash
   cat out/review/current.diff.head          # must equal: git rev-parse HEAD
   git rev-parse HEAD
   ```

   Also check `frozen files` against `git diff --name-only <base>...HEAD | wc -l`. A stale patch costs a whole review round.
4. For a committed base, give reviewers a read-only checkout so they can run one test without touching the working tree:

   ```bash
   git worktree add --detach out/review/head <base>
   ```

5. Give every reviewer the patch paths, the base commit, and the checkout path. They review that snapshot. Dispatch both axes together and wait for their reports; do not poll `list_agents` — the runtime delivers each reviewer's message when it finishes.

If a finding needs code changes: stop the reviewers, make the changes, re-freeze, and start a fresh review. Do not keep the old reviewers running against a tree that moved.

## Reviewer instructions

- Treat the frozen patch as the change under review. Use the live repo only to read surrounding code and docs.
- Do not edit files, run the full suite, or wait for the working tree to change.
- Run one test only when a finding needs proof.
- Report findings; the implementation agent applies them.
- Report hard standards violations and spec misses first; baseline smells are judgement calls, so keep them to the top two.
- Keep the two axes separate: Standards (see `CODING_STANDARDS.md`) and Spec (the originating ticket under `.scratch/academic-digest/issues/`).
