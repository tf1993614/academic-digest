#!/usr/bin/env bash
#
# Unattended entry point shared by the Claude Code and Codex schedules.
#
# Usage: run-daily.sh <claude|codex>
#
# A scheduler unit, plist or crontab line only needs this one command. The
# wrapper owns everything that is easy to get wrong outside a login shell:
#
#   - the repository root: config.yaml, secrets.env, out/ and state/ stay there
#     (the code travels with the skill, the runtime data stays with the repo);
#   - secrets.env, loaded into the client's environment;
#   - a per-repository kernel file lock, so a slow run is never stacked on;
#   - one append-only log, out/logs/run-daily.log;
#   - the client's exit code, passed through unchanged.
#
# DSH is not a client here: its schedule is a task-board card, which starts the
# session itself and never goes through this script.
set -uo pipefail
umask 077

usage() {
  printf 'usage: run-daily.sh <claude|codex>\n' >&2
  printf '  claude  claude -p "/academic-digest" (headless, skills discovered)\n' >&2
  printf '  codex   codex exec against this skill (sandbox network on)\n' >&2
}

if [[ $# -ne 1 ]]; then
  usage
  exit 2
fi
client="$1"
case "$client" in
  claude | codex) ;;
  *)
    usage
    exit 2
    ;;
esac

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
skill_dir="$(dirname "$script_dir")"
repo="$(git -C "$skill_dir" rev-parse --show-toplevel 2>/dev/null ||
  git -C "$PWD" rev-parse --show-toplevel 2>/dev/null)" || {
  printf '[fail] run-daily: neither %s nor %s is inside a git checkout\n' \
    "$skill_dir" "$PWD" >&2
  printf '       run the wrapper from the repository the digest belongs to\n' >&2
  exit 1
}

log_dir="$repo/out/logs"
log="$log_dir/run-daily.log"
mkdir -p "$log_dir" "$repo/state" || {
  printf '[fail] run-daily: cannot create %s or %s\n' "$log_dir" "$repo/state" >&2
  exit 1
}

# One summary line reaches the scheduler (journalctl / launchd / cron mail);
# everything else is appended to the log so no snippet needs its own redirect.
printf '[run-daily] %s: %s (log: %s)\n' "$client" "$repo" "$log"
exec >>"$log" 2>&1

runner=""
cleanup() {
  local status=$?
  printf '[run-daily] %s exited %s after %ss\n' "$client" "$status" "$SECONDS"
  exit "$status"
}

forward() {
  if [[ -n "$runner" ]]; then
    kill "-$1" "$runner" 2>/dev/null || true
  fi
  exit "$2"
}

trap cleanup EXIT
trap 'forward TERM 143' TERM
trap 'forward INT 130' INT

printf '=== %s run-daily %s repo=%s pid=%s\n' \
  "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$client" "$repo" "$$"

if [[ -f "$repo/secrets.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$repo/secrets.env"
  set +a
  printf '[ok] run-daily: loaded %s/secrets.env\n' "$repo"
else
  printf '[warn] run-daily: %s/secrets.env not found; relying on the inherited environment\n' \
    "$repo"
fi

for required in "$client" python3; do
  if ! command -v "$required" >/dev/null 2>&1; then
    printf '[fail] run-daily: %s not found on PATH\n' "$required"
    printf '       schedulers do not inherit your shell PATH; set it in the unit/plist/crontab\n'
    exit 1
  fi
done

cd "$repo" || {
  printf '[fail] run-daily: cannot enter %s\n' "$repo"
  exit 1
}

case "$client" in
  claude)
    # Keep this in step with references/scheduling/claude.md. --bare is absent
    # on purpose: it skips skill discovery, so /academic-digest would not expand.
    cmd=(
      claude
      -p "/academic-digest"
      --permission-mode acceptEdits
      --allowedTools "Bash(python3 *),Read,Write,Edit"
      --permission-prompts none
      --max-turns 60
      --output-format json
    )
    ;;
  codex)
    # Keep this in step with references/scheduling/codex.md. The sandbox network
    # switch is required: codex exec turns network access off by default.
    cmd=(
      codex exec
      -C "$repo"
      --sandbox workspace-write
      -c sandbox_workspace_write.network_access=true
      --skip-git-repo-check
      --json
      -o "$log_dir/codex-last-message.md"
      "读取 $skill_dir/SKILL.md 并照做：按“每日运行”跑 collect、写日报、digest check、push。secrets.env 已由 wrapper 加载到环境变量，不要打印密钥。"
    )
    ;;
esac

printf '[cmd] %s\n' "${cmd[*]}"
python3 "$script_dir/run-daily-lock.py" "$repo/state/run-daily.lock" "${cmd[@]}" &
runner=$!
wait "$runner"
exit $?
