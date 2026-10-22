# Code review

Review a frozen diff, never a moving working tree. A reviewer that sees the tree change while it reads has to re-read or wait; during the 03 implementation two review subagents burned their runs polling `git diff` and never reported.

## Freeze the diff

1. Stop editing. A commit is cleanest; uncommitted changes are fine as long as they stay still.
2. Run one of:

   ```bash
   scripts/review-patch.sh                 # uncommitted work: working tree vs HEAD
   scripts/review-patch.sh --base 08def36  # committed work: 08def36..HEAD
   ```

   It writes `out/review/current.diff`, plus `.stat`, `.status`, `.base`, and `.head`. `out/` is gitignored. Only the working-tree mode includes untracked files.
3. For a committed base, give reviewers a read-only checkout so they can run one test without touching the working tree:

   ```bash
   git worktree add --detach out/review/head <base>
   ```

4. Give every reviewer the patch paths, the base commit, and the checkout path. They review that snapshot.

If a finding needs code changes: stop the reviewers, make the changes, re-freeze, and start a fresh review. Do not keep the old reviewers running against a tree that moved.

## Reviewer instructions

- Treat the frozen patch as the change under review. Use the live repo only to read surrounding code and docs.
- Do not edit files, run the full suite, or wait for the working tree to change.
- Run one test only when a finding needs proof.
- Report findings; the implementation agent applies them.
- Keep the two axes separate: Standards (see `CODING_STANDARDS.md`) and Spec (the originating ticket under `.scratch/academic-digest/issues/`).
