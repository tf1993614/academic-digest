#!/usr/bin/env bash
# Freeze a diff into a reviewable patch plus metadata.
# Usage: scripts/review-patch.sh [--base REF] [output-patch]
#   (no --base)  working tree against HEAD, untracked files included
#   --base REF   committed range REF..HEAD; untracked files are not part of it
# Default output: out/review/current.diff (out/ is gitignored).
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
cd "$root"

base="HEAD"
out="out/review/current.diff"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --base)
      base="${2:?--base needs a git ref}"
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

git diff "$base" --binary > "$out"
if [[ "$base" == "$head" ]]; then
  while IFS= read -r file; do
    git diff --no-index --binary -- /dev/null "$file" >> "$out" || true
  done < <(git ls-files --others --exclude-standard)
fi

git diff "$base" --stat > "$out.stat"
if [[ "$base" == "$head" ]]; then
  {
    echo "# untracked"
    git ls-files --others --exclude-standard
  } >> "$out.stat"
fi
git status --short > "$out.status"
printf '%s\n' "$base" > "$out.base"
printf '%s\n' "$head" > "$out.head"

printf 'frozen diff: %s\n' "$out"
printf 'frozen stat: %s.stat\n' "$out"
printf 'frozen base: %s.base\n' "$out"
printf 'frozen head: %s.head\n' "$out"
