#!/usr/bin/env bash
# Freeze a diff into a reviewable patch plus metadata.
# Usage: scripts/review-patch.sh [--base REF] [output-patch]
#   (no --base)  working tree against HEAD, untracked files included
#   --base REF   committed range REF...HEAD; requires a clean working tree
# Default output: out/review/current.diff (out/ is gitignored).
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
cd "$root"

base="HEAD"
committed_base=false
out="out/review/current.diff"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --base)
      base="${2:?--base needs a git ref}"
      committed_base=true
      shift 2
      ;;
    *)
      out="$1"
      shift
      ;;
  esac
done
base="$(git rev-parse "$base")"
head="$(git rev-parse HEAD)"
case "$out" in
  /*) ;;
  *) out="$root/$out" ;;
esac
mkdir -p "$(dirname "$out")"

if [[ "$committed_base" == true ]]; then
  # A committed range is reviewable only when the working tree cannot move
  # under the reviewers; commit or stash first.
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "error: --base review needs a clean working tree; commit or stash first" >&2
    exit 1
  fi
  if git diff --quiet "$base"...HEAD; then
    echo "error: empty diff for $base...HEAD" >&2
    exit 1
  fi
  git diff "$base"...HEAD --binary > "$out"
  git diff "$base"...HEAD --stat > "$out.stat"
  files="$(git diff --name-only "$base"...HEAD | wc -l | tr -d ' ')"
else
  # Working tree against HEAD, untracked files included.
  if [[ -z "$(git diff HEAD --name-only)" ]] \
    && [[ -z "$(git ls-files --others --exclude-standard)" ]]; then
    echo "error: empty working-tree diff" >&2
    exit 1
  fi
  git diff HEAD --binary > "$out"
  while IFS= read -r file; do
    git diff --no-index --binary -- /dev/null "$file" >> "$out" || true
  done < <(git ls-files --others --exclude-standard)
  git diff HEAD --stat > "$out.stat"
  {
    echo "# untracked"
    git ls-files --others --exclude-standard
  } >> "$out.stat"
  files="$(( $(git diff --name-only HEAD | wc -l) + $(git ls-files --others --exclude-standard | wc -l) ))"
fi

git status --short > "$out.status"
printf '%s\n' "$base" > "$out.base"
printf '%s\n' "$head" > "$out.head"

printf 'frozen diff: %s\n' "$out"
printf 'frozen stat: %s.stat\n' "$out"
printf 'frozen base: %s.base\n' "$out"
printf 'frozen head: %s.head\n' "$out"
printf 'frozen files: %s\n' "$files"
