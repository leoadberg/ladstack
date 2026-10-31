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
found = re.findall(r"(?:^|\s)long:(\d+)([smh])(?=\s|$)", event.get("prompt", ""))
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
