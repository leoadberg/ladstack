#!/usr/bin/env python3
"""UserPromptSubmit: long:10m in a message lets commands run that long until the next message."""
import json
import os
import re
import sys
from pathlib import Path

MAX_LIMIT = 3600
UNITS = {"s": 1, "m": 60, "h": 3600}

event = json.load(sys.stdin)
path = Path.home() / ".claude" / "grants" / "{}.json".format(event["session_id"])
prompt = event.get("prompt", "")
# a background task's notification arrives as a prompt too: it is not the user's next message, so the grant stands
if "<task-notification>" in prompt or "[SYSTEM NOTIFICATION - NOT USER INPUT]" in prompt:
    sys.exit(0)
found = re.findall(r"(?:^|\s)long:(\d+)([smh])(?=\s|$)", prompt)
if not found:
    if path.exists():
        path.unlink()
    sys.exit(0)

limit = min(max(int(amount) * UNITS[unit] for amount, unit in found), MAX_LIMIT)
path.parent.mkdir(parents=True, exist_ok=True)
tmp = path.with_suffix(".tmp")
tmp.write_text(json.dumps({"limit": limit}))
os.replace(str(tmp), str(path))
print("Timeout grant: every command may run up to {}s until the user's next message.".format(limit))
