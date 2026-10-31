#!/usr/bin/env python3
"""PreToolUse on Bash: run every command under a hard limit, 60 s unless the user granted more."""
import json
import shlex
import sys
from pathlib import Path

DEFAULT_LIMIT = 60
LIMIT = Path(__file__).resolve().parent.parent / "bin" / "limit.py"


def granted_limit(session_id):
    path = Path.home() / ".claude" / "grants" / "{}.json".format(session_id)
    return json.loads(path.read_text())["limit"] if path.exists() else None


try:
    event = json.load(sys.stdin)
    tool_input = dict(event["tool_input"])
    command = tool_input["command"]
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
