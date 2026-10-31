#!/usr/bin/env python3
"""UserPromptSubmit: a message containing long:10m:<regex> grants matching commands a longer limit."""
import json
import os
import re
import sys
import time
from pathlib import Path

TTL = 15 * 60
MAX_LIMIT = 3600
UNITS = {"s": 1, "m": 60, "h": 3600}

event = json.load(sys.stdin)
found = re.findall(r"(?:^|\s)long:(\d+)([smh]):(\S+)", event.get("prompt", ""))
if not found:
    sys.exit(0)

path = Path.home() / ".claude" / "grants" / "{}.json".format(event["session_id"])
path.parent.mkdir(parents=True, exist_ok=True)
now = time.time()
grants = json.loads(path.read_text()) if path.exists() else []
grants = [g for g in grants if g["expires"] > now]
for amount, unit, pattern in found:
    try:
        re.compile(pattern)
    except re.error as e:
        print("Timeout grant NOT created, bad regex {!r}: {}".format(pattern, e))
        continue
    limit = min(int(amount) * UNITS[unit], MAX_LIMIT)
    grants.append({"pattern": pattern, "limit": limit, "expires": now + TTL})
    print("Timeout grant: commands starting with {!r} may run {}s, for the next {} min.".format(pattern, limit, TTL // 60))

tmp = path.with_suffix(".tmp")
tmp.write_text(json.dumps(grants))
os.replace(str(tmp), str(path))
