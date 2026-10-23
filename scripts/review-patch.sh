#!/usr/bin/env bash
# Freeze a diff into a reviewable patch plus metadata.
# Usage: scripts/review-patch.sh [--base REF] [--include-generated] [--verify] [output-patch]
#   (no --base)  working tree against HEAD, untracked files included
#   --base REF   committed range REF...HEAD; requires a clean working tree
#   --include-generated  keep the generated client copies in the content diff
#   --verify     fail if HEAD, the --base ref, or the working tree moved since the freeze
# Default output: out/review/current.diff (out/ is gitignored).
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
cd "$root"

base="HEAD"
committed_base=false
include_generated=false
verify=false
out="out/review/current.diff"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --base)
      base="${2:?--base needs a git ref}"
      committed_base=true
      shift 2
      ;;
    --include-generated)
      include_generated=true
      shift
      ;;
    --verify)
      verify=true
      shift
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

generated_roots=(
  ".dsh/skills/academic-digest"
  ".claude/skills/academic-digest"
  ".agents/skills/academic-digest"
)

excludes=()
if [[ "$include_generated" == false ]]; then
  for generated_root in "${generated_roots[@]}"; do
    excludes+=(":(exclude)$generated_root" ":(exclude)$generated_root/**")
  done
fi

write_generated_hashes() {
  python3 - "$root" <<'PY'
import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
for relative_root in (
    ".dsh/skills/academic-digest",
    ".claude/skills/academic-digest",
    ".agents/skills/academic-digest",
):
    directory = root / relative_root
    if not directory.is_dir():
        continue
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            print(f"{digest}  {path.relative_to(root)}")
PY
}

tree_hash() {
  cat "$1" "$2" | git hash-object --stdin
}

is_generated_path() {
  case "$1" in
    .dsh/skills/academic-digest/* | \
      .claude/skills/academic-digest/* | \
      .agents/skills/academic-digest/*) return 0 ;;
    *) return 1 ;;
  esac
}

freeze() {
  local target="$1"
  local files
  mkdir -p "$(dirname "$target")"

  if [[ "$committed_base" == true ]]; then
    if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
      echo "error: --base review needs a clean tracked tree; commit or stash first" >&2
      exit 1
    fi
    if git diff --quiet "$base"...HEAD --no-color --no-ext-diff -- . ${excludes[@]+"${excludes[@]}"}; then
      echo "error: empty diff for $base...HEAD after excluding generated copies; pass --include-generated to inspect them" >&2
      exit 1
    fi
    git diff "$base"...HEAD --binary --no-color --no-ext-diff -- . ${excludes[@]+"${excludes[@]}"} >"$target"
    git diff "$base"...HEAD --stat --no-color --no-ext-diff -- . ${excludes[@]+"${excludes[@]}"} >"$target.stat"
    files="$(git diff --name-only "$base"...HEAD -- . ${excludes[@]+"${excludes[@]}"} | wc -l | tr -d ' ')"
  else
    local tracked_diff
    tracked_diff="$(git diff HEAD --name-only -- . ${excludes[@]+"${excludes[@]}"})"
    local untracked=()
    while IFS= read -r file; do
      [[ -n "$file" ]] || continue
      if [[ "$include_generated" == false ]] && is_generated_path "$file"; then
        continue
      fi
      untracked+=("$file")
    done < <(git ls-files --others --exclude-standard)

    if [[ -z "$tracked_diff" && ${#untracked[@]} -eq 0 ]]; then
      echo "error: empty working-tree diff after excluding generated copies; pass --include-generated to inspect them" >&2
      exit 1
    fi

    git diff HEAD --binary --no-color --no-ext-diff -- . ${excludes[@]+"${excludes[@]}"} >"$target"
    if [[ ${#untracked[@]} -gt 0 ]]; then
      for file in "${untracked[@]}"; do
        git diff --no-index --binary --no-color -- /dev/null "$file" >>"$target" || true
      done
    fi
    git diff HEAD --stat --no-color --no-ext-diff -- . ${excludes[@]+"${excludes[@]}"} >"$target.stat"
    {
      echo "# untracked"
      if [[ ${#untracked[@]} -gt 0 ]]; then
        printf '%s\n' "${untracked[@]}"
      fi
    } >>"$target.stat"
    files="$(( $(git diff --name-only HEAD -- . ${excludes[@]+"${excludes[@]}"} | wc -l) + ${#untracked[@]} ))"
  fi

  write_generated_hashes >"$target.generated"
  printf '%s\n' "$(tree_hash "$target" "$target.generated")" >"$target.treehash"
  git status --porcelain >"$target.status"
  printf '%s\n' "$base" >"$target.base"
  printf '%s\n' "$head" >"$target.head"

  printf 'frozen diff: %s\n' "$target"
  printf 'frozen stat: %s.stat\n' "$target"
  printf 'frozen generated: %s.generated\n' "$target"
  printf 'frozen treehash: %s.treehash\n' "$target"
  printf 'frozen base: %s.base\n' "$target"
  printf 'frozen head: %s.head\n' "$target"
  printf 'frozen files: %s\n' "$files"
}

if [[ "$verify" == true ]]; then
  if [[ ! -f "$out.treehash" ]]; then
    echo "error: no frozen tree at $out.treehash; freeze first" >&2
    exit 1
  fi
  frozen_base="$(cat "$out.base" 2>/dev/null || true)"
  frozen_head="$(cat "$out.head" 2>/dev/null || true)"
  if [[ "$frozen_base" != "$base" || "$frozen_head" != "$head" ]]; then
    echo "[fail] review-patch: HEAD moved since the freeze (base $frozen_base -> $base, head $frozen_head -> $head); re-freeze before dispatch" >&2
    exit 1
  fi
  verify_dir="$(mktemp -d)"
  trap 'rm -rf "$verify_dir"' EXIT
  freeze "$verify_dir/current.diff" >/dev/null
  if [[ "$(cat "$out.treehash")" == "$(cat "$verify_dir/current.diff.treehash")" ]]; then
    echo "[ok] review-patch: frozen patch still matches"
    exit 0
  fi
  echo "[fail] review-patch: working tree changed since the freeze; re-freeze before dispatch" >&2
  exit 1
fi

freeze "$out"
