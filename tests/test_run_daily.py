"""The unattended wrapper is the one shell path shared by the CLI clients.

Seam: ``scripts/run-daily.sh <client>`` is invoked exactly like a scheduler
would invoke it, with a stub ``claude`` / ``codex`` first on ``PATH``. The stub
records its argv, working directory and the loaded secrets; the wrapper keeps
its own output in ``out/logs/run-daily.log``. Nothing imports the wrapper or
calls an internal function.

Two skill layouts are exercised, because the wrapper resolves the repository
root in two steps: the checkout that owns the skill (a generated copy inside a
git repository), and, when the skill was copied into a client scan root, the
repository the wrapper was started from.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SYNC = ROOT / "scripts" / "sync-skills.sh"
SKILL = Path(".claude") / "skills" / "academic-digest"
SENDKEY = "test-sendkey-value"
LOCK = Path("state") / "run-daily.lock"

STUB = """#!/usr/bin/env bash
{{
  printf 'cwd=%s\\n' "$PWD"
  for arg in "$@"; do printf 'arg=%s\\n' "$arg"; done
  printf 'sendkey=%s\\n' "${{SERVERCHAN_SENDKEY-}}"
}} > "{record}"
exit {exit_code}
"""


class Stub:
    """A fake client CLI plus the record it writes."""

    def __init__(self, bin_dir: Path, name: str, *, exit_code: int = 0):
        self.bin_dir = bin_dir
        self.record = bin_dir / f"{name}.record"
        bin_dir.mkdir(parents=True, exist_ok=True)
        script = bin_dir / name
        script.write_text(STUB.format(record=self.record, exit_code=exit_code), encoding="utf-8")
        script.chmod(0o755)

    def calls(self) -> list[dict[str, Any]]:
        if not self.record.is_file():
            return []
        calls: list[dict[str, Any]] = []
        for line in self.record.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            if key == "cwd":
                calls.append({"cwd": value, "args": [], "sendkey": ""})
            elif key == "arg" and calls:
                calls[-1]["args"].append(value)
            elif key == "sendkey" and calls:
                calls[-1]["sendkey"] = value
        return calls


def _sync_to(target: Path) -> None:
    result = subprocess.run(
        ["bash", str(SYNC), str(target)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr


def _git_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    (path / "secrets.env").write_text(
        f"SERVERCHAN_SENDKEY={SENDKEY}\nGITHUB_TOKEN=test-github-token\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture(scope="session")
def skill_copy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A generated copy outside any git checkout, as a client scan root would be."""

    home = tmp_path_factory.mktemp("skillhome")
    _sync_to(home)
    skill = home / SKILL
    assert (skill / "scripts" / "run-daily.sh").is_file()
    return skill


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return _git_repo(tmp_path / "repo")


def _run(
    skill: Path,
    repo: Path,
    *args: str,
    stub: Stub | None = None,
    cwd: Path | None = None,
    timeout: int = 30,
):
    env = os.environ.copy()
    for name in ("PYTHONPATH", "SERVERCHAN_SENDKEY", "GITHUB_TOKEN"):
        env.pop(name, None)
    if stub is not None:
        env["PATH"] = f"{stub.bin_dir}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        [str(skill / "scripts" / "run-daily.sh"), *args],
        cwd=cwd or repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _flag_value(args: list[str], flag: str) -> str:
    assert flag in args, f"{flag} missing from {args}"
    index = args.index(flag)
    assert index + 1 < len(args), f"{flag} has no value in {args}"
    return args[index + 1]


def _log(repo: Path) -> str:
    return (repo / "out" / "logs" / "run-daily.log").read_text(encoding="utf-8")


def _dead_pid() -> int:
    """A PID that belonged to a process which has already exited."""

    process = subprocess.Popen(["true"])
    process.wait(timeout=10)
    return process.pid


def _hold_lock(repo: Path, *, holder: int, client: int | None = None) -> Path:
    """Write the runtime lock the wrapper reads, as a crashed run would leave it."""

    lock = repo / LOCK
    lock.mkdir(parents=True)
    (lock / "pid").write_text(f"{holder}\n", encoding="utf-8")
    if client is not None:
        (lock / "client").write_text(f"{client}\n", encoding="utf-8")
    return lock


def test_claude_argv_is_the_documented_headless_form(skill_copy: Path, repo: Path) -> None:
    stub = Stub(repo.parent / "bin", "claude")
    result = _run(skill_copy, repo, "claude", stub=stub)
    assert result.returncode == 0, result.stderr

    calls = stub.calls()
    assert len(calls) == 1
    args = calls[0]["args"]
    assert args[0] == "-p"
    assert args[1] == "/academic-digest"
    assert _flag_value(args, "--permission-mode") == "acceptEdits"
    assert _flag_value(args, "--allowedTools") == "Bash(python3 *),Read,Write,Edit"
    assert _flag_value(args, "--permission-prompts") == "none"
    assert _flag_value(args, "--max-turns") == "60"
    assert _flag_value(args, "--output-format") == "json"
    assert "--bare" not in args, "--bare skips skill discovery; the wrapper must not add it"


def test_codex_argv_is_the_documented_exec_form(skill_copy: Path, repo: Path) -> None:
    stub = Stub(repo.parent / "bin", "codex")
    result = _run(skill_copy, repo, "codex", stub=stub)
    assert result.returncode == 0, result.stderr

    calls = stub.calls()
    assert len(calls) == 1
    args = calls[0]["args"]
    assert args[0] == "exec"
    assert _flag_value(args, "-C") == str(repo)
    assert _flag_value(args, "--sandbox") == "workspace-write"
    assert (
        _flag_value(args, "-c") == "sandbox_workspace_write.network_access=true"
    ), "codex would time out on PubMed without the sandbox network switch"
    assert "--skip-git-repo-check" in args
    assert "--json" in args
    assert Path(_flag_value(args, "-o")).parent == repo / "out" / "logs"
    prompt = args[-1]
    assert str(skill_copy / "SKILL.md") in prompt
    assert "每日运行" in prompt


def test_wrapper_resolves_the_repository_that_owns_the_skill(
    repo: Path, tmp_path: Path
) -> None:
    """A skill inside a checkout runs that checkout, not the caller's directory."""

    _sync_to(repo)
    skill = repo / SKILL
    stub = Stub(tmp_path / "bin", "claude")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    result = _run(skill, repo, "claude", stub=stub, cwd=elsewhere)
    assert result.returncode == 0, result.stderr
    assert stub.calls()[0]["cwd"] == str(repo)
    assert (repo / "out" / "logs" / "run-daily.log").is_file()


@pytest.mark.parametrize("client", ["claude", "codex"])
def test_wrapper_runs_in_the_repository_and_loads_its_secrets(
    skill_copy: Path, repo: Path, client: str
) -> None:
    stub = Stub(repo.parent / "bin", client)
    result = _run(skill_copy, repo, client, stub=stub)
    assert result.returncode == 0, result.stderr

    call = stub.calls()[0]
    assert call["cwd"] == str(repo)
    assert call["sendkey"] == SENDKEY

    log = _log(repo)
    assert f"run-daily {client}" in log
    assert "exited 0" in log


def test_a_missing_secrets_file_still_runs_from_the_inherited_environment(
    skill_copy: Path, repo: Path
) -> None:
    (repo / "secrets.env").unlink()
    stub = Stub(repo.parent / "bin", "claude")
    result = _run(skill_copy, repo, "claude", stub=stub)
    assert result.returncode == 0, result.stderr
    assert stub.calls(), "a missing secrets.env is a warning, not a reason to skip the day"
    assert "secrets.env" in _log(repo)


@pytest.mark.parametrize(("client", "code"), [("claude", 3), ("codex", 7)])
def test_wrapper_passes_the_client_exit_code_through(
    skill_copy: Path, repo: Path, client: str, code: int
) -> None:
    stub = Stub(repo.parent / "bin", client, exit_code=code)
    result = _run(skill_copy, repo, client, stub=stub)
    assert result.returncode == code
    assert f"exited {code}" in _log(repo)


@pytest.mark.parametrize("args", [(), ("openai",), ("claude", "extra")])
def test_an_unknown_client_is_a_usage_error(
    skill_copy: Path, repo: Path, args: tuple[str, ...]
) -> None:
    stub = Stub(repo.parent / "bin", "claude")
    result = _run(skill_copy, repo, *args, stub=stub)
    assert result.returncode == 2
    assert "usage:" in result.stderr
    assert "claude" in result.stderr and "codex" in result.stderr
    assert stub.calls() == [], "an invalid argument must not start a client"


def test_a_live_lock_skips_the_overlapping_run(skill_copy: Path, repo: Path) -> None:
    lock = _hold_lock(repo, holder=os.getpid())
    stub = Stub(repo.parent / "bin", "claude")

    result = _run(skill_copy, repo, "claude", stub=stub)
    assert result.returncode == 0
    assert stub.calls() == [], "the overlapping run must not start a second client"
    assert "still active" in _log(repo)
    assert (lock / "pid").is_file(), "the live holder's lock must not be removed"


def test_a_lock_whose_client_outlived_the_wrapper_is_not_reclaimed(
    skill_copy: Path, repo: Path
) -> None:
    """A SIGKILLed wrapper can leave its client running; that still blocks a second client."""

    _hold_lock(repo, holder=_dead_pid(), client=os.getpid())
    stub = Stub(repo.parent / "bin", "claude")

    result = _run(skill_copy, repo, "claude", stub=stub)
    assert result.returncode == 0
    assert stub.calls() == [], "a client that is still running must not get a sibling"
    assert "still active" in _log(repo)


def test_a_lock_left_by_dead_processes_is_reclaimed(skill_copy: Path, repo: Path) -> None:
    _hold_lock(repo, holder=_dead_pid(), client=_dead_pid())
    stub = Stub(repo.parent / "bin", "claude")

    result = _run(skill_copy, repo, "claude", stub=stub)
    assert result.returncode == 0
    assert stub.calls(), "a stale lock must be reclaimed instead of skipping forever"
    assert "stale lock" in _log(repo)
    assert not (repo / LOCK).exists(), "the run's own lock must be released at exit"
