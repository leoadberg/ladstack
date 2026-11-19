#!/usr/bin/env python3
"""PreToolUse on Bash: run every command under a hard limit, 10 s unless the user granted more.

A command that would let a job outlive the limit is refused, grant or not: one that detaches it from the
process group (nohup, setsid, systemd-run, disown, a new tmux or screen session), or that backgrounds it
inside an ssh command, where the group kill does not reach."""
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
# a lone & (not &&, >&, &>, |&)
BACKGROUND = re.compile(r"(?<![&>|<])&(?![&>])")
SSH_END = {";", "&", "&&", "|", "||", "|&", ";;", "(", ")"}
BLOCKED_MESSAGE = """{} is blocked: it lets a job outlive the time limit, which kills only the local process group
and does not reach through ssh. Run the command in the foreground, and bound any remote command with its own
timeout. If it cannot finish within the limit, profile it and make it faster, or ask the user to re-attempt with
a long: grant in their message (for example long:10m). Do not look for another way to detach it."""


def remote_background(command):
    """Whether a remote command given to ssh backgrounds a job: killing the local ssh leaves it running."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return False
    in_ssh = False
    for token in tokens:
        if token in SSH_END:
            in_ssh = False
        elif token.rsplit("/", 1)[-1] == "ssh":
            in_ssh = True
        elif in_ssh and BACKGROUND.search(token):
            return True
    return False


def refusal(command):
    match = DETACH.search(command)
    if match:
        return match.group(1).split()[0]
    if remote_background(command):
        return "& inside an ssh command"
    return None


def granted_limit(session_id):
    path = Path.home() / ".claude" / "grants" / "{}.json".format(session_id)
    return json.loads(path.read_text())["limit"] if path.exists() else None


try:
    event = json.load(sys.stdin)
    tool_input = dict(event["tool_input"])
    command = tool_input["command"]
    blocked = refusal(command)
    if blocked:
        print(BLOCKED_MESSAGE.format(blocked), file=sys.stderr)
        sys.exit(2)
    limit = granted_limit(event["session_id"])
    if limit is None:
        limit = DEFAULT_LIMIT
        tool_input.pop("run_in_background", None)
    tool_input["timeout"] = (limit + 10) * 1000
    tool_input["command"] = " ".join(shlex.quote(part) for part in [sys.executable, str(LIMIT), str(limit), command])
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": tool_input}}))
except Exception as e:
    print("timeout hook failed, command blocked: {}".format(e), file=sys.stderr)
    sys.exit(2)
