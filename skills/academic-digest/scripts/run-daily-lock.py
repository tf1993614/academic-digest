#!/usr/bin/env python3
"""Run one client under a per-repository exclusive lock.

``run-daily.sh`` calls this; a scheduler never does. The lock is a kernel
``flock`` on ``state/run-daily.lock``, so the kernel releases it when this
process dies: there is no stale lock to reclaim and no PID-reuse ambiguity. A
second run that finds the lock held exits 0 without starting a client, which is
what a scheduler should do for an overlapping run.

The client's exit code is this process's exit code, and TERM/INT/HUP are
forwarded to the client so a scheduler stop does not leave it running.
"""

from __future__ import annotations

import fcntl
import os
import signal
import subprocess
import sys


def main() -> int:
    lock_path = sys.argv[1]
    argv = sys.argv[2:]
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print("[skip] run-daily: another run holds the lock; not stacking another client")
        return 0

    child: subprocess.Popen[bytes] | None = None
    pending = 0

    def forward(signum: int, _frame: object) -> None:
        nonlocal pending
        if child is None:
            # A signal that lands between handler setup and Popen is replayed
            # once the client exists, so it cannot start after the scheduler
            # already stopped this run.
            pending = signum
            return
        try:
            child.send_signal(signum)
        except ProcessLookupError:
            pass

    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, forward)

    # The client inherits the locked descriptor, so the lock survives a SIGKILL
    # of this helper and is released only when the client itself is gone.
    child = subprocess.Popen(argv, pass_fds=(descriptor,))
    if pending:
        child.send_signal(pending)
    status = child.wait()
    # Popen reports a signalled child as -N; a shell reports 128+N.
    return 128 - status if status < 0 else status


if __name__ == "__main__":
    raise SystemExit(main())
