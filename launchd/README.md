# Manual install: run the server on system start

This folder holds the launchd agent used to start the PTZ server on login.
It's a template — `__REPO_PATH__` must be replaced with the absolute path
to this repo on the target machine before installing.

## Install

1. Copy the plist into the current user's `LaunchAgents` folder:

   ```bash
   cp launchd/com.uutech.uu-dev-ptz.plist ~/Library/LaunchAgents/
   ```

2. Replace `__REPO_PATH__` with the absolute path to this repo (four
   occurrences):

   ```bash
   sed -i '' "s#__REPO_PATH__#$(pwd)#g" ~/Library/LaunchAgents/com.uutech.uu-dev-ptz.plist
   ```

3. Make sure the launcher script is executable and the log directory exists:

   ```bash
   chmod +x scripts/start_server.sh
   mkdir -p logs
   ```

4. Validate the plist, then load it:

   ```bash
   plutil -lint ~/Library/LaunchAgents/com.uutech.uu-dev-ptz.plist
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.uutech.uu-dev-ptz.plist
   ```

5. Confirm it's running and check the app on `http://localhost:5001`:

   ```bash
   launchctl list | grep uu-dev-ptz
   tail -f logs/launchd.err.log
   ```

## Notes

- `logs/launchd.err.log` is where application logs land — Python's
  `logging` module writes to stderr by default, so startup lines and
  errors show up here, not in `launchd.out.log`.
- The plist sets `PATH` explicitly so `python3` resolves the same way
  under launchd (no login shell) as it does in an interactive terminal.
  If `python3` lives somewhere unusual on the target machine, add that
  directory to the `PATH` entry.
- `RunAtLoad` starts it on login; `KeepAlive` restarts it if it crashes.
- To remove: `launchctl bootout gui/$(id -u)/com.uutech.uu-dev-ptz` then
  delete the file from `~/Library/LaunchAgents/`.

See `../LAUNCHD_SETUP.md` for how this repo's own dev machine is
configured.
