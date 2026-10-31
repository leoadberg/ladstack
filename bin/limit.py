#!/usr/bin/env python3
"""limit.py SECONDS COMMAND: run COMMAND in its own process group and kill the group at the limit.

Replaces coreutils timeout, which macOS does not ship. Exits 124 when the limit was hit."""
import os
import shutil
import signal
import subprocess
import sys

GRACE = 5
KILLED_MESSAGE = """HARD TIMEOUT: command killed after {}s. Before anything else:
1. List survivors on every host it touched, read-only. Killing the local ssh can leave the remote command running.
2. Kill by exact PID only, after reading its command line. Never pkill -f.
3. If a kill is denied, stop and tell the user the PID and what it is doing.
4. Do not rerun the command. Find a faster way."""


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
