#!/usr/bin/env bash
# Freeze the current working tree into a reviewable patch plus metadata.
# Usage: scripts/review-patch.sh [output-patch]
# Default output: out/review/current.diff (out/ is gitignored).
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
cd "$root"

out="${1:-out/review/current.diff}"
case "$out" in
  /*) ;;
  *) out="$root/$out" ;;
esac
mkdir -p "$(dirname "$out")"

git diff HEAD --binary > "$out"
while IFS= read -r file; do
  git diff --no-index --binary -- /dev/null "$file" >> "$out" || true
done < <(git ls-files --others --exclude-standard)

git diff HEAD --stat > "$out.stat"
{
  echo "# untracked"
  git ls-files --others --exclude-standard
} >> "$out.stat"
git status --short > "$out.status"
git rev-parse HEAD > "$out.head"

printf 'frozen diff: %s\n' "$out"
printf 'frozen stat: %s.stat\n' "$out"
printf 'frozen status: %s.status\n' "$out"
printf 'base commit: %s.head\n' "$out"
