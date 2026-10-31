#!/usr/bin/env python3
"""PreToolUse on Bash: run every command under a hard limit, 60 s unless the user granted more."""
import json
import re
import shlex
import sys
import time
from pathlib import Path

DEFAULT_LIMIT = 60
CHAINING = re.compile(r"[;&|`\n]|\$\(")
LIMIT = Path(__file__).resolve().parent.parent / "bin" / "limit.py"


def granted_limit(session_id, command):
    path = Path.home() / ".claude" / "grants" / "{}.json".format(session_id)
    if not path.exists() or CHAINING.search(command):
        return None
    now = time.time()
    limits = [g["limit"] for g in json.loads(path.read_text())
              if g["expires"] > now and re.match(g["pattern"], command)]
    return max(limits) if limits else None


try:
    event = json.load(sys.stdin)
    tool_input = dict(event["tool_input"])
    command = tool_input["command"]
    limit = granted_limit(event["session_id"], command)
    if limit is None:
        limit = DEFAULT_LIMIT
        tool_input.pop("run_in_background", None)
    tool_input["timeout"] = (limit + 10) * 1000
    tool_input["command"] = " ".join(shlex.quote(part) for part in [sys.executable, str(LIMIT), str(limit), command])
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": tool_input}}))
except Exception as e:
    print("timeout hook failed, command blocked: {}".format(e), file=sys.stderr)
    sys.exit(2)
