"""The unattended wrapper is the one shell path shared by the CLI clients.

Seam: ``scripts/run-daily.sh <client>`` is invoked exactly like a scheduler
would invoke it, with a stub ``claude`` / ``codex`` first on ``PATH``. The stub
records its argv, working directory and the loaded secrets; the wrapper keeps
its own output in ``out/logs/run-daily.log``. Nothing imports the wrapper or
calls an internal function.

The skill used here is a freshly generated copy placed *outside* any git
checkout, which is the user-level install shape: the wrapper then falls back to
the repository it was started from and writes all runtime data there.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SYNC = ROOT / "scripts" / "sync-skills.sh"
SKILL = Path(".claude") / "skills" / "academic-digest"
SENDKEY = "test-sendkey-value"

STUB = """#!/usr/bin/env bash
{{
  printf 'cwd=%s\\n' "$PWD"
  for arg in "$@"; do printf 'arg=%s\\n' "$arg"; done
  printf 'sendkey=%s\\n' "${{SERVERCHAN_SENDKEY-}}"
}} > "{record}"
{block}
exit {exit_code}
"""

BLOCK = """while [[ ! -e "{release}" ]]; do
  sleep 0.05
done"""


class Stub:
    """A fake client CLI plus the files it records into."""

    def __init__(self, bin_dir: Path, name: str, *, exit_code: int = 0, block: bool = False):
        self.bin_dir = bin_dir
        self.record = bin_dir / f"{name}.record"
        self.release = bin_dir / "release"
        bin_dir.mkdir(parents=True, exist_ok=True)
        script = bin_dir / name
        script.write_text(
            STUB.format(
                record=self.record,
                exit_code=exit_code,
                block=BLOCK.format(release=self.release) if block else "",
            ),
            encoding="utf-8",
        )
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


@pytest.fixture(scope="session")
def skill_copy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A generated copy outside the repository, as a user-level install would be."""

    home = tmp_path_factory.mktemp("skillhome")
    result = subprocess.run(
        ["bash", str(SYNC), str(home)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    skill = home / SKILL
    assert (skill / "scripts" / "run-daily.sh").is_file()
    return skill


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    (repo / "secrets.env").write_text(
        f"SERVERCHAN_SENDKEY={SENDKEY}\nGITHUB_TOKEN=test-github-token\n",
        encoding="utf-8",
    )
    return repo


def _run(skill: Path, repo: Path, *args: str, stub: Stub | None = None, timeout: int = 30):
    env = os.environ.copy()
    for name in ("PYTHONPATH", "SERVERCHAN_SENDKEY", "GITHUB_TOKEN"):
        env.pop(name, None)
    if stub is not None:
        env["PATH"] = f"{stub.bin_dir}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        [str(skill / "scripts" / "run-daily.sh"), *args],
        cwd=repo,
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
    first = Stub(repo.parent / "first-bin", "claude", block=True)
    second = Stub(repo.parent / "second-bin", "claude")

    running = subprocess.Popen(
        [str(skill_copy / "scripts" / "run-daily.sh"), "claude"],
        cwd=repo,
        env={
            **os.environ,
            "PATH": f"{first.bin_dir}{os.pathsep}{os.environ['PATH']}",
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while not first.record.is_file() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert first.record.is_file(), "the first run never reached the client"

        overlapping = _run(skill_copy, repo, "claude", stub=second, timeout=20)
        assert overlapping.returncode == 0
        assert second.calls() == [], "the overlapping run must not start a second client"
    finally:
        first.release.write_text("", encoding="utf-8")
        running.wait(timeout=20)
    assert running.returncode == 0


def test_a_lock_left_by_a_dead_process_does_not_block_forever(
    skill_copy: Path, repo: Path
) -> None:
    blocking = Stub(repo.parent / "blocking-bin", "claude", block=True)
    killed = subprocess.Popen(
        [str(skill_copy / "scripts" / "run-daily.sh"), "claude"],
        cwd=repo,
        env={
            **os.environ,
            "PATH": f"{blocking.bin_dir}{os.pathsep}{os.environ['PATH']}",
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.monotonic() + 10
    while not blocking.record.is_file() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert blocking.record.is_file(), "the killed run never reached the client"
    killed.kill()
    killed.wait(timeout=10)
    blocking.release.write_text("", encoding="utf-8")

    fast = Stub(repo.parent / "fast-bin", "claude")
    result = _run(skill_copy, repo, "claude", stub=fast, timeout=20)
    assert result.returncode == 0
    assert fast.calls(), "a stale lock must be reclaimed instead of skipping forever"
