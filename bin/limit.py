#!/usr/bin/env python3
"""limit.py SECONDS COMMAND: run COMMAND in its own process group and kill the group at the limit.

Replaces coreutils timeout, which macOS does not ship. Exits 124 when the limit was hit."""
import os
import shutil
import signal
import subprocess
import sys

GRACE = 5
KILLED_MESSAGE = """HARD TIMEOUT: this command was killed. This applies only to this command and closely similar
ones, and tells you nothing about how long anything else will take.

Run every other command exactly as you would have without this message. Do not estimate
runtimes, avoid a command or line of work, shrink its scope, or ask for permission because of
this kill. Your guesses about runtime are unreliable, and most commands finish in milliseconds.
Running a command is the only valid test: if it is too slow, it will be killed and you will be
told. Any number of separate short commands is fine.

For the killed command, work through these in order:

1. Clean up side effects of the kill, including leftover processes on this machine and any other
   it touched: killing a local ssh can leave the remote command running. List survivors
   read-only, then kill by exact PID after reading the command line, never pkill -f. If a kill
   is denied, stop and tell the user the PID and what it is doing.
2. Think hard about why it was slow. Usually it ran in an accidentally slow way: a build invoked
   incorrectly, an infinite loop or deadlock, scanning more data than intended. Do not rerun it
   unchanged. Do not move this same work to the background or split it into chunks, since that
   does not make it faster.
3. If this work is certainly what the user wants and has not been profiled, run a subset of it
   under a profiler such as perf or py-spy and fix what you find. A 2% speedup is not worth the
   effort, but 10x or larger speedups are often available.
4. Only if this killed work is certainly necessary and cannot be drastically sped up, ask the
   user to re-attempt with a long: grant in their message (for example long:10m). Never suggest
   a grant for a command that has not been killed."""


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
        print(KILLED_MESSAGE, flush=True)
        sys.exit(124)
    sys.exit(128 - code if code < 0 else code)


if __name__ == "__main__":
    main()
