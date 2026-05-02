# AGENTS.md

Guidance for coding agents working in this repository.

## Project

PTZ Preset Control is a local web app for recalling and cataloguing AVIPAS camera presets over VISCA IP. It also integrates with a Blackmagic ATEM so the active camera can follow preview or program.

## Operating Context

This app is used for live production of a multi-camera church service.

- Operators are experienced and should be treated that way.
- The app still needs strong guardrails against live-production mistakes.
- Guardrails matter most for:
  - moving a camera that is live on program
  - overwriting preset thumbnails with the wrong image
  - bulk actions that silently produce misleading results
- Before or after the service, some workflows can favor convenience because nobody is watching live.

When in doubt: protect live output first, then optimize convenience.

## Run

```bash
python server.py
```

App URL: `http://localhost:5001`

Optional dependencies:

| Feature | Dependency |
|---|---|
| URL capture | `pip install playwright && playwright install chromium` |
| USB capture fallback | `pip install opencv-python` |
| Primary USB capture | `ffmpeg` on the system path |

## Architecture

The app is intentionally small:

- `server.py`: stdlib HTTP server, VISCA control, ATEM integration, SSE, capture, persistence
- `public/index.html`: single-file SPA with inline CSS and JavaScript

Important constraint:

- This is **not Flask**
- Routes are hand-written in `do_GET`, `do_POST`, and `do_DELETE`
- Frontend JS lives in the single `<script>` block in `public/index.html`

## State

Persistent state lives in `data/`:

- `data/settings.json`
- `data/images/{cam}_{preset}.jpg`

Preset label keys use the form `"{cam}:{preset}"`.

The browser stores only the selected preview webcam device in `localStorage`.

## Behavior That Matters

### Live safety

- Live-mode behavior must avoid accidental movement of the live camera.
- Scan or capture flows should not silently generate bad preset images.
- Prefer explicit errors over “doing something convenient but wrong.”

### ATEM

`server.py` runs a background `_atem_loop()` and pushes SSE events on `/events`.

Frontend event types:

- `atem`
- `preview`
- `program`

In Live mode, the UI can follow either preview or program via `atemFollows`.

### Capture priority

Preset image capture uses this order:

1. Configured USB device through `ffmpeg`
2. Configured stream URL through Playwright
3. Browser webcam fallback

## Common Change Pattern

Most features touch these places in order:

1. `server.py` route or backend behavior
2. `DEFAULT_SETTINGS` if new state is persisted
3. `public/index.html` state, fetch logic, and rendering

If a new UI setting persists, add it to both server defaults and frontend state.

## Verification

Use these checks before pushing:

```bash
ruff check server.py
python -m py_compile server.py
uv run pytest tests/test_frontend_contracts.py
```

## Working Rules

- Keep solutions simple and local.
- Preserve the single-file frontend structure unless there is a strong reason not to.
- Favor clear operator feedback for risky actions.
- Design for mobile and iOS Safari, not just desktop.
