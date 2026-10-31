# ladstack

Global Claude Code guardrails for one user, on macOS or Linux, without sudo.

```sh
curl -fsSL https://raw.githubusercontent.com/leoadberg/ladstack/main/install.sh | sh
```

Needs `git` and `python3`. Installs to `~/.ladstack`, merges its hooks into `~/.claude/settings.json` (your other
settings stay), and checks for updates every 15 minutes via launchd, a systemd user timer or cron. Restart Claude Code
afterwards.

## Hard timeout

Every Bash command Claude runs is killed at 60 seconds, along with its process group, and Claude is told how to clean up.
The limit does not reach through ssh: put a `timeout` in the remote command too.

To allow longer, put this in your message:

```
long:10m:make build the project
```

For 15 minutes, in that session, commands starting with that regex get 10 minutes (`s`, `m`, `h`; at most 1 h) and may run
in the background. A command containing `;`, `&`, `|`, a backtick, `$(` or a newline never qualifies.

## Adding a hook

Put the script in `hooks/`, list it in `hooks/manifest.json`, add a test to `tests/test_ladstack.py` and push. A machine
applies a new revision only if its tests pass there; see `update.log`.

## Removing

```sh
python3 ~/.ladstack/bin/setup.py --uninstall && rm -rf ~/.ladstack
```
