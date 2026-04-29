# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

PTZ Preset Control is a local web app for recalling and cataloguing presets on AVIPAS cameras over VISCA IP. It also integrates with Blackmagic ATEM switchers so the active camera can follow the configured preview or program input.

## Running The Server

```bash
python server.py
```

The app serves from `http://localhost:5001`.

Optional dependencies:

| Feature | Dependency |
|---|---|
| URL capture (VDO.ninja, browser streams) | `pip install playwright && playwright install chromium` |
| USB capture fallback | `pip install opencv-python` |
| Primary USB capture | `ffmpeg` on the system path |

## Architecture

The project is intentionally small and centered in two files:

- `server.py`: threaded stdlib HTTP server, VISCA control, ATEM integration, SSE, device capture, and persistence.
- `public/index.html`: single-file SPA with inline CSS and JavaScript.

## State And Persistence

Persistent runtime state lives under `data/`:

- `data/settings.json`: cameras, labels, dwell time, grid settings, ATEM config, live/edit mode, and follow mode.
- `data/images/{cam}_{preset}.jpg`: saved preset thumbnails.

Preset labels are keyed in settings as `"{cam}:{preset}"`.

The browser stores only the selected local webcam device in `localStorage`.

## ATEM Integration

`server.py` runs a background `_atem_loop()` that maintains the UDP connection to the ATEM switcher and broadcasts Server-Sent Events on `/events`.

The frontend listens for:

- `atem`: connection state plus initial preview/program values
- `preview`: preview source changes
- `program`: program source changes

In Live mode, the UI can follow either preview or program based on `atemFollows`.

## Capture Priority

When scanning or capturing preset thumbnails, the app uses this priority:

1. Configured USB device through `ffmpeg`
2. Configured stream URL through Playwright
3. Browser webcam capture fallback

## Verification

CI currently checks:

- `ruff check server.py`
- `python -m py_compile server.py`
- extracted inline JS syntax from `public/index.html`
- HTML structure sanity for `public/index.html`

Always run these locally before declaring a change done:

```bash
ruff check server.py
python -m py_compile server.py
```

For frontend changes, also verify JS syntax by extracting the `<script>` block and running `node --check` against it.

## Architecture Constraints

- Do NOT create new `.py` files. All backend logic belongs in `server.py`.
- Do NOT create separate CSS/JS files. All frontend belongs in `public/index.html`.
- Python 3.12 is the target. Use `int | None` union syntax, walrus operator (`:=`), f-strings, etc.
- No test suite exists. Verification is: lint + compile + manual server start.

## Threading Safety

Globals protected by locks — always acquire the lock before reading or writing them:

- `_sse_clients` → `_sse_lock`
- `_atem_state` → `_atem_state_lock`

The server uses `ThreadingMixIn` — every request runs in its own thread. Any shared mutable state needs a lock.

## Exception Handling

Broad `except Exception` is intentional in network, subprocess, and thread contexts — these must not crash background loops or individual HTTP handlers. Do not narrow them to specific exception types unless you know the full set a given call can raise.

## Settings Schema

Settings keys in `data/settings.json` are referenced by name in both `server.py` and the inline JS in `public/index.html`. Renaming or restructuring a key requires updating both files simultaneously. New keys need a default value added to `DEFAULT_SETTINGS` in `server.py`.

## VISCA Protocol

VISCA commands are binary with specific byte ordering and camera address encoding. When modifying `send_visca_preset_recall` or `inquire_visca_pan_tilt_position`, verify byte layout against the VISCA spec. Wrong bytes may be silently accepted by the camera but produce wrong behavior with no error.

## Common Mistakes (learned)

- Do not add `# type: ignore` comments without a specific reason — ruff will flag unnecessary ones.
- Do not remove `with _sse_lock:` guards around `_sse_clients` access even if the operation looks atomic.
- Settings POST at `_handle_settings_post` does a full replace — do not change it to a merge without understanding the frontend's save behavior.
- Do not split `server.py` or `public/index.html` into multiple files to "clean up" — the single-file constraint is intentional.
