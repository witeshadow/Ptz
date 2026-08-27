# Run at System Start (launchd)

The server runs as a per-user launchd agent so it starts automatically on
login and restarts if it crashes.

## Files

- `~/Library/LaunchAgents/com.uutech.uu-dev-ptz.plist` — launchd agent
  definition (lives outside this repo, in your user Library folder).
- `scripts/start_server.sh` — launcher invoked by launchd. `cd`s into the
  repo and runs `python3 server.py`. No venv/uv needed — `server.py` is
  stdlib-only for a basic run (see optional deps in `CLAUDE.md` for URL/USB
  capture).
- `logs/` — launchd output, gitignored.
  - `logs/launchd.err.log` — this is where actual application logs land.
    Python's `logging` module writes to stderr by default, so ATEM/joystick
    thread activity, startup lines, and errors all show up here.
  - `logs/launchd.out.log` — captures stdout; normally empty.

## plist settings of note

- `Label`: `com.uutech.uu-dev-ptz` (matches the plist filename).
- `RunAtLoad`: true — starts on login.
- `KeepAlive`: true — launchd relaunches it if the process exits/crashes.
- Server binds `0.0.0.0:5001`, so once running it's reachable from other
  devices on the network, not just `localhost`.

## Useful commands

```bash
# live-tail logs for review
tail -f logs/launchd.err.log

# check it's running (shows PID + last exit status)
launchctl list | grep uu-dev-ptz

# stop it
launchctl bootout gui/$(id -u)/com.uutech.uu-dev-ptz

# start it (or restart after editing the plist)
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.uutech.uu-dev-ptz.plist

# validate the plist after hand-editing it
plutil -lint ~/Library/LaunchAgents/com.uutech.uu-dev-ptz.plist
```

## History

The plist was originally copied from another project's launch agent
(`shonk_webhook`) and had that project's `Label`, paths, and log locations.
It was rewritten to point at this repo and given a matching `Label`.
