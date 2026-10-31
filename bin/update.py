#!/usr/bin/env python3
"""Fast-forward to origin/main, only if the new revision's tests pass, then reapply setup."""
import datetime
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "update.log"
MAX_LOG_BYTES = 1000000
# launchd and cron start with a minimal PATH
os.environ["PATH"] = os.environ.get("PATH", "") + ":/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"


def log(message):
    if LOG.exists() and LOG.stat().st_size > MAX_LOG_BYTES:
        LOG.unlink()
    with LOG.open("a") as f:
        f.write("{} {}\n".format(datetime.datetime.now(datetime.timezone.utc).isoformat(), message))


def git(*args, **kwargs):
    return subprocess.run(["git", "-C", str(ROOT)] + list(args), check=True, timeout=30,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)


def tests_pass(rev):
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "rev.tar"
        with archive.open("wb") as f:
            subprocess.run(["git", "-C", str(ROOT), "archive", rev], check=True, timeout=30, stdout=f)
        with tarfile.open(str(archive)) as tar:
            tar.extractall(tmp)
        return subprocess.run([sys.executable, str(Path(tmp) / "tests" / "test_ladstack.py"), "-q"], timeout=30,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT).returncode == 0


def main():
    git("fetch", "-q", "origin", "main")
    head = git("rev-parse", "HEAD").stdout.decode().strip()
    target = git("rev-parse", "FETCH_HEAD").stdout.decode().strip()
    if head == target:
        return
    if not tests_pass(target):
        log("staying on {}: tests fail on {}".format(head, target))
        return
    git("merge", "-q", "--ff-only", target)
    subprocess.run([sys.executable, str(ROOT / "bin" / "setup.py"), "--hooks-only"], check=True, timeout=30,
                   stdout=subprocess.PIPE)
    log("updated {} -> {}".format(head, target))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log("update failed: {}".format(e))
        sys.exit(1)
