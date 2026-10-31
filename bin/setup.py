#!/usr/bin/env python3
"""Merge hooks/manifest.json into ~/.claude/settings.json and install the auto-updater. Safe to rerun.

setup.py --uninstall removes both."""
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home()
SETTINGS = HOME / ".claude" / "settings.json"
LABEL = "com.ladstack.update"
CRON_MARKER = "# ladstack-update"
INTERVAL_MINUTES = 15


def is_ours(hook):
    return str(ROOT / "hooks") in hook.get("command", "")


def without_our_hooks(settings):
    hooks = settings.get("hooks", {})
    for event in list(hooks):
        kept = []
        for group in hooks[event]:
            group["hooks"] = [h for h in group.get("hooks", []) if not is_ours(h)]
            if group["hooks"]:
                kept.append(group)
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if not hooks:
        settings.pop("hooks", None)


def write_settings(settings):
    # Follow a symlink so a dotfiles-managed settings file stays a symlink
    path = SETTINGS.resolve() if SETTINGS.exists() else SETTINGS
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".ladstack-tmp")
    tmp.write_text(json.dumps(settings, indent=2) + "\n")
    os.replace(str(tmp), str(path))


def read_settings():
    if not SETTINGS.exists():
        return {}
    try:
        return json.loads(SETTINGS.read_text())
    except ValueError as e:
        sys.exit("ladstack: {} is not valid JSON, not touching it: {}".format(SETTINGS, e))


def install_hooks():
    manifest = json.loads((ROOT / "hooks" / "manifest.json").read_text())
    settings = read_settings()
    if SETTINGS.exists():
        backup = SETTINGS.with_name("settings.json.before-ladstack")
        if not backup.exists():
            shutil.copy2(str(SETTINGS), str(backup))
    without_our_hooks(settings)
    settings.setdefault("env", {}).update(manifest["env"])
    for entry in manifest["hooks"]:
        command = " ".join(shlex.quote(p) for p in [sys.executable, str(ROOT / "hooks" / entry["script"])])
        group = {"hooks": [{"type": "command", "command": command}]}
        if "matcher" in entry:
            group["matcher"] = entry["matcher"]
        settings.setdefault("hooks", {}).setdefault(entry["event"], []).append(group)
    write_settings(settings)


def uninstall_hooks():
    manifest = json.loads((ROOT / "hooks" / "manifest.json").read_text())
    settings = read_settings()
    without_our_hooks(settings)
    env = settings.get("env", {})
    for key, value in manifest["env"].items():
        if env.get(key) == value:
            del env[key]
    if not env:
        settings.pop("env", None)
    write_settings(settings)


def run(*args):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, timeout=30)


def update_command():
    return [sys.executable, str(ROOT / "bin" / "update.py")]


def launchd_plist():
    return HOME / "Library" / "LaunchAgents" / (LABEL + ".plist")


def install_launchd():
    args = "".join("<string>{}</string>".format(a) for a in update_command())
    plist = launchd_plist()
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>'
        "<key>Label</key><string>{}</string>"
        "<key>ProgramArguments</key><array>{}</array>"
        "<key>StartInterval</key><integer>{}</integer>"
        "<key>RunAtLoad</key><true/>"
        "</dict></plist>\n".format(LABEL, args, INTERVAL_MINUTES * 60))
    domain = "gui/{}".format(os.getuid())
    run("launchctl", "bootout", domain + "/" + LABEL)
    return run("launchctl", "bootstrap", domain, str(plist)).returncode == 0


def systemd_dir():
    return Path(os.environ.get("XDG_CONFIG_HOME", str(HOME / ".config"))) / "systemd" / "user"


def systemd_available():
    return shutil.which("systemctl") is not None and run("systemctl", "--user", "show-environment").returncode == 0


def install_systemd():
    units = systemd_dir()
    units.mkdir(parents=True, exist_ok=True)
    (units / "ladstack-update.service").write_text(
        "[Unit]\nDescription=Update ladstack\n\n[Service]\nType=oneshot\nExecStart={}\n".format(
            " ".join(shlex.quote(a) for a in update_command())))
    (units / "ladstack-update.timer").write_text(
        "[Unit]\nDescription=Update ladstack every {0} minutes\n\n"
        "[Timer]\nOnBootSec=5min\nOnUnitActiveSec={0}min\nPersistent=true\n\n"
        "[Install]\nWantedBy=timers.target\n".format(INTERVAL_MINUTES))
    run("systemctl", "--user", "daemon-reload")
    ok = run("systemctl", "--user", "enable", "--now", "ladstack-update.timer").returncode == 0
    # Keeps the timer running while logged out. Best effort: some hosts refuse it without root.
    if shutil.which("loginctl"):
        run("loginctl", "enable-linger")
    return ok


def cron_lines():
    listing = run("crontab", "-l")
    lines = listing.stdout.splitlines() if listing.returncode == 0 else []
    return [line for line in lines if CRON_MARKER not in line]


def write_crontab(lines):
    text = "".join(line + "\n" for line in lines)
    return subprocess.run(["crontab", "-"], input=text, universal_newlines=True, timeout=30).returncode == 0


def install_cron():
    command = " ".join(shlex.quote(a) for a in update_command())
    return write_crontab(cron_lines() + ["*/{} * * * * {} {}".format(INTERVAL_MINUTES, command, CRON_MARKER)])


def install_updater():
    if platform.system() == "Darwin":
        if install_launchd():
            return "launchd"
    elif systemd_available() and install_systemd():
        return "systemd user timer"
    if shutil.which("crontab") and install_cron():
        return "cron"
    return None


def uninstall_updater():
    if platform.system() == "Darwin" and shutil.which("launchctl"):
        run("launchctl", "bootout", "gui/{}/{}".format(os.getuid(), LABEL))
        if launchd_plist().exists():
            launchd_plist().unlink()
    if (systemd_dir() / "ladstack-update.timer").exists():
        if systemd_available():
            run("systemctl", "--user", "disable", "--now", "ladstack-update.timer")
        for name in ("ladstack-update.timer", "ladstack-update.service"):
            (systemd_dir() / name).unlink()
    if shutil.which("crontab"):
        listing = run("crontab", "-l")
        if listing.returncode == 0 and CRON_MARKER in listing.stdout:
            write_crontab(cron_lines())


def main():
    if "--uninstall" in sys.argv[1:]:
        uninstall_hooks()
        uninstall_updater()
        print("ladstack: removed hooks and updater. Delete {} to finish.".format(ROOT))
        return
    install_hooks()
    print("ladstack: hooks installed in {}. Restart Claude Code to load them.".format(SETTINGS))
    if "--hooks-only" in sys.argv[1:]:
        return
    updater = install_updater()
    if updater:
        print("ladstack: auto-update every {} min via {}".format(INTERVAL_MINUTES, updater))
    else:
        print("ladstack: WARNING no launchd, systemd or cron available; run bin/update.py yourself", file=sys.stderr)


if __name__ == "__main__":
    main()
