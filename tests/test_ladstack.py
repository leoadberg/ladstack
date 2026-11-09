#!/usr/bin/env python3
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.home = Path(self._tmp.name)
        self.env = dict(os.environ, HOME=str(self.home))
        self.env.pop("XDG_CONFIG_HOME", None)

    def tearDown(self):
        self._tmp.cleanup()

    def hook(self, script, event):
        return subprocess.run([sys.executable, str(ROOT / "hooks" / script)], input=json.dumps(event).encode(),
                              env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10)

    def wrap(self, command, **extra):
        event = {"session_id": "s", "tool_input": dict(command=command, **extra)}
        result = self.hook("timeout.py", event)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)["hookSpecificOutput"]["updatedInput"]

    def limit_of(self, command):
        return int(shlex.split(self.wrap(command)["command"])[2])


class TimeoutHook(Base):
    def test_default_limit_and_no_background(self):
        updated = self.wrap("sleep 90", run_in_background=True, description="d")
        self.assertEqual(shlex.split(updated["command"])[2:], ["60", "sleep 90"])
        self.assertNotIn("run_in_background", updated)
        self.assertEqual(updated["description"], "d")
        self.assertEqual(updated["timeout"], 70000)

    def test_quoting_survives(self):
        command = """echo "a'b" 'c"d' $HOME"""
        self.assertEqual(shlex.split(self.wrap(command)["command"])[3], command)

    def test_grant_covers_every_command(self):
        out = self.hook("grant.py", {"session_id": "s", "prompt": "long:10m please run it"})
        self.assertIn(b"600s", out.stdout)
        self.assertEqual(self.limit_of("sleep 90"), 600)
        self.assertEqual(self.limit_of("cd x && make; make test"), 600)

    def test_grant_ends_at_next_message(self):
        self.hook("grant.py", {"session_id": "s", "prompt": "long:10m"})
        self.hook("grant.py", {"session_id": "s", "prompt": "thanks, now the next thing"})
        self.assertEqual(self.limit_of("sleep 90"), 60)

    def test_grant_keeps_background(self):
        self.hook("grant.py", {"session_id": "s", "prompt": "long:2m"})
        self.assertTrue(self.wrap("sleep 90", run_in_background=True)["run_in_background"])

    def test_grant_is_per_session(self):
        self.hook("grant.py", {"session_id": "other", "prompt": "long:10m"})
        self.assertEqual(self.limit_of("sleep 90"), 60)

    def test_grant_is_capped(self):
        self.hook("grant.py", {"session_id": "s", "prompt": "long:9h"})
        self.assertEqual(self.limit_of("sleep 90"), 3600)

    def test_no_grant_in_ordinary_message(self):
        for prompt in ("belong:10m", "long:10m:make", "long:10"):
            self.hook("grant.py", {"session_id": "s", "prompt": prompt})
            self.assertFalse((self.home / ".claude" / "grants" / "s.json").exists())

    def test_nohup_blocked_without_grant(self):
        for command in ("nohup ./pull.sh > log 2>&1 &", "cd x; nohup make", "FOO=1 nohup make", "sudo nohup make",
                        "ssh ec2 'nohup ./job.sh &'", "(nohup make &)", "x && nohup\tmake"):
            result = self.hook("timeout.py", {"session_id": "s", "tool_input": {"command": command}})
            self.assertEqual(result.returncode, 2, command)
            self.assertIn(b"nohup is blocked", result.stderr)

    def test_nohup_mentions_pass(self):
        for command in ("man nohup", "grep -c nohup log", "echo nohupx", "ls nohup.out"):
            self.assertEqual(self.limit_of(command), 60, command)

    def test_nohup_allowed_with_grant(self):
        self.hook("grant.py", {"session_id": "s", "prompt": "long:10m"})
        self.assertEqual(self.limit_of("nohup make &"), 600)

    def test_hook_failure_blocks(self):
        path = self.home / ".claude" / "grants" / "s.json"
        path.parent.mkdir(parents=True)
        path.write_text("not json")
        result = self.hook("timeout.py", {"session_id": "s", "tool_input": {"command": "sleep 1"}})
        self.assertEqual(result.returncode, 2)


class Limit(unittest.TestCase):
    def run_limit(self, limit, command):
        return subprocess.run([sys.executable, str(ROOT / "bin" / "limit.py"), str(limit), command],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)

    def test_passes_output_and_exit_code(self):
        result = self.run_limit(5, "echo hi; exit 7")
        self.assertEqual((result.returncode, result.stdout), (7, b"hi\n"))

    def test_kills_whole_group_at_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "survived"
            started = time.time()
            result = self.run_limit(1, "(sleep 2; touch {}) & wait".format(shlex.quote(str(marker))))
            self.assertEqual(result.returncode, 124)
            self.assertIn(b"HARD TIMEOUT: this command was killed", result.stdout)
            self.assertIn(b"long: grant", result.stdout)
            self.assertIn(b"split it into chunks", result.stdout)
            self.assertLess(time.time() - started, 2)
            time.sleep(1.5)
            self.assertFalse(marker.exists())


class Setup(Base):
    def setUp(self):
        super().setUp()
        # Stand-ins so tests never reach this machine's real scheduler
        self.bin = self.home / "fakebin"
        self.bin.mkdir()
        for name in ("systemctl", "loginctl", "launchctl"):
            self.fake(name, "exit 1")
        self.cron = self.home / "crontab"
        self.fake("crontab", 'if [ "$1" = "-l" ]; then cat {0} 2>/dev/null; else cat > {0}; fi'.format(shlex.quote(str(self.cron))))
        self.env["PATH"] = str(self.bin) + ":" + self.env["PATH"]
        self.settings = self.home / ".claude" / "settings.json"

    def fake(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)

    def setup_cmd(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "bin" / "setup.py")] + list(args), env=self.env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)

    def test_merge_is_idempotent_and_keeps_user_settings(self):
        self.settings.parent.mkdir()
        mine = {"type": "command", "command": "mine"}
        self.settings.write_text(json.dumps({"model": "x", "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [mine]}]}}))
        for _ in range(2):
            self.assertEqual(self.setup_cmd("--hooks-only").returncode, 0)
        settings = json.loads(self.settings.read_text())
        self.assertEqual(settings["model"], "x")
        self.assertEqual(len(settings["hooks"]["PreToolUse"]), 2)
        self.assertEqual(settings["hooks"]["PreToolUse"][0]["hooks"], [mine])
        self.assertEqual(len(settings["hooks"]["UserPromptSubmit"]), 1)

    def test_refuses_invalid_settings(self):
        self.settings.parent.mkdir()
        self.settings.write_text("{oops")
        self.assertNotEqual(self.setup_cmd("--hooks-only").returncode, 0)
        self.assertEqual(self.settings.read_text(), "{oops")

    @unittest.skipIf(sys.platform == "darwin", "launchd path")
    def test_cron_fallback_and_uninstall(self):
        self.cron.write_text("0 0 * * * keep\n")
        for _ in range(2):
            self.assertEqual(self.setup_cmd().returncode, 0)
        lines = self.cron.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(self.setup_cmd("--uninstall").returncode, 0)
        self.assertEqual(self.cron.read_text(), "0 0 * * * keep\n")
        self.assertEqual(json.loads(self.settings.read_text()), {})


if __name__ == "__main__":
    unittest.main()
