# ladstack

Global Claude Code guardrails for one user, on macOS or Linux, without sudo.

```sh
curl -fsSL https://raw.githubusercontent.com/leoadberg/ladstack/main/install.sh | sh
```

Needs `git` and `python3`. Installs to `~/.ladstack`, merges its hooks into `~/.claude/settings.json` (your other
settings stay), and checks for updates every 15 minutes via launchd, a systemd user timer or cron. Restart Claude Code
afterwards.

## Hard timeout

Every Bash command Claude runs is killed at 10 seconds, along with its process group, and Claude is told how to clean up.
The limit does not reach through ssh: put a `timeout` in the remote command too.

A command that lets a job outlive the limit is refused unless you grant it (below), here or inside an ssh command:
`nohup`, `setsid`, `systemd-run`, `disown`, or a new `tmux` or `screen` session. `&` is never refused.

To allow longer, put this anywhere in your message:

```
long:10m build the project
```

The `long:` prefix is case-insensitive, so `Long:1m` also works.

Until your next message, in that session, every command may run that long (`s`, `m`, `h`) and may run in the
background.

To let Claude start a job that outlives its command (a recrunch on another host, say), put `background:ok` anywhere in
your message (case-insensitive). Until your next message, in that session, the detaching commands above are allowed.
It combines with a `long:` grant.

## Adding a hook

Put the script in `hooks/`, list it in `hooks/manifest.json`, add a test to `tests/test_ladstack.py` and push. A machine
applies a new revision only if its tests pass there; see `update.log`.

## Removing

```sh
python3 ~/.ladstack/bin/setup.py --uninstall && rm -rf ~/.ladstack
```
