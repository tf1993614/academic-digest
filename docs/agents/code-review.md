# Code review

Review a frozen diff, never a moving working tree. A reviewer that sees the tree change while it reads has to re-read or wait; during the 03 implementation two review subagents burned their runs polling `git diff` and never reported.

## Before you freeze

- Walk the ticket checklist and confirm every item has a test or fixture that fails without it.
- Check every documented default and every "no update means no block" claim.
- Grep `README.md`, `CODING_STANDARDS.md`, the ADR, and the ticket for every payload key you added, renamed, or removed.
- Fix these before dispatching. A review round costs two subagent runs.

## Freeze the diff

1. Stop editing. A commit is cleanest; uncommitted changes are fine as long as they stay still. For a committed range, commit or stash tracked changes first: `--base` refuses a dirty tracked tree but tolerates untracked notes.
2. Run one of:

   ```bash
   scripts/review-patch.sh                 # uncommitted work: working tree vs HEAD
   scripts/review-patch.sh --base 08def36  # committed work: 08def36...HEAD
   ```

   It writes `out/review/current.diff`, plus `.stat`, `.status`, `.base`, `.head`, `.generated`, `.treehash`, and prints `frozen files: N`. The three generated client copies are **excluded from the content diff by default**; `.generated` holds their sha256 hashes and `.treehash` fingerprints the patch plus those hashes. `--base` reviews the committed range and fails on a dirty tree or an empty diff; only the working-tree mode includes untracked files. Add `--include-generated` only when the sync script or the copies themselves are the subject of review.
3. Verify the freeze before dispatching:

   ```bash
   cat out/review/current.diff.head          # must equal: git rev-parse HEAD
   git rev-parse HEAD
   scripts/review-patch.sh --verify          # working-tree mode: treehash must still match
   ```

   `--verify` re-freezes into a temp directory and fails if the patch or a generated copy moved since the freeze. A stale patch costs a whole review round. For a committed base, `frozen files` already excludes the generated copies; compare it against `git diff --name-only <base>...HEAD` minus those paths, or skip the manual count and rely on the treehash.
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
- Keep the two axes separate: Standards (see `CODING_STANDARDS.md`) and Spec (the originating ticket under `.scratch/oss-release/issues/`).
- The generated client copies are not in the patch. Verify them with `scripts/check-skills.sh` (or the `.generated` hashes); review the source skill, the sync/check scripts, and the docs instead. Ask for `--include-generated` only when the sync output itself is under review.
