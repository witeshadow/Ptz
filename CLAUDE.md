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
