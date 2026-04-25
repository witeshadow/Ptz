# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

PTZ Preset Control — a local web app for recalling and cataloguing presets on AVIPAS cameras via VISCA over IP. It also integrates with Blackmagic ATEM switchers to automatically switch the active camera when the ATEM preview input changes.

## Running the server

```bash
python server.py        # starts on http://localhost:5001
```

No build step. All dependencies are stdlib except optional extras:

| Feature | Dependency |
|---|---|
| Stream URL capture (VDO.ninja etc.) | `pip install playwright && playwright install chromium` |
| USB capture fallback | `pip install opencv-python` |
| USB capture (primary) | `ffmpeg` system binary |

## Architecture

The project is two files:

- **`server.py`** — a `ThreadedHTTPServer` (stdlib) with a single `Handler` class. All routing, VISCA, ATEM, and capture logic lives here.
- **`public/index.html`** — a self-contained SPA (all CSS and JS inline, no build tooling).

### State split

Server-side persistent state lives in `data/settings.json` (cameras, labels, dwell time, ATEM config). The webcam device ID is the only piece of state stored client-side (browser `localStorage`).

Preset snapshot images are stored as `data/images/{cam}_{preset}.jpg` — `cam` and `preset` are both 0-indexed integers.

Labels are keyed as `"{cam}:{preset}"` strings inside the `labels` dict in settings.

### ATEM integration

A single daemon thread (`_atem_loop`) maintains a UDP connection to the ATEM switcher using its binary protocol. When the preview input changes (`PrvI` command), it broadcasts a Server-Sent Event to all connected browsers, which then call `switchCamera()` to follow the preview. The SSE endpoint is `/events`; browsers auto-reconnect on drop.

### Image capture priority

When capturing a snapshot the server tries sources in this order:
1. USB/v4l2 device via `ffmpeg` (falls back to `cv2` if ffmpeg fails)
2. Stream URL via a persistent Playwright Chromium page (lazy-init singleton, reused across requests)

The browser can also capture directly from a local webcam and upload the JPEG blob, bypassing the server entirely — this path is used when neither `usbDevice` nor `streamUrl` is configured for the active camera.
