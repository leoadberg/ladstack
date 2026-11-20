#!/usr/bin/env python3
"""UserPromptSubmit: grants in a message, until the next message.

long:10m lets commands run that long; background:ok lets them start jobs that outlive the command."""
import json
import os
import re
import sys
from pathlib import Path

UNITS = {"s": 1, "m": 60, "h": 3600}

event = json.load(sys.stdin)
path = Path.home() / ".claude" / "grants" / "{}.json".format(event["session_id"])
prompt = event.get("prompt", "")
# a background task's notification arrives as a prompt too: it is not the user's next message, so the grant stands
if "<task-notification>" in prompt or "[SYSTEM NOTIFICATION - NOT USER INPUT]" in prompt:
    sys.exit(0)
found = re.findall(r"(?:^|\s)(?i:long):(\d+)([smh])(?=\s|$)", prompt)
background = re.search(r"(?:^|\s)(?i:background:ok)(?=\s|$)", prompt) is not None
if not found and not background:
    if path.exists():
        path.unlink()
    sys.exit(0)

limit = max(int(amount) * UNITS[unit] for amount, unit in found) if found else None
path.parent.mkdir(parents=True, exist_ok=True)
tmp = path.with_suffix(".tmp")
tmp.write_text(json.dumps({"limit": limit, "background": background}))
os.replace(str(tmp), str(path))
if limit is not None:
    print("Timeout grant: every command may run up to {}s until the user's next message.".format(limit))
if background:
    print("Background grant: commands may start jobs that outlive them (nohup, setsid, tmux, & inside ssh) until the "
          "user's next message. Give such a job a PID file and wait on it.")
