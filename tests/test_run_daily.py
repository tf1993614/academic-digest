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

import fcntl
import os
import re
import subprocess
import time
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


def _log_path(repo: Path) -> Path:
    return repo / "out" / "logs" / "run-daily.log"


def _log(repo: Path) -> str:
    return _log_path(repo).read_text(encoding="utf-8")


def _wait_for(path: Path, timeout: float = 10.0) -> None:
    """Wait for a marker the client writes; every other assertion is state only."""

    deadline = time.monotonic() + timeout
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert path.exists(), f"{path} never appeared"


def _flags(text: str) -> set[str]:
    return set(re.findall(r"(?<![\w-])--?[A-Za-z][A-Za-z0-9-]*", text))


def _hold_lock(repo: Path):
    """Take the same kernel lock the wrapper's helper takes."""

    lock = repo / LOCK
    lock.parent.mkdir(parents=True, exist_ok=True)
    handle = lock.open("a+")
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return handle


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
    assert Path(_flag_value(args, "-o")) == repo / "out" / "logs" / "codex-last-message.md"
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
    assert _log_path(repo).stat().st_mode & 0o777 == 0o600, (
        "the log can hold secrets-adjacent errors; it must stay private"
    )
    assert result.stdout.count("\n") == 1, "only the pre-exec banner reaches stdout"
    assert result.stdout.startswith(f"[run-daily] {client}: ")


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


def test_a_client_killed_by_a_signal_maps_to_128_plus_n(
    skill_copy: Path, repo: Path, tmp_path: Path
) -> None:
    """Popen reports a signalled child as -N; the wrapper must report 128+N."""

    bin_dir = tmp_path / "killed-bin"
    bin_dir.mkdir()
    script = bin_dir / "claude"
    script.write_text("#!/usr/bin/env bash\nkill -TERM $$\n", encoding="utf-8")
    script.chmod(0o755)

    env = os.environ.copy()
    for name in ("PYTHONPATH", "SERVERCHAN_SENDKEY", "GITHUB_TOKEN"):
        env.pop(name, None)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    result = subprocess.run(
        [str(skill_copy / "scripts" / "run-daily.sh"), "claude"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 143, result.stderr
    assert "exited 143" in _log(repo)


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
    held = _hold_lock(repo)
    first = Stub(repo.parent / "first-bin", "claude")
    try:
        overlapping = _run(skill_copy, repo, "claude", stub=first)
    finally:
        held.close()

    assert overlapping.returncode == 0
    assert first.calls() == [], "the overlapping run must not start a second client"
    assert "another run holds the lock" in _log(repo)

    # The kernel releases the lock; nothing has to be cleaned up by hand.
    second = Stub(repo.parent / "second-bin", "claude")
    following = _run(skill_copy, repo, "claude", stub=second)
    assert following.returncode == 0
    assert second.calls(), "the next run must proceed once the holder is gone"


def test_the_lock_reports_the_client_exit_code_and_is_released(
    skill_copy: Path, repo: Path
) -> None:
    stub = Stub(repo.parent / "bin", "claude", exit_code=5)
    failed = _run(skill_copy, repo, "claude", stub=stub)
    assert failed.returncode == 5

    retry = Stub(repo.parent / "retry-bin", "claude")
    following = _run(skill_copy, repo, "claude", stub=retry)
    assert following.returncode == 0
    assert retry.calls(), "a failed run must not leave the lock behind"


def test_a_user_level_symlink_still_resolves_the_repository(
    repo: Path, tmp_path: Path
) -> None:
    _sync_to(repo)
    scan_root = tmp_path / "home" / ".claude" / "skills"
    scan_root.mkdir(parents=True)
    linked = scan_root / "academic-digest"
    linked.symlink_to(repo / SKILL, target_is_directory=True)
    stub = Stub(tmp_path / "bin", "claude")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()

    result = _run(linked, repo, "claude", stub=stub, cwd=elsewhere)
    assert result.returncode == 0, result.stderr
    assert stub.calls()[0]["cwd"] == str(repo)


def test_sigterm_is_forwarded_to_the_client(skill_copy: Path, repo: Path, tmp_path: Path) -> None:
    """A scheduler stop must reach the client, not orphan it behind the lock.

    This is the one bounded wait in the suite: the client writes a marker when
    it starts and another when it receives TERM, and the test polls for them
    instead of sleeping for a fixed period.
    """

    bin_dir = tmp_path / "signal-bin"
    bin_dir.mkdir()
    started = bin_dir / "started"
    termed = bin_dir / "termed"
    script = bin_dir / "claude"
    script.write_text(
        "#!/usr/bin/env bash\n"
        f"trap 'printf termed > {termed}; exit 143' TERM\n"
        f"printf started > {started}\n"
        "while :; do sleep 1; done\n",
        encoding="utf-8",
    )
    script.chmod(0o755)

    env = os.environ.copy()
    for name in ("PYTHONPATH", "SERVERCHAN_SENDKEY", "GITHUB_TOKEN"):
        env.pop(name, None)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    running = subprocess.Popen(
        [str(skill_copy / "scripts" / "run-daily.sh"), "claude"],
        cwd=repo,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _wait_for(started)
        running.terminate()
        status = running.wait(timeout=20)
    finally:
        if running.poll() is None:
            running.kill()
            running.wait(timeout=20)

    assert status == 143
    _wait_for(termed)


@pytest.mark.parametrize("client", ["claude", "codex"])
def test_scheduling_docs_document_the_argv_the_wrapper_passes(
    skill_copy: Path, repo: Path, client: str
) -> None:
    """The manual-run recipe and the wrapper's argv are one contract.

    Wrapper to docs: every flag/value the stub records must be documented.
    Docs to wrapper: the manual-run snippet may not pass a flag the wrapper
    does not pass, so a doc-only escape hatch fails too.
    """

    stub = Stub(repo.parent / "bin", client)
    result = _run(skill_copy, repo, client, stub=stub)
    assert result.returncode == 0, result.stderr
    args = stub.calls()[0]["args"]
    wrapper_flags = {arg for arg in args if arg.startswith("-")}

    doc = (
        ROOT
        / "skills"
        / "academic-digest"
        / "references"
        / "scheduling"
        / f"{client}.md"
    ).read_text(encoding="utf-8")

    for index, arg in enumerate(args):
        if not arg.startswith("-"):
            continue
        assert arg in doc, f"{client}: docs do not document {arg!r}"
        if arg in {"-C", "-o"}:
            # Values that only exist at run time; the doc names the flag itself.
            continue
        if index + 1 == len(args):
            continue
        value = args[index + 1]
        if value.startswith("-") or str(repo) in value or str(skill_copy) in value:
            continue
        assert f"{arg} {value}" in doc or f'{arg} "{value}"' in doc, (
            f"{client}: docs do not document {arg} {value!r}"
        )

    manual = re.search(r"## 先手动跑一次(.*?)```bash\n(.*?)```", doc, re.S)
    assert manual is not None, f"{client}: no manual-run snippet"
    # Drop the secrets prelude: `set -a` is a shell flag, not a client flag.
    manual_snippet = re.sub(r"(?m)^set -a.*\n", "", manual.group(2))
    documented_flags = _flags(manual_snippet)
    assert documented_flags, f"{client}: the manual-run snippet documents no flags"
    assert documented_flags <= wrapper_flags, (
        f"{client}: the docs pass flags the wrapper does not: "
        f"{sorted(documented_flags - wrapper_flags)}"
    )

    if client == "codex":
        assert "codex-last-message.md" in doc
