#!/usr/bin/env python3
"""PreToolUse on Bash: run every command under a hard limit, 10 s unless the user granted more (long:).

A command that would let a job outlive the limit is refused unless the user granted it (background:ok): one that
detaches it from the process group (nohup, setsid, systemd-run, disown, a new tmux or screen session)."""
import json
import re
import shlex
import sys
from pathlib import Path

DEFAULT_LIMIT = 10
LIMIT = Path(__file__).resolve().parent.parent / "bin" / "limit.py"
# a detaching command where a command starts, here or inside a quoted remote command (ssh host 'nohup ...')
DETACH = re.compile(r"""(?:^|[;&|(`'"\n]|\$\()\s*(?:\w+=\S*\s+)*(?:sudo\s+|env\s+)*"""
                    r"""(nohup|setsid|systemd-run|disown|tmux\s+new(?:-session)?|screen\s+(?:\S+\s+)*-d\S*)(?:\s|$)""")
BLOCKED_MESSAGE = """{} is blocked: it lets a job outlive the time limit, which kills only the local process group
and does not reach through ssh. Run the command in the foreground, and bound any remote command with its own
timeout. If it cannot finish within the limit, profile it and make it faster, or ask the user to re-attempt with
a long: grant in their message (for example long:10m), or a background:ok grant for a job that must outlive its
command. Do not look for another way to detach it."""


def refusal(command):
    match = DETACH.search(command)
    if match:
        return match.group(1).split()[0]
    return None


def grant(session_id):
    path = Path.home() / ".claude" / "grants" / "{}.json".format(session_id)
    return json.loads(path.read_text()) if path.exists() else {"limit": None, "background": False}


try:
    event = json.load(sys.stdin)
    tool_input = dict(event["tool_input"])
    command = tool_input["command"]
    granted = grant(event["session_id"])
    blocked = refusal(command)
    if blocked and not granted["background"]:
        print(BLOCKED_MESSAGE.format(blocked), file=sys.stderr)
        sys.exit(2)
    limit = granted["limit"]
    if limit is None:
        limit = DEFAULT_LIMIT
        tool_input.pop("run_in_background", None)
    tool_input["timeout"] = (limit + 10) * 1000
    tool_input["command"] = " ".join(shlex.quote(part) for part in [sys.executable, str(LIMIT), str(limit), command])
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": tool_input}}))
except Exception as e:
    print("timeout hook failed, command blocked: {}".format(e), file=sys.stderr)
    sys.exit(2)
