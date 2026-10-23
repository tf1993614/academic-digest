# Code review

Review a frozen diff, never a moving working tree. A reviewer that sees the tree change while it reads has to re-read or wait; during the 03 implementation two review subagents burned their runs polling `git diff` and never reported.

## Before you freeze

- Walk the ticket checklist and confirm every item has a test or fixture that fails without it.
- Check every documented default and every "no update means no block" claim.
- Grep `README.md`, `CODING_STANDARDS.md`, the ADR, and the ticket for every payload key you added, renamed, or removed.
- For new concurrency, locking, signal, or atomicity code: name the kernel primitive and list the failure modes in the ticket (SIGKILL, PID reuse, TOCTOU, fd inheritance, the signal window). Shell bookkeeping must say why a kernel primitive will not do. **A second blocking finding on the same mechanism means redesign, not another patch.**
- Any doc that repeats a command, flag, or default: make the test derive one side from the other (see `CODING_STANDARDS.md` §Docs). Two hand-written literals in the test check nothing.
- Run the suite the way the hook does: the pre-commit hook checks the index out into a directory with **no `.git`**, so a new test must not require git metadata (skip that branch, or read the checked-out file instead).
- If the ticket ships a path that a cited research doc still calls non-existent, amend that citation with a dated note in this diff.
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
   scripts/review-patch.sh --verify          # treehash and HEAD must still match
   scripts/review-patch.sh --verify --base 08def36   # same check for a committed range
   ```

   `--verify` re-freezes into a temp directory and fails if the patch or a generated copy moved since the freeze; it also fails when `HEAD` (or the `--base` ref) moved. A stale patch costs a whole review round. `frozen files` already excludes the generated copies, so it needs no manual count.
4. For a committed base, give reviewers a read-only checkout so they can run one test without touching the working tree:

   ```bash
   git worktree add --detach out/review/head <base>
   ```

5. Give every reviewer the patch paths, the base commit, and the checkout path. They review that snapshot. Dispatch both axes together and wait for their reports; do not poll `list_agents` — the runtime delivers each reviewer's message when it finishes.

If a finding needs code changes: stop the reviewers, make the changes, re-freeze against the **previous frozen head** and review the delta; re-review the full range only when the fix is a redesign (the concurrency rule above). Do not keep the old reviewers running against a tree that moved.

## Reviewer instructions

- Treat the frozen patch as the change under review. Use the live repo only to read surrounding code and docs.
- Do not edit files, run the full suite, or wait for the working tree to change.
- Run one test only when a finding needs proof.
- Report findings; the implementation agent applies them.
- Report hard standards violations and spec misses first; baseline smells are judgement calls, so keep them to the top two.
- Keep the two axes separate: Standards (see `CODING_STANDARDS.md`) and Spec (the originating ticket under `.scratch/oss-release/issues/`).
- The generated client copies are not in the patch. Verify them with `scripts/check-skills.sh` (or the `.generated` hashes); review the source skill, the sync/check scripts, and the docs instead. Ask for `--include-generated` only when the sync output itself is under review.
