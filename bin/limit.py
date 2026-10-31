#!/usr/bin/env python3
"""limit.py SECONDS COMMAND: run COMMAND in its own process group and kill the group at the limit.

Replaces coreutils timeout, which macOS does not ship. Exits 124 when the limit was hit."""
import os
import shutil
import signal
import subprocess
import sys

GRACE = 5
KILLED_MESSAGE = """HARD TIMEOUT: command killed after {}s. Work through these in order:

1. Clean up side effects of the kill, including leftover processes on this machine and any other it touched: killing a
   local ssh can leave the remote command running. List survivors read-only, then kill by exact PID after reading the
   command line, never pkill -f. If a kill is denied, stop and tell the user the PID and what it is doing.
2. Think hard about how to do this task in less time. Nearly every time this message appears, the task was accidentally
   run in a slow way: a build invoked incorrectly, an infinite loop or deadlock, scanning more data than intended. Do not
   rerun the same command.
3. If this task is certainly what the user wants and it has not been profiled yet, run a subset of it under a profiler
   such as perf or py-spy to find speedups and performance regressions, then fix them. A 2% speedup is not worth the
   effort, but 10x or larger speedups are often available.
4. Only if the task is certainly necessary for the user's goal and cannot be drastically sped up, ask the user to
   re-attempt with a long: grant in their message (for example long:10m), and estimate how long the task will take."""


def kill_group(pgid, sig):
    try:
        os.killpg(pgid, sig)
    except ProcessLookupError:
        pass


def stop(child):
    kill_group(child.pid, signal.SIGTERM)
    try:
        child.wait(GRACE)
    except subprocess.TimeoutExpired:
        pass
    kill_group(child.pid, signal.SIGKILL)
    child.wait()


def main():
    limit, command = int(sys.argv[1]), sys.argv[2]
    shell = shutil.which("bash") or "/bin/sh"
    child = subprocess.Popen([shell, "-c", command], start_new_session=True)

    def on_signal(signum, _frame):
        stop(child)
        sys.exit(128 + signum)

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, on_signal)

    try:
        code = child.wait(limit)
    except subprocess.TimeoutExpired:
        stop(child)
        print(KILLED_MESSAGE.format(limit), flush=True)
        sys.exit(124)
    sys.exit(128 - code if code < 0 else code)


if __name__ == "__main__":
    main()
